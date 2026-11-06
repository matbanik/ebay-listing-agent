"""
eBay REST API client for the listing pipeline (replaces the ebay-mcp server).

Covers only the calls the workflows make: Taxonomy, Metadata, Account, Browse,
Media (image upload) and the Inventory item/offer lifecycle. Endpoint paths,
headers and retry rules are ported from ebay-mcp v1.17.0 (MIT,
github.com/YosefHayim/ebay-mcp), which this pipeline used before.

Credentials come from .env at the repo root (gitignored); real environment
variables override it:
    EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_USER_REFRESH_TOKEN,
    EBAY_REDIRECT_URI (RuName, only for auth-url/exchange-code),
    EBAY_ENVIRONMENT (production|sandbox), EBAY_MARKETPLACE_ID, EBAY_CONTENT_LANGUAGE

Seller settings (policy IDs, inventory location, thresholds) come from
account.json (gitignored), which `setup` writes. See tools/account_config.py.

Output is JSON on stdout. eBay errors go to stderr as JSON, exit code 1.
A refused safety gate exits with code 2.

Usage (see .agent/skills/ebay-api/SKILL.md):
    python tools/ebay_api.py setup                               # once: writes account.json
    python tools/ebay_api.py categories "sony wh-1000xm5"
    python tools/ebay_api.py aspects 112529
    python tools/ebay_api.py condition-policies 112529
    python tools/ebay_api.py upload-images sony-wh-1000xm5 --replace
    python tools/ebay_api.py put-item sony-wh-1000xm5
    python tools/ebay_api.py create-offer sony-wh-1000xm5
    python tools/ebay_api.py fees <offerId>
    python tools/ebay_api.py publish <offerId> --confirm         # human-approved only
    python tools/ebay_api.py reconcile [--archive]               # sold -> listings/archive/
"""

import argparse
import base64
import json
import os
import re
import statistics
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from account_config import DEFAULT_PIPELINE, POLICY_KEYS, account_path, account_problems, load_account  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
TOKEN_CACHE = ROOT / ".ebay-token-cache.json"
LISTINGS = ROOT / "listings"

INVENTORY = "/sell/inventory/v1"
TAXONOMY = "/commerce/taxonomy/v1"
METADATA = "/sell/metadata/v1"
ACCOUNT = "/sell/account/v1"
BROWSE = "/buy/browse/v1"
MEDIA_UPLOAD = "/commerce/media/v1_beta/image/create_image_from_file"

APP_SCOPE = "https://api.ebay.com/oauth/api_scope"
# Scopes requested by auth-url. Enough for every command here.
USER_SCOPES = [
    APP_SCOPE,
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
]
CATEGORY_TREES = {"EBAY_US": "0"}  # other marketplaces: looked up via getDefaultCategoryTreeId

TIMEOUT = 30
SERVER_RETRIES = 3
TOKEN_SKEW = 300  # refresh this many seconds before expiry
MAX_IMAGES = 24

# Known eBay errors -> what to do about them
ERROR_HINTS = {
    1001: "Access token invalid. Run again (the token is refreshed automatically); if it persists the refresh "
          "token expired: run auth-url / exchange-code.",
    1100: "Access denied: the token lacks a scope this call needs. Re-consent with auth-url / exchange-code.",
    25005: "Category is not valid for EBAY_US (eBay Motors tree 100?). Use the tree-0 category, e.g. 57988 for "
           "riding apparel.",
    25709: "Invalid Content-Language/Accept-Language. Check EBAY_CONTENT_LANGUAGE (en-US).",
    21919301: "UPC/ISBN missing in a category that requires it. Set product.upc to [\"Does Not Apply\"].",
}
# 25002 is eBay's generic "user error" code, so match on the message text instead of the id
TEXT_HINTS = [
    ("already exists", "An offer already exists for this SKU. Use update-offer (the existing offerId is in the "
                       "error parameters)."),
    ("System error", "eBay-side system error (often transient). Wait a minute and retry; if it persists, check "
                     "the offer with get-offer."),
    ("ShippingPackage", "Remove packageWeightAndSize from inventory-item.json (flat-rate policy), put-item, retry."),
    ("ReturnsWithinOption", "Return window not allowed in this category; use the default return policy "
                            "(policies.return in account.json), then update-offer."),
    ("Business Polic", "The seller account is not opted in to Business Policies. Run "
                       "`setup --opt-in --confirm`, wait a few minutes, then create policies in Seller Hub."),
]


class EbayApiError(Exception):
    def __init__(self, status, method, url, body):
        self.status, self.method, self.url, self.body = status, method, url, body
        super().__init__(f"{method} {url} -> HTTP {status}")

    def error_ids(self):
        errors = self.body.get("errors", []) if isinstance(self.body, dict) else []
        return {e.get("errorId") for e in errors if isinstance(e, dict)}

    def to_dict(self):
        out = {"status": self.status, "method": self.method, "url": self.url, "response": self.body}
        hints = [ERROR_HINTS[i] for i in sorted(i for i in self.error_ids() if i in ERROR_HINTS)]
        text = json.dumps(self.body)
        hints += [h for needle, h in TEXT_HINTS if needle in text]
        if hints:
            out["hints"] = hints
        return out


class GateRefused(Exception):
    """A safety gate refused the command (exit code 2)."""


# --------------------------------------------------------------------------- config

def load_env_file(path=ENV_FILE):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_config(environment=None, env_file=ENV_FILE):
    """Settings from .env, overridden by real environment variables."""
    file_values = load_env_file(env_file)

    def get(key, default=None):
        return os.environ.get(key) or file_values.get(key) or default

    env = environment or get("EBAY_ENVIRONMENT", "production")
    if env not in ("production", "sandbox"):
        raise SystemExit(f"EBAY_ENVIRONMENT must be production or sandbox, got {env!r}")
    sandbox = ".sandbox" if env == "sandbox" else ""
    return {
        "environment": env,
        "client_id": get("EBAY_CLIENT_ID"),
        "client_secret": get("EBAY_CLIENT_SECRET"),
        "refresh_token": get("EBAY_USER_REFRESH_TOKEN"),
        "redirect_uri": get("EBAY_REDIRECT_URI"),
        "marketplace": get("EBAY_MARKETPLACE_ID", "EBAY_US"),
        "language": get("EBAY_CONTENT_LANGUAGE", "en-US"),
        "api_host": f"https://api{sandbox}.ebay.com",
        "media_host": f"https://apim{sandbox}.ebay.com",
        "auth_host": f"https://auth{sandbox}.ebay.com",
    }


def set_env_value(key, value, path=ENV_FILE):
    """Replace or append KEY=value in the .env file, keeping other lines."""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    out, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- client

class EbayClient:
    def __init__(self, config, session=None, cache_path=TOKEN_CACHE, sleep=time.sleep):
        self.config = config
        self.session = session or requests.Session()
        self.cache_path = cache_path
        self.sleep = sleep

    # ---- tokens

    def _read_cache(self):
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_cache(self, cache):
        try:
            self.cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except OSError:
            pass  # caching is an optimisation only

    def _cache_key(self, kind):
        return f"{self.config['environment']}:{kind}:{(self.config['client_id'] or '')[-6:]}"

    def _basic_auth(self):
        cid, secret = self.config["client_id"], self.config["client_secret"]
        if not (cid and secret):
            raise SystemExit("Missing EBAY_CLIENT_ID / EBAY_CLIENT_SECRET (set them in .env at the repo root).")
        return "Basic " + base64.b64encode(f"{cid}:{secret}".encode()).decode()

    def _token_request(self, data):
        url = f"{self.config['api_host']}/identity/v1/oauth2/token"
        resp = self.session.request(
            "POST", url, data=data, timeout=TIMEOUT,
            headers={"Authorization": self._basic_auth(),
                     "Content-Type": "application/x-www-form-urlencoded"})
        body = _parse_body(resp)
        if resp.status_code != 200:
            raise EbayApiError(resp.status_code, "POST", url, body)
        return body

    def access_token(self, kind="user", force=False):
        """kind 'user' = seller token from the refresh token; 'app' = client credentials (Browse)."""
        key = self._cache_key(kind)
        cache = self._read_cache()
        entry = cache.get(key)
        if not force and entry and entry.get("expires_at", 0) - TOKEN_SKEW > time.time():
            return entry["access_token"]

        if kind == "app":
            body = self._token_request({"grant_type": "client_credentials", "scope": APP_SCOPE})
        else:
            if not self.config["refresh_token"]:
                raise SystemExit("Missing EBAY_USER_REFRESH_TOKEN (set it in .env at the repo root, "
                                 "or run auth-url / exchange-code).")
            # No scope parameter: eBay returns the scopes the refresh token was granted.
            body = self._token_request({"grant_type": "refresh_token",
                                        "refresh_token": self.config["refresh_token"]})
        cache[key] = {"access_token": body["access_token"],
                      "expires_at": time.time() + int(body.get("expires_in", 7200))}
        self._write_cache(cache)
        return body["access_token"]

    # ---- requests

    def default_headers(self):
        lang = self.config["language"]
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Content-Language": lang,
            # Without it the Inventory API rejects requests with error 25709.
            "Accept-Language": lang,
            "X-EBAY-C-MARKETPLACE-ID": self.config["marketplace"],
        }

    def request(self, method, path, *, params=None, body=None, files=None, token="user", host=None):
        """Send one API call. Returns the parsed JSON body ({} for 204).

        401 -> refresh the token once and retry; 429 -> fail with Retry-After;
        5xx -> up to 3 retries with exponential backoff.
        """
        url = (host or self.config["api_host"]) + path
        auth_retried = False
        attempt = 0
        while True:
            headers = self.default_headers()
            headers["Authorization"] = "Bearer " + self.access_token(token, force=auth_retried)
            kwargs = {"params": params, "headers": headers, "timeout": TIMEOUT}
            if files is not None:
                headers.pop("Content-Type")  # requests sets the multipart boundary
                kwargs["files"] = files
            elif body is not None:
                kwargs["data"] = json.dumps(body)
            try:
                resp = self.session.request(method, url, **kwargs)
            except requests.RequestException as e:
                if attempt < SERVER_RETRIES:
                    self.sleep(2 ** attempt)
                    attempt += 1
                    continue
                raise EbayApiError(None, method, url, {"transport_error": str(e)})

            status = resp.status_code
            if status == 401 and not auth_retried:
                auth_retried = True
                continue
            if status >= 500 and attempt < SERVER_RETRIES:
                self.sleep(2 ** attempt)
                attempt += 1
                continue
            data = _parse_body(resp)
            if status == 429:
                retry = resp.headers.get("Retry-After", "unknown")
                data = {"rate_limited": f"eBay rate limit hit; retry after {retry} s", "response": data}
            if status >= 400:
                raise EbayApiError(status, method, url, data)
            return data

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body=body, **kw)

    def put(self, path, body=None, **kw):
        return self.request("PUT", path, body=body, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def category_tree(self):
        tree = CATEGORY_TREES.get(self.config["marketplace"])
        if tree is None:
            tree = self.get(f"{TAXONOMY}/get_default_category_tree_id",
                            params={"marketplace_id": self.config["marketplace"]})["categoryTreeId"]
        return tree


def _parse_body(resp):
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text[:2000]}


# --------------------------------------------------------------------------- listing folders

def listing_dir(slug_or_path):
    p = Path(slug_or_path)
    if p.is_dir():
        return p.resolve()
    d = LISTINGS / slug_or_path
    if not d.is_dir():
        raise SystemExit(f"Listing folder not found: {slug_or_path} (looked in {d})")
    return d


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"Missing {path}")
    except ValueError as e:
        raise SystemExit(f"{path} is not valid JSON: {e}")


def write_json(path, data, indent=2):
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


def strip_private(body):
    """Drop our bookkeeping keys (leading underscore) before sending."""
    return {k: v for k, v in body.items() if not k.startswith("_")}


def log_call(folder, command, **fields):
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "command": command, **fields}
    with (folder / "api-log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_validator(folder):
    """Run validate_payload.py on the folder; refuse on errors."""
    sys.path.insert(0, str(Path(__file__).parent))
    from validate_payload import validate_target
    _, report = validate_target(folder)
    if report.errors:
        raise GateRefused("validate_payload.py found errors (fix them, or pass --skip-validate to debug):\n  - "
                          + "\n  - ".join(report.errors))
    return report.warnings


# --------------------------------------------------------------------------- offer checks (from ebay-mcp offerFormat.js)

def _amount(a):
    try:
        return float(a["value"]) if isinstance(a, dict) and "value" in a else None
    except (TypeError, ValueError):
        return None


def offer_format_errors(offer, creating=True):
    errs = []
    fmt = offer.get("format", "FIXED_PRICE")
    pricing = offer.get("pricingSummary") or {}
    duration = offer.get("listingDuration")
    best = ((offer.get("listingPolicies") or {}).get("bestOfferTerms") or {})
    if fmt == "FIXED_PRICE":
        if duration not in (None, "GTC"):
            errs.append("FIXED_PRICE offers must use listingDuration GTC")
        if "auctionStartPrice" in pricing or "auctionReservePrice" in pricing:
            errs.append("auctionStartPrice/auctionReservePrice only apply to AUCTION offers")
        if creating and _amount(pricing.get("price")) is None:
            errs.append("pricingSummary.price.value is required")
        floor, price = _amount(best.get("autoDeclinePrice")), _amount(pricing.get("price"))
        if floor is not None and price is not None and floor >= price:
            errs.append(f"bestOfferTerms.autoDeclinePrice {floor} must be below the price {price}")
    elif fmt == "AUCTION":
        if duration == "GTC" or (creating and duration is None):
            errs.append("AUCTION offers need a day-count listingDuration such as DAYS_7")
        if offer.get("availableQuantity") not in (None, 1):
            errs.append("AUCTION offers list one unit; omit availableQuantity or set it to 1")
        start = _amount(pricing.get("auctionStartPrice"))
        if creating and start is None:
            errs.append("auctionStartPrice is required for AUCTION offers")
        reserve, bin_price = _amount(pricing.get("auctionReservePrice")), _amount(pricing.get("price"))
        if start is not None and reserve is not None and reserve <= start:
            errs.append("auctionReservePrice must be higher than auctionStartPrice")
        if start is not None and bin_price is not None and bin_price < start * 1.3:
            errs.append("Buy It Now (pricingSummary.price) must be at least 30% above auctionStartPrice")
        if best.get("bestOfferEnabled") and bin_price is not None:
            errs.append("an AUCTION offer can carry Best Offer or a Buy It Now price, not both")
    else:
        errs.append(f"Unknown format {fmt!r} (FIXED_PRICE or AUCTION)")
    return errs


def published_offers(client, sku):
    try:
        data = client.get(f"{INVENTORY}/offer", params={"sku": sku})
    except EbayApiError as e:
        if e.status == 404 or e.error_ids() & {25702, 25713}:
            return []
        raise
    return [o for o in data.get("offers", []) if o.get("status") == "PUBLISHED"]


# --------------------------------------------------------------------------- read-only commands

def cmd_policies(client, args):
    mp = client.config["marketplace"]
    out = {}
    for kind in ("fulfillment", "payment", "return"):
        data = client.get(f"{ACCOUNT}/{kind}_policy", params={"marketplace_id": mp})
        rows = []
        for p in data.get(f"{kind}Policies", []):
            row = {"id": p.get(f"{kind}PolicyId"), "name": p.get("name")}
            if kind == "fulfillment":
                row["handlingTime"] = (p.get("handlingTime") or {}).get("value")
                row["services"] = [s.get("shippingServiceCode")
                                   for o in p.get("shippingOptions", []) for s in o.get("shippingServices", [])]
                row["freeShipping"] = any(s.get("freeShipping") for o in p.get("shippingOptions", [])
                                          for s in o.get("shippingServices", []))
            elif kind == "return":
                row["returnsAccepted"] = p.get("returnsAccepted")
                row["period"] = (p.get("returnPeriod") or {}).get("value")
                row["payer"] = p.get("returnShippingCostPayer")
            else:
                row["immediatePay"] = p.get("immediatePay")
            rows.append(row)
        out[kind] = rows
    return out


def _pick_policy(kind, rows, explicit, existing):
    ids = [r["id"] for r in rows]
    if explicit:
        if explicit not in ids:
            raise GateRefused(f"--{kind} {explicit} is not one of this account's {kind} policies: {ids}")
        return explicit, "chosen with --" + kind
    if existing in ids:
        return existing, "kept from account.json"
    if len(rows) == 1:
        return ids[0], "the only one"
    if kind == "return":
        thirty = [r["id"] for r in rows if str(r.get("period")) == "30"]
        if len(thirty) == 1:
            return thirty[0], "the only 30-day return policy"
    if not rows:
        return None, "none found: create one in Seller Hub (Account > Business policies)"
    return None, f"{len(rows)} found: pass --{kind} ID"


def _inventory_locations(client):
    try:
        return client.get(f"{INVENTORY}/location", params={"limit": 100}).get("locations", [])
    except EbayApiError as e:
        if e.status == 404:
            return []
        raise


def cmd_setup(client, args):
    """Discover policies and the inventory location and write account.json (re-runnable)."""
    if args.opt_in:
        if not args.confirm:
            raise GateRefused("--opt-in enrolls the seller account in Business Policies; add --confirm "
                              "only with the account owner's approval.")
        client.post(f"{ACCOUNT}/program/opt_in", {"programType": "SELLING_POLICY_MANAGEMENT"})
        return {"optedIn": "SELLING_POLICY_MANAGEMENT",
                "next": "Wait a few minutes, create shipping/payment/return policies in Seller Hub, run setup again"}

    path = account_path()
    existing = load_account(path) or {}
    old_seller, old_pol = existing.get("seller", {}), existing.get("policies", {})
    policies = cmd_policies(client, args)

    if args.create_location:
        if not args.confirm:
            raise GateRefused("--create-location creates an inventory location on the seller account; "
                              "add --confirm (human-approved).")
        if not (args.location_key and args.postal_code):
            raise GateRefused("--create-location needs --location-key and --postal-code.")
        address = {"postalCode": args.postal_code, "country": args.country}
        if args.city:
            address["city"] = args.city
        if args.state:
            address["stateOrProvince"] = args.state
        client.post(f"{INVENTORY}/location/{urllib.parse.quote(args.location_key)}",
                    {"location": {"address": address}, "locationTypes": ["WAREHOUSE"],
                     "name": args.location_key, "merchantLocationStatus": "ENABLED"})

    locations = _inventory_locations(client)
    keys = [loc.get("merchantLocationKey") for loc in locations]
    enabled = [k for k, loc in zip(keys, locations) if loc.get("merchantLocationStatus", "ENABLED") == "ENABLED"]
    if args.location_key:
        if args.location_key not in keys:
            raise GateRefused(f"--location-key {args.location_key} not found. Locations: {keys} "
                              "(or add --create-location --postal-code ... --confirm)")
        loc_key, loc_note = args.location_key, "chosen with --location-key"
    elif old_seller.get("merchantLocationKey") in keys:
        loc_key, loc_note = old_seller["merchantLocationKey"], "kept from account.json"
    elif len(enabled) == 1:
        loc_key, loc_note = enabled[0], "the only enabled location"
    else:
        loc_key = None
        loc_note = (f"{len(enabled)} found: pass --location-key KEY" if enabled else
                    "none found: add --create-location --location-key KEY --postal-code ZIP --confirm")
    address = next(((loc.get("location") or {}).get("address") or {} for loc in locations
                    if loc.get("merchantLocationKey") == loc_key), {})

    choices, chosen = {"merchantLocationKey": loc_note}, {}
    for kind in POLICY_KEYS:
        chosen[kind], choices[kind] = _pick_policy(kind, policies[kind], getattr(args, kind), old_pol.get(kind))
    return_ids = [r["id"] for r in policies["return"]]
    fourteen = [r["id"] for r in policies["return"] if str(r.get("period")) == "14"]
    if args.return_14_day and args.return_14_day not in return_ids:
        raise GateRefused(f"--return-14-day {args.return_14_day} is not one of this account's return policies")
    chosen["return_14_day"] = (args.return_14_day or (old_pol.get("return_14_day")
                               if old_pol.get("return_14_day") in return_ids else None)
                               or (fourteen[0] if len(fourteen) == 1 else None))
    fulfillment_ids = [r["id"] for r in policies["fulfillment"]]
    chosen["disallowed_fulfillment"] = sorted({i for i in (old_pol.get("disallowed_fulfillment") or [])
                                               + (args.disallow_fulfillment or []) if i in fulfillment_ids})

    account = {
        "_comment": "Written by `python tools/ebay_api.py setup`. Private: keep out of git.",
        "seller": {"marketplace": client.config["marketplace"], "merchantLocationKey": loc_key,
                   "postalCode": address.get("postalCode") or old_seller.get("postalCode"),
                   "country": address.get("country") or old_seller.get("country")},
        "policies": chosen,
        "pipeline": {**DEFAULT_PIPELINE, **(existing.get("pipeline") or {})},
    }
    problems = account_problems(account)
    if not args.dry_run:
        write_json(path, account)
    return {"file": str(path), "written": not args.dry_run, "account": account, "choices": choices,
            "problems": problems, "available": {"policies": policies, "locations": keys},
            "next": ("Ready: the Lister copies these IDs into offer.json; validate_payload.py checks them" if not problems else
                     "Fix the problems above, then run setup again")}


def cmd_categories(client, args):
    tree = client.category_tree()
    data = client.get(f"{TAXONOMY}/category_tree/{tree}/get_category_suggestions", params={"q": args.query})
    if args.raw:
        return data
    return [{
        "categoryId": s["category"]["categoryId"],
        "name": s["category"]["categoryName"],
        "path": " > ".join(a["categoryName"] for a in reversed(s.get("categoryTreeNodeAncestors", []))),
    } for s in data.get("categorySuggestions", [])]


def cmd_aspects(client, args):
    tree = client.category_tree()
    data = client.get(f"{TAXONOMY}/category_tree/{tree}/get_item_aspects_for_category",
                      params={"category_id": args.category_id})
    if args.raw:
        return data
    rows = []
    for a in data.get("aspects", []):
        c = a.get("aspectConstraint", {})
        values = [v["localizedValue"] for v in a.get("aspectValues", [])]
        rows.append({
            "name": a.get("localizedAspectName"),
            "required": bool(c.get("aspectRequired")),
            "usage": c.get("aspectUsage"),
            "mode": c.get("aspectMode"),
            "cardinality": c.get("itemToAspectCardinality"),
            "values": values[:args.max_values],
            "valueCount": len(values),
        })
    if args.required:
        rows = [r for r in rows if r["required"]]
    order = {True: 0, False: 1}
    rows.sort(key=lambda r: (order[r["required"]], r["usage"] != "RECOMMENDED"))
    return rows


def _condition_enum_by_id():
    sys.path.insert(0, str(Path(__file__).parent))
    from validate_payload import CONDITION_IDS
    return {v: k for k, v in CONDITION_IDS.items()}


def cmd_condition_policies(client, args):
    mp = client.config["marketplace"]
    data = client.get(f"{METADATA}/marketplace/{mp}/get_item_condition_policies",
                      params={"filter": f"categoryIds:{{{args.category_id}}}"})
    if args.raw:
        return data
    enums = _condition_enum_by_id()
    return [{
        "categoryId": p.get("categoryId"),
        "conditionRequired": p.get("itemConditionRequired"),
        "conditions": [{
            "id": int(c["conditionId"]),
            "enum": enums.get(int(c["conditionId"])),
            "label": c.get("conditionDescription"),
        } for c in p.get("itemConditions", [])],
    } for p in data.get("itemConditionPolicies", [])]


def cmd_return_policies(client, args):
    mp = client.config["marketplace"]
    data = client.get(f"{METADATA}/marketplace/{mp}/get_return_policies",
                      params={"filter": f"categoryIds:{{{args.category_id}}}"})
    if args.raw:
        return data
    out = []
    for p in data.get("returnPolicies", []):
        dom = p.get("domestic", {})
        out.append({
            "categoryId": p.get("categoryId"),
            "required": p.get("required"),
            "returnsAcceptanceEnabled": dom.get("returnsAcceptanceEnabled"),
            "domesticPeriods": [f"{x.get('value')} {x.get('unit')}" for x in dom.get("returnPeriods", [])],
            "domesticPayers": dom.get("returnShippingCostPayers"),
        })
    return out


def cmd_browse(client, args):
    filters = []
    if args.condition:
        filters.append("conditions:{" + args.condition.upper() + "}")
    if args.buy_it_now:
        filters.append("buyingOptions:{FIXED_PRICE}")
    params = {"q": args.query, "limit": args.limit}
    if filters:
        params["filter"] = ",".join(filters)
    data = client.get(f"{BROWSE}/item_summary/search", params=params, token="app")
    if args.raw:
        return data
    items = []
    for it in data.get("itemSummaries", []):
        price = _amount(it.get("price"))
        ship_opts = it.get("shippingOptions") or [{}]
        ship = _amount(ship_opts[0].get("shippingCost"))
        items.append({
            "title": it.get("title"),
            "price": price,
            "shipping": ship,
            "total": round(price + (ship or 0), 2) if price is not None else None,
            "condition": it.get("condition"),
            "buyingOptions": it.get("buyingOptions"),
            "url": it.get("itemWebUrl"),
        })
    totals = sorted(i["total"] for i in items if i["total"] is not None)
    stats = {"count": len(totals), "total_matches": data.get("total"),
             "note": "ACTIVE asking prices = ceiling only, not sold prices"}
    if totals:
        stats.update(min=totals[0], median=round(statistics.median(totals), 2), max=totals[-1])
    return {"stats": stats, "items": items}


def cmd_get_item(client, args):
    return client.get(f"{INVENTORY}/inventory_item/{urllib.parse.quote(args.sku, safe='')}")


def cmd_get_offer(client, args):
    return client.get(f"{INVENTORY}/offer/{args.offer_id}")


def cmd_offers(client, args):
    try:
        return client.get(f"{INVENTORY}/offer", params={"sku": args.sku})
    except EbayApiError as e:
        if e.status == 404 or e.error_ids() & {25702, 25713}:
            return {"offers": [], "total": 0}
        raise


# --------------------------------------------------------------------------- reconcile

STAMP_START, STAMP_END = "<!-- reconcile:start -->", "<!-- reconcile:end -->"


def classify_offers(offers):
    """Status of a SKU from its offers. A sold single-quantity item shows the
    listing OUT_OF_STOCK with soldQuantity >= 1 (the offer drops back to UNPUBLISHED)."""
    if not offers:
        return "NO_OFFER", {}
    offer = next((o for o in offers if (o.get("listing") or {}).get("listingId")), offers[0])
    listing = offer.get("listing") or {}
    sold = int(listing.get("soldQuantity") or 0)
    info = {"offerId": offer.get("offerId"), "offerStatus": offer.get("status"),
            "listingId": listing.get("listingId"), "listingStatus": listing.get("listingStatus"),
            "soldQuantity": sold}
    price = _amount((offer.get("pricingSummary") or {}).get("price"))
    if price is not None:
        info["price"] = price
    if listing.get("listingId"):
        info["url"] = f"https://www.ebay.com/itm/{listing['listingId']}"
    if not listing.get("listingId"):
        return "NEVER_LISTED", info
    if offer.get("status") == "PUBLISHED" and listing.get("listingStatus") == "ACTIVE":
        return "ACTIVE", info
    return ("SOLD" if sold > 0 else "ENDED"), info


def folder_sku(folder):
    offer_file = folder / "offer.json"
    if offer_file.is_file():
        try:
            sku = json.loads(offer_file.read_text(encoding="utf-8-sig")).get("sku")
            if sku:
                return sku
        except ValueError:
            pass
    return folder.name


def stamp_draft(folder, status, info, today, note=""):
    """Write (or replace) a reconcile block under the first heading of listing-draft.md."""
    draft = folder / "listing-draft.md"
    text = draft.read_text(encoding="utf-8-sig") if draft.is_file() else f"# Listing Draft — {folder.name}\n"
    text = re.sub(rf"\n?{re.escape(STAMP_START)}.*?{re.escape(STAMP_END)}\n?", "\n", text, flags=re.S)
    detail = ", ".join(f"{k} {info[k]}" for k in ("listingId", "listingStatus", "soldQuantity", "offerId")
                       if info.get(k) not in (None, ""))
    block = (f"{STAMP_START}\n> **Reconciled {today}: {status}**"
             f"{' — ' + detail if detail else ''}.{' ' + note if note else ''}\n"
             f"> This line supersedes any older status below. Written by `ebay_api.py reconcile`.\n{STAMP_END}\n")
    lines = text.splitlines(keepends=True)
    at = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
    lines[at:at] = ["\n", block]
    draft.write_text(re.sub(r"\n{3,}", "\n\n", "".join(lines)), encoding="utf-8")


def cmd_reconcile(client, args):
    """Compare every listing folder with eBay; with --archive, move SOLD folders to listings/archive/."""
    root = Path(args.root).resolve() if args.root else LISTINGS
    archive = root / "archive"
    today = datetime.now().date().isoformat()
    folders = [(d, "listings") for d in sorted(root.iterdir()) if d.is_dir() and d.name != "archive"]
    if archive.is_dir():
        folders += [(d, "archive") for d in sorted(archive.iterdir()) if d.is_dir()]
    if args.slug:
        folders = [f for f in folders if f[0].name in set(args.slug)]
    items, summary = [], {}
    for folder, where in folders:
        sku = folder_sku(folder)
        status, info = classify_offers(cmd_offers(client, argparse.Namespace(sku=sku)).get("offers", []))
        item = {"slug": folder.name, "location": where, "sku": sku, "status": status, **info}
        if where == "listings" and status == "SOLD":
            item["action"] = "archive"
        elif where == "archive" and status == "ACTIVE":
            item["action"] = "still live but archived: move back to listings/"
        elif where == "listings" and status in ("ENDED", "NO_OFFER", "NEVER_LISTED"):
            item["action"] = "review: not live and not sold (relist, or archive by hand)"
        if args.archive and item.get("action") == "archive":
            dest = archive / folder.name
            if dest.exists():
                item["action"] = f"NOT moved: {dest} already exists"
            else:
                archive.mkdir(exist_ok=True)
                stamp_draft(folder, status, info, today, "Archived from `listings/`.")
                folder.rename(dest)
                item["action"], item["location"] = "archived", "archive"
        elif args.archive and where == "archive" and status in ("SOLD", "NEVER_LISTED", "ENDED"):
            stamp_draft(folder, status, info, today)
        items.append(item)
        summary.setdefault(status, []).append(folder.name)
    pending = [i["slug"] for i in items if i.get("action") == "archive"]
    return {"checked": today, "summary": summary, "items": items,
            "next": (f"Run with --archive to move {len(pending)} sold folder(s) to listings/archive/"
                     if pending else "Nothing to archive"),
            "note": "Sale price and buyer need the sell.fulfillment scope (getOrders); this checks listing status only"}


def listing_fees(client, offer_id):
    data = client.post(f"{INVENTORY}/offer/get_listing_fees", {"offers": [{"offerId": offer_id}]})
    fees, total = [], 0.0
    for summary in data.get("feeSummaries", []):
        for fee in summary.get("fees", []):
            amt = _amount(fee.get("amount")) or 0.0
            fees.append({"type": fee.get("feeType"), "amount": amt,
                         "promotionalDiscount": _amount(fee.get("promotionalDiscount"))})
            total += amt - (_amount(fee.get("promotionalDiscount")) or 0.0)
    return {"offerId": offer_id, "total": round(total, 2), "fees": [f for f in fees if f["amount"]],
            "note": "Insertion/upgrade fees only; final value fees are charged when the item sells",
            "warnings": [w for s in data.get("feeSummaries", []) for w in s.get("warnings", [])]}


def cmd_fees(client, args):
    return listing_fees(client, args.offer_id)


# --------------------------------------------------------------------------- write commands

def cmd_upload_images(client, args):
    folder = listing_dir(args.slug)
    slug = folder.name
    if args.files:
        paths = [Path(p) for p in args.files]
    else:
        paths = sorted(p for p in folder.iterdir()
                       if re.fullmatch(rf"{re.escape(slug)}-\d+\.(jpe?g|png|gif|webp)", p.name, re.IGNORECASE))
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise SystemExit(f"Image not found: {', '.join(missing)}")
    if not paths:
        raise SystemExit(f"No {slug}-NN.jpg images in {folder}")

    out_path = folder / "image-urls.json"
    existing = []
    if not args.replace and out_path.exists():
        existing = read_json(out_path)
        if not isinstance(existing, list):
            raise SystemExit(f"{out_path} is not a JSON array; rerun with --replace")
    if len(existing) + len(paths) > MAX_IMAGES:
        raise SystemExit(f"{len(existing) + len(paths)} images; eBay allows {MAX_IMAGES}")

    types = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
    uploaded, failures = [], []
    for p in paths:
        ctype = types.get(p.suffix.lower(), "image/jpeg")
        try:
            with p.open("rb") as fh:
                data = client.request("POST", MEDIA_UPLOAD, host=client.config["media_host"],
                                      files={"image": (p.name, fh, ctype)})
        except EbayApiError as e:
            failures.append({"file": p.name, "error": e.to_dict()})
            continue
        url = data.get("imageUrl")
        if not url:
            failures.append({"file": p.name, "error": data})
            continue
        uploaded.append(url)
        print(f"uploaded {p.name}", file=sys.stderr)

    if uploaded:
        write_json(out_path, existing + uploaded, indent=4)
        log_call(folder, "upload-images", count=len(uploaded), replace=args.replace, failures=len(failures))
    result = {"written": str(out_path) if uploaded else None, "uploaded": uploaded,
              "total": len(existing) + len(uploaded), "failures": failures}
    if failures:
        print(json.dumps(result, indent=2), file=sys.stderr)
        raise SystemExit(1)
    return result


def _confirm_live_change(client, sku, args, what):
    live = published_offers(client, sku)
    if live and not args.confirm:
        ids = ", ".join(str((o.get("listing") or {}).get("listingId") or o.get("offerId")) for o in live)
        raise GateRefused(f"{what} changes a LIVE listing ({ids}). Get the human's approval for this "
                          f"change, then rerun with --confirm.")
    return live


def cmd_put_item(client, args):
    folder = listing_dir(args.slug)
    sku = folder.name
    body = read_json(folder / "inventory-item.json")
    if "packageWeightAndSize" in body:
        raise GateRefused("inventory-item.json has packageWeightAndSize; remove it (it causes "
                          "'Invalid ShippingPackage' with the flat-rate shipping policy).")
    urls_path = folder / "image-urls.json"
    if urls_path.exists():
        urls = read_json(urls_path)
        body.setdefault("product", {})["imageUrls"] = urls
    if not (body.get("product") or {}).get("imageUrls"):
        raise GateRefused("No product.imageUrls and no image-urls.json; run upload-images first.")
    warnings = [] if args.skip_validate else run_validator(folder)
    live = _confirm_live_change(client, sku, args, "put-item")

    client.put(f"{INVENTORY}/inventory_item/{urllib.parse.quote(sku, safe='')}", strip_private(body))
    log_call(folder, "put-item", sku=sku, images=len(body["product"]["imageUrls"]), live=bool(live))
    return {"sku": sku, "status": "saved", "images": len(body["product"]["imageUrls"]),
            "liveListingUpdated": bool(live), "validatorWarnings": warnings}


def cmd_create_offer(client, args):
    folder = listing_dir(args.slug)
    sku = folder.name
    path = folder / "offer.json"
    offer = read_json(path)
    if offer.get("_offerId"):
        raise GateRefused(f"offer.json already has _offerId {offer['_offerId']}; use update-offer.")
    if offer.get("sku") != sku:
        raise GateRefused(f"offer.json sku {offer.get('sku')!r} must equal the folder name {sku!r}.")
    errs = offer_format_errors(offer, creating=True)
    if errs:
        raise GateRefused("offer.json: " + "; ".join(errs))
    warnings = [] if args.skip_validate else run_validator(folder)

    data = client.post(f"{INVENTORY}/offer", strip_private(offer))
    offer_id = data.get("offerId")
    offer["_offerId"] = offer_id
    write_json(path, offer)
    log_call(folder, "create-offer", sku=sku, offerId=offer_id, warnings=data.get("warnings"))
    return {"offerId": offer_id, "status": "UNPUBLISHED", "warnings": data.get("warnings", []),
            "validatorWarnings": warnings}


# updateOffer's body (EbayOfferDetailsWithId) has no sku/marketplaceId/format
UPDATE_EXCLUDED = {"sku", "marketplaceId", "format"}


def cmd_update_offer(client, args):
    folder = listing_dir(args.slug)
    offer = read_json(folder / "offer.json")
    offer_id = args.offer_id or offer.get("_offerId")
    if not offer_id:
        raise GateRefused("No offerId: offer.json has no _offerId and --offer-id was not given.")
    errs = offer_format_errors(offer, creating=False)
    if errs:
        raise GateRefused("offer.json: " + "; ".join(errs))
    warnings = [] if args.skip_validate else run_validator(folder)
    current = client.get(f"{INVENTORY}/offer/{offer_id}")
    if current.get("sku") != folder.name:
        raise GateRefused(f"Offer {offer_id} belongs to SKU {current.get('sku')!r}, not {folder.name!r}.")
    if current.get("status") == "PUBLISHED" and not args.confirm:
        raise GateRefused(f"Offer {offer_id} is PUBLISHED: update-offer revises the live listing. "
                          f"Get the human's approval, then rerun with --confirm.")

    body = {k: v for k, v in strip_private(offer).items() if k not in UPDATE_EXCLUDED}
    data = client.put(f"{INVENTORY}/offer/{offer_id}", body)
    log_call(folder, "update-offer", offerId=offer_id, status=current.get("status"),
             warnings=data.get("warnings"))
    return {"offerId": offer_id, "status": current.get("status"), "updated": True,
            "warnings": data.get("warnings", []), "validatorWarnings": warnings}


def cmd_delete_offer(client, args):
    current = client.get(f"{INVENTORY}/offer/{args.offer_id}")
    status = current.get("status")
    if status != "UNPUBLISHED":
        raise GateRefused(f"Offer {args.offer_id} is {status}; delete-offer only removes UNPUBLISHED offers "
                          f"(on a published offer it would end the live listing).")
    client.delete(f"{INVENTORY}/offer/{args.offer_id}")
    folder = LISTINGS / current.get("sku", "")
    if current.get("sku") and folder.is_dir():
        log_call(folder, "delete-offer", offerId=args.offer_id)
    return {"offerId": args.offer_id, "sku": current.get("sku"), "deleted": True}


def offer_summary(client, offer):
    pricing = offer.get("pricingSummary", {})
    best = (offer.get("listingPolicies") or {}).get("bestOfferTerms") or {}
    summary = {
        "offerId": offer.get("offerId"),
        "sku": offer.get("sku"),
        "status": offer.get("status"),
        "categoryId": offer.get("categoryId"),
        "price": _amount(pricing.get("price")),
        "bestOfferFloor": _amount(best.get("autoDeclinePrice")) if best.get("bestOfferEnabled") else None,
        "policies": {k: v for k, v in (offer.get("listingPolicies") or {}).items() if k.endswith("PolicyId")},
    }
    try:
        item = client.get(f"{INVENTORY}/inventory_item/{urllib.parse.quote(offer.get('sku', ''), safe='')}")
        summary["title"] = (item.get("product") or {}).get("title")
        summary["condition"] = item.get("condition")
        summary["images"] = len((item.get("product") or {}).get("imageUrls") or [])
    except EbayApiError:
        pass
    return summary


def cmd_publish(client, args):
    offer = client.get(f"{INVENTORY}/offer/{args.offer_id}")
    if offer.get("status") != "UNPUBLISHED":
        raise GateRefused(f"Offer {args.offer_id} is {offer.get('status')}, not UNPUBLISHED.")
    summary = offer_summary(client, offer)
    try:
        summary["fees"] = listing_fees(client, args.offer_id)["total"]
    except EbayApiError as exc:  # fees are informational; don't block the preview or the publish
        summary["fees"] = None
        summary["feesError"] = exc.to_dict()
    if not args.confirm:
        print(json.dumps(summary, indent=2), file=sys.stderr)
        raise GateRefused("Not published. Show this summary to the human; after their explicit approval in "
                          "this session, rerun with --confirm.")

    data = client.post(f"{INVENTORY}/offer/{args.offer_id}/publish")
    listing_id = data.get("listingId")
    folder = LISTINGS / offer.get("sku", "")
    if offer.get("sku") and folder.is_dir():
        log_call(folder, "publish", offerId=args.offer_id, listingId=listing_id, warnings=data.get("warnings"))
    return {"offerId": args.offer_id, "listingId": listing_id,
            "url": f"https://www.ebay.com/itm/{listing_id}" if listing_id else None,
            "warnings": data.get("warnings", []), "summary": summary}


# --------------------------------------------------------------------------- re-auth

def cmd_auth_url(client, args):
    cfg = client.config
    if not (cfg["client_id"] and cfg["redirect_uri"]):
        raise SystemExit("Need EBAY_CLIENT_ID and EBAY_REDIRECT_URI (RuName) in .env.")
    scopes = USER_SCOPES + (args.scope or [])
    query = urllib.parse.urlencode({"client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"],
                                    "response_type": "code", "scope": " ".join(scopes)},
                                   quote_via=urllib.parse.quote)
    return {"url": f"{cfg['auth_host']}/oauth2/authorize?{query}",
            "next": "Open the URL, sign in as the seller, accept, then run: "
                    "python tools/ebay_api.py exchange-code \"<redirect URL or code>\""}


def cmd_exchange_code(client, args):
    code = args.code
    if "code=" in code:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
    code = urllib.parse.unquote(code)
    body = client._token_request({"grant_type": "authorization_code", "code": code,
                                  "redirect_uri": client.config["redirect_uri"]})
    if not body.get("refresh_token"):
        raise SystemExit("Token response had no refresh_token.")
    if not args.dry_run:
        set_env_value("EBAY_USER_REFRESH_TOKEN", body["refresh_token"])
        try:
            TOKEN_CACHE.unlink()
        except FileNotFoundError:
            pass
    days = int(body.get("refresh_token_expires_in", 0)) // 86400
    return {"stored": not args.dry_run, "refreshTokenValidDays": days, "env_file": str(ENV_FILE)}


# --------------------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(description="eBay REST API client for the listing pipeline")
    p.add_argument("--env", choices=["production", "sandbox"], help="default: EBAY_ENVIRONMENT or production")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        s.set_defaults(fn=fn)
        return s

    add("policies", cmd_policies, "List fulfillment/payment/return business policies")

    s = add("setup", cmd_setup, "Discover policies + inventory location -> account.json (re-runnable)")
    for kind in POLICY_KEYS:
        s.add_argument(f"--{kind}", metavar="POLICY_ID", help=f"default {kind} policy")
    s.add_argument("--return-14-day", metavar="POLICY_ID", help="14-day return policy (few categories allow it)")
    s.add_argument("--disallow-fulfillment", action="append", metavar="POLICY_ID",
                   help="a fulfillment policy the validator must refuse (repeatable)")
    s.add_argument("--location-key", help="merchantLocationKey to use (or create)")
    s.add_argument("--create-location", action="store_true", help="create --location-key (needs --confirm)")
    s.add_argument("--postal-code")
    s.add_argument("--country", default="US")
    s.add_argument("--city")
    s.add_argument("--state")
    s.add_argument("--opt-in", action="store_true", help="enroll in Business Policies (needs --confirm)")
    s.add_argument("--confirm", action="store_true", help="allow the account change (human-approved)")
    s.add_argument("--dry-run", action="store_true", help="show the result, don't write account.json")

    s = add("categories", cmd_categories, "Category suggestions for a query")
    s.add_argument("query")
    s.add_argument("--raw", action="store_true")

    s = add("aspects", cmd_aspects, "Item specifics for a category (required first)")
    s.add_argument("category_id")
    s.add_argument("--required", action="store_true", help="only required aspects")
    s.add_argument("--max-values", type=int, default=25)
    s.add_argument("--raw", action="store_true")

    s = add("condition-policies", cmd_condition_policies, "Condition IDs a category accepts")
    s.add_argument("category_id")
    s.add_argument("--raw", action="store_true")

    s = add("return-policies", cmd_return_policies, "Return windows/payers a category allows")
    s.add_argument("category_id")
    s.add_argument("--raw", action="store_true")

    s = add("browse", cmd_browse, "Active listings (price ceiling only)")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--condition", choices=["NEW", "USED", "new", "used"])
    s.add_argument("--buy-it-now", action="store_true")
    s.add_argument("--raw", action="store_true")

    s = add("get-item", cmd_get_item, "Get an inventory item by SKU")
    s.add_argument("sku")
    s = add("get-offer", cmd_get_offer, "Get an offer by ID")
    s.add_argument("offer_id")
    s = add("offers", cmd_offers, "List offers for a SKU")
    s.add_argument("--sku", required=True)
    s = add("reconcile", cmd_reconcile, "Live status of every listing folder (ACTIVE/SOLD/ENDED/...)")
    s.add_argument("slug", nargs="*", help="only these folders (default: all)")
    s.add_argument("--archive", action="store_true",
                   help="move SOLD folders to listings/archive/ and stamp their listing-draft.md")
    s.add_argument("--root", help="listings folder (default: listings/ in the repo)")
    s = add("fees", cmd_fees, "Listing fees for an unpublished offer")
    s.add_argument("offer_id")

    s = add("upload-images", cmd_upload_images, "Upload {slug}-NN images to EPS -> image-urls.json")
    s.add_argument("slug")
    s.add_argument("--replace", action="store_true", help="overwrite image-urls.json instead of appending")
    s.add_argument("--files", nargs="+", help="upload these files instead of all {slug}-NN images")

    for name, fn, help_ in [("put-item", cmd_put_item, "createOrReplaceInventoryItem from inventory-item.json"),
                            ("create-offer", cmd_create_offer, "createOffer from offer.json (unpublished)"),
                            ("update-offer", cmd_update_offer, "updateOffer (full replace) from offer.json")]:
        s = add(name, fn, help_)
        s.add_argument("slug")
        s.add_argument("--skip-validate", action="store_true", help="debug only: skip validate_payload.py")
        if name != "create-offer":
            s.add_argument("--confirm", action="store_true", help="allow changing a LIVE listing (human-approved)")
        if name == "update-offer":
            s.add_argument("--offer-id", help="default: _offerId in offer.json")

    s = add("delete-offer", cmd_delete_offer, "Delete an UNPUBLISHED offer")
    s.add_argument("offer_id")

    s = add("publish", cmd_publish, "Publish an offer (preview without --confirm)")
    s.add_argument("offer_id")
    s.add_argument("--confirm", action="store_true", help="publish; only after explicit human approval")

    s = add("auth-url", cmd_auth_url, "Print the seller consent URL (re-auth)")
    s.add_argument("--scope", action="append", help="extra scope URL(s)")
    s = add("exchange-code", cmd_exchange_code, "Exchange a consent code for a refresh token -> .env")
    s.add_argument("code", help="the code, or the whole redirect URL")
    s.add_argument("--dry-run", action="store_true", help="don't write .env")
    return p


def main(argv=None, client=None):
    args = build_parser().parse_args(argv)
    client = client or EbayClient(load_config(args.env))
    try:
        result = args.fn(client, args)
    except GateRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    except EbayApiError as e:
        print(json.dumps({"error": e.to_dict()}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    if result is not None:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
