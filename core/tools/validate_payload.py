"""
Pre-publish validation for eBay listing payloads.
Validates evaluator output (and, for a listing folder, image-urls.json,
listing-draft.md and the request bodies inventory-item.json / offer.json that
tools/ebay_api.py sends) against the schema contract and eBay requirements
before calling the API.

Usage:
    python tools/validate_payload.py listings/{slug}/
    python tools/validate_payload.py path/to/evaluator-output.json
    python tools/validate_payload.py listings/*/ --json      # machine-readable result

Exit code: 0 when there are no errors (warnings allowed), 1 otherwise.

Requirements:
    pip install jsonschema     # optional; schema check is skipped without it
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from account_config import account_problems, load_account, pipeline_value  # noqa: E402

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "evaluator-output.json"

# Inventory API ConditionEnum -> numeric condition ID
CONDITION_IDS = {
    "NEW": 1000,
    "NEW_OTHER": 1500,
    "NEW_WITH_DEFECTS": 1750,
    "CERTIFIED_REFURBISHED": 2000,
    "EXCELLENT_REFURBISHED": 2010,
    "VERY_GOOD_REFURBISHED": 2020,
    "GOOD_REFURBISHED": 2030,
    "SELLER_REFURBISHED": 2500,
    "LIKE_NEW": 2750,
    "PRE_OWNED_EXCELLENT": 2990,
    "USED_EXCELLENT": 3000,
    "PRE_OWNED_FAIR": 3010,
    "USED_VERY_GOOD": 4000,
    "USED_GOOD": 5000,
    "USED_ACCEPTABLE": 6000,
    "FOR_PARTS_OR_NOT_WORKING": 7000,
}
VALID_CONDITION_IDS = set(CONDITION_IDS.values())

PHOTOS_ONLY_DISCLAIMER = "condition assessed from photos only"
# Thresholds come from account.json "pipeline" (defaults in account_config.DEFAULT_PIPELINE)

# Cassini / eBay keyword-spam penalties. Word boundaries so "WOWtech" or
# "Rarely" don't trip them.
SPAM_PATTERNS = [
    r"L@@K", r"\bWOW\b", r"\bRARE\b!*", r"\bAMAZING\b", r"\bMUST SEE\b",
    r"\bFREE SHIPPING\b", r"(?<![\w-])NR(?![\w-])",r"\*{2,}", r"!{2,}", r"#{2,}",
]

# Tags and attributes eBay strips or rejects in descriptions
FORBIDDEN_HTML = [
    (r"<script\b", "<script>"),
    (r"<iframe\b", "<iframe>"),
    (r"<form\b", "<form>"),
    (r"<object\b", "<object>"),
    (r"<embed\b", "<embed>"),
    (r"javascript:", "javascript: URL"),
    (r"\son\w+\s*=", "inline event handler (onclick=...)"),
]

# Functional claims the pipeline cannot make from photos alone
TESTED_CLAIM = re.compile(r"\b(tested|fully functional|confirmed working|works perfectly|working condition)\b",
                          re.IGNORECASE)
# Words just before a claim that turn it into a disclaimer ("not bench-tested", "untested")
NEGATION = re.compile(r"\b(not|never|un|without being)[\s-]*(\w+[\s-]+)?$", re.IGNORECASE)


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_title(title: str, r: Report, known_terms: set[str] = frozenset()):
    if not title:
        r.error("Title is empty")
        return
    if len(title) > 80:
        r.error(f"Title exceeds 80 chars ({len(title)})")
    if title != title.strip():
        r.error("Title has leading/trailing whitespace")
    for pat in SPAM_PATTERNS:
        if re.search(pat, title, re.IGNORECASE):
            r.error(f"Title contains spam pattern: {pat}")
    # Shouting words. Short tokens and anything with a digit (USB, GPS, R8000,
    # XM5) are model numbers or acronyms, not shouting.
    caps = [w for w in title.split()
            if len(w) >= 5 and w.isalpha() and w.isupper() and w.lower() not in known_terms]
    if caps:
        r.warn(f"Title has ALL-CAPS words (Cassini may penalize): {caps}")


def validate_identification(ident: dict, r: Report, known_terms: set[str] = frozenset()):
    if not ident.get("category_id"):
        r.error("Missing category_id")
    if not ident.get("brand"):
        r.error("Missing brand (use 'Unbranded' only when the item truly has none)")
    if not ident.get("upc"):
        r.error("Missing UPC (use 'Does Not Apply' if none)")
    validate_title(ident.get("title", ""), r, known_terms)


def validate_pricing(pricing: dict, r: Report):
    rec = pricing.get("recommended_price")
    if not is_number(rec) or rec <= 0:
        r.error(f"Invalid recommended_price: {rec!r}")
        return

    min_p, max_p = pricing.get("min_price"), pricing.get("max_price")
    if is_number(min_p) and rec < min_p:
        r.error(f"recommended_price {rec} below min_price {min_p}")
    if is_number(max_p) and rec > max_p:
        r.error(f"recommended_price {rec} above max_price {max_p}")

    auto_decline = pricing.get("auto_decline_below")
    if auto_decline is not None:
        if not is_number(auto_decline):
            r.error(f"Invalid auto_decline_below: {auto_decline!r}")
        elif auto_decline >= rec:
            r.error(f"auto_decline_below ({auto_decline}) >= recommended_price ({rec})")
        elif not pricing.get("best_offer_enabled"):
            r.warn("auto_decline_below is set but best_offer_enabled is false")

    conf = pricing.get("confidence")
    min_conf = pipeline_value("min_confidence")
    if is_number(conf) and conf < min_conf:
        r.warn(f"Pricing confidence {conf} < {min_conf} -- ask the user before listing")


def validate_condition(cond: dict, r: Report):
    grade = cond.get("final_grade") or cond.get("grade")
    cid = cond.get("condition_id")
    if not grade:
        r.error("Missing condition final_grade")
    elif grade not in CONDITION_IDS:
        r.error(f"final_grade '{grade}' is not an Inventory API ConditionEnum value")
    if cid is not None and cid not in VALID_CONDITION_IDS:
        r.error(f"Unknown condition_id: {cid}")
    if grade in CONDITION_IDS and cid is not None and CONDITION_IDS[grade] != cid:
        r.error(f"final_grade {grade} is condition_id {CONDITION_IDS[grade]}, not {cid}")

    desc = cond.get("condition_description") or cond.get("notes") or ""
    if cid != 1000 and not desc:
        r.error("Missing condition_description (required for anything but NEW)")
    if cond.get("changed_from_curator"):
        r.warn("Evaluator changed the Curator's condition grade -- requires human review")


def validate_listing_specs(specs: dict, r: Report):
    html = specs.get("description_html", "")
    if not html:
        r.error("Missing listing description HTML")
    check_html(html, r, "Description")

    specifics = specs.get("item_specifics") or {}
    if not specifics:
        r.error("No item specifics provided")
    elif not any(k.lower() == "brand" for k in specifics):
        r.warn("item_specifics has no Brand")


def check_disclosure_text(text: str, tested: bool, r: Report, where: str = "Text"):
    """Photo-only grading must say so, and must not claim testing nobody did."""
    if tested:
        return
    if PHOTOS_ONLY_DISCLAIMER not in text.lower():
        r.error(f"{where}: missing 'Condition assessed from photos only' disclaimer")
    for m in TESTED_CLAIM.finditer(text):
        if NEGATION.search(text[max(0, m.start() - 25):m.start()]):
            continue
        r.error(f"{where} claims '{m.group(0)}' but condition.tested_by_human is not true "
                f"-- confirm with the seller or remove the claim")
        break


def check_html(html: str, r: Report, where: str):
    for pat, label in FORBIDDEN_HTML:
        if re.search(pat, html, re.IGNORECASE):
            r.error(f"{where} contains {label} (eBay will reject or strip it)")


def validate_disclosures(data: dict, r: Report):
    cond = data.get("condition", {})
    if cond.get("condition_id") == 1000:
        return
    text = " ".join([
        cond.get("condition_description") or "",
        data.get("listing_specs", {}).get("description_html") or "",
    ])
    check_disclosure_text(text, cond.get("tested_by_human") is True, r)


def validate_schema(data: dict, r: Report):
    try:
        import jsonschema
    except ImportError:
        r.warn("jsonschema not installed -- skipped schema validation (pip install jsonschema)")
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8-sig"))
    validator = jsonschema.Draft7Validator(schema)
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in err.path) or "(root)"
        r.error(f"Schema: {where}: {err.message}")


def validate_evaluator_output(data: dict) -> Report:
    r = Report()
    validate_schema(data, r)

    # Brand/model words may legitimately be in caps (XREAL, TBECA)
    ident = data.get("identification") or {}
    specifics = (data.get("listing_specs") or {}).get("item_specifics") or {}
    known_terms = {
        w.lower()
        for v in [ident.get("brand"), ident.get("model"), *specifics.values()]
        for item in (v if isinstance(v, list) else [v]) if isinstance(item, str)
        for w in item.split()
    }

    sections = {
        "identification": validate_identification,
        "pricing": validate_pricing,
        "condition": validate_condition,
        "listing_specs": validate_listing_specs,
    }
    for key, fn in sections.items():
        if not isinstance(data.get(key), dict):
            r.error(f"Missing '{key}' section")
        elif key == "identification":
            fn(data[key], r, known_terms)
        else:
            fn(data[key], r)
    validate_disclosures(data, r)

    count = data.get("comps", {}).get("count", 0)
    if not is_number(count) or count < 5:
        r.warn(f"Only {count} sold comps found -- low confidence pricing")

    approval = data.get("approval", {})
    reasons = approval.get("review_reasons", [])
    if approval.get("requires_human_review"):
        r.warn(f"Human review required: {', '.join(reasons) or '(no reason given)'}")
    rec = data.get("pricing", {}).get("recommended_price")
    gate = pipeline_value("price_review_threshold")
    if is_number(rec) and rec > gate and not approval.get("requires_human_review"):
        r.error(f"Price ${rec} > ${gate} but approval.requires_human_review is false")
    return r


def validate_image_urls(path: Path, r: Report):
    if not path.exists():
        r.warn("No image-urls.json -- images not uploaded yet")
        return
    try:
        urls = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        r.error(f"image-urls.json is not valid JSON: {e}")
        return
    if path.read_bytes()[:3] == b"\xef\xbb\xbf":
        r.warn("image-urls.json has a UTF-8 BOM (some JSON readers reject it)")
    if isinstance(urls, dict):
        r.warn("image-urls.json is a {name: url} map; the upload tool now writes a plain array")
        urls = list(urls.values())
    if isinstance(urls, str):
        r.error("image-urls.json is a bare string, not an array (PowerShell 5.1 single-item bug)")
        return
    if not isinstance(urls, list) or not urls:
        r.error("image-urls.json must be a non-empty array of URLs")
        return
    if len(urls) > 24:
        r.error(f"image-urls.json has {len(urls)} URLs; eBay allows 24")
    bad = [u for u in urls if not isinstance(u, str) or not u.startswith("https://") or " " in u]
    if bad:
        r.error(f"image-urls.json has {len(bad)} malformed URL(s), e.g. {str(bad[0])[:80]}")
    if len(set(urls)) != len(urls):
        r.warn("image-urls.json contains duplicate URLs")


def validate_listing_draft(path: Path, r: Report):
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8-sig")
    if "System.Collections" in text or "$(" in text:
        r.error("listing-draft.md has unexpanded PowerShell placeholders ($(...) / System.Collections...)")




def _price(amount) -> float | None:
    try:
        return float(amount["value"])
    except (TypeError, KeyError, ValueError):
        return None


def validate_inventory_item(item: dict, tested: bool, r: Report):
    product = item.get("product") or {}
    brand_words = {w.lower() for v in (product.get("aspects") or {}).values()
                   for x in (v if isinstance(v, list) else [v]) if isinstance(x, str) for w in x.split()}
    validate_title(product.get("title", ""), r, brand_words)
    if "packageWeightAndSize" in item:
        r.error("inventory-item.json: remove packageWeightAndSize (causes 'Invalid ShippingPackage' "
                "with the flat-rate shipping policy)")
    cond = item.get("condition")
    if cond not in CONDITION_IDS:
        r.error(f"inventory-item.json: condition {cond!r} is not an Inventory API ConditionEnum value")
    aspects = product.get("aspects") or {}
    if not aspects:
        r.error("inventory-item.json: product.aspects (item specifics) is empty")
    elif not any(k.lower() == "brand" for k in aspects):
        r.error("inventory-item.json: product.aspects has no Brand")
    if any(not isinstance(v, list) for v in aspects.values()):
        r.error("inventory-item.json: every product.aspects value must be a list of strings")
    qty = ((item.get("availability") or {}).get("shipToLocationAvailability") or {}).get("quantity")
    if not is_number(qty) or qty < 1:
        r.error("inventory-item.json: availability.shipToLocationAvailability.quantity must be >= 1")
    html = product.get("description") or ""
    check_html(html, r, "inventory-item.json product.description")
    if cond != "NEW":
        if not item.get("conditionDescription"):
            r.error("inventory-item.json: conditionDescription is required for anything but NEW")
        check_disclosure_text(" ".join([html, item.get("conditionDescription") or ""]), tested, r,
                              "inventory-item.json")


def validate_offer(offer: dict, slug: str, evaluator: dict, tested: bool, used: bool, r: Report):
    if offer.get("sku") != slug:
        r.error(f"offer.json: sku {offer.get('sku')!r} must equal the folder name {slug!r}")
    account = load_account()
    seller = (account or {}).get("seller", {})
    policies = (account or {}).get("policies", {})
    for problem in account_problems(account):
        r.error(f"account: {problem} (needed to check offer.json policies and location)")
    marketplace = seller.get("marketplace", "EBAY_US")
    if offer.get("marketplaceId") != marketplace:
        r.error(f"offer.json: marketplaceId must be {marketplace} (got {offer.get('marketplaceId')!r})")
    if not offer.get("categoryId"):
        r.error("offer.json: categoryId missing")
    location = seller.get("merchantLocationKey")
    if not offer.get("merchantLocationKey"):
        r.error(f"offer.json: merchantLocationKey missing (use {location or 'seller.merchantLocationKey from account.json'})")
    elif location and offer["merchantLocationKey"] != location:
        r.warn(f"offer.json: merchantLocationKey {offer['merchantLocationKey']} is not the account default {location}")

    pol = offer.get("listingPolicies") or {}
    ful, pay, ret = pol.get("fulfillmentPolicyId"), pol.get("paymentPolicyId"), pol.get("returnPolicyId")
    if not (ful and pay and ret):
        r.error("offer.json: listingPolicies needs fulfillmentPolicyId, paymentPolicyId and returnPolicyId")
    ful_default, ret_default = policies.get("fulfillment"), policies.get("return")
    if ful and ful in set(policies.get("disallowed_fulfillment") or []):
        r.error(f"offer.json: fulfillment policy {ful} is listed in account.json disallowed_fulfillment; "
                f"use {ful_default}")
    elif ful and ful_default and ful != ful_default:
        r.warn(f"offer.json: fulfillment policy {ful} is not the account default {ful_default}")
    if pay and policies.get("payment") and pay != policies["payment"]:
        r.warn(f"offer.json: payment policy {pay} is not the account default {policies['payment']}")
    if ret and ret == policies.get("return_14_day"):
        r.warn("offer.json: 14-day return policy -- confirm with `ebay_api.py return-policies <categoryId>` "
               "that the category allows 14 days")
    elif ret and ret_default and ret != ret_default:
        r.warn(f"offer.json: return policy {ret} is not the account default {ret_default}")

    price = _price((offer.get("pricingSummary") or {}).get("price"))
    if offer.get("format", "FIXED_PRICE") == "FIXED_PRICE":
        if price is None or price <= 0:
            r.error("offer.json: pricingSummary.price.value must be a number > 0")
        rec = (evaluator.get("pricing") or {}).get("recommended_price")
        if price is not None and is_number(rec) and abs(price - rec) > 0.005:
            r.warn(f"offer.json price {price} differs from evaluator recommended_price {rec}")
    best = pol.get("bestOfferTerms") or {}
    floor = _price(best.get("autoDeclinePrice"))
    if best.get("bestOfferEnabled") and floor is not None and price is not None and floor >= price:
        r.error(f"offer.json: autoDeclinePrice {floor} must be below the price {price}")

    html = offer.get("listingDescription") or ""
    check_html(html, r, "offer.json listingDescription")
    if html and used:
        check_disclosure_text(html, tested, r, "offer.json listingDescription")


def validate_api_payloads(folder: Path, evaluator: dict, r: Report):
    """Check the request bodies tools/ebay_api.py sends, when the Lister has written them."""
    cond = evaluator.get("condition") or {}
    tested = cond.get("tested_by_human") is True

    def load(name):
        path = folder / name
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            r.error(f"{name} is not valid JSON: {e}")
            return None
        if not isinstance(data, dict):
            r.error(f"{name} must be a JSON object")
            return None
        return data

    item, offer = load("inventory-item.json"), load("offer.json")
    if item is not None:
        validate_inventory_item(item, tested, r)
    if offer is not None:
        used = (item.get("condition") != "NEW") if item else cond.get("condition_id") != 1000
        validate_offer(offer, folder.name, evaluator, tested, used, r)


def validate_target(target: Path) -> tuple[Path, Report]:
    json_file = target / "evaluator-output.json" if target.is_dir() else target
    if not json_file.exists():
        r = Report()
        r.error(f"No evaluator-output.json found in {target}")
        return json_file, r
    try:
        data = json.loads(json_file.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        r = Report()
        r.error(f"{json_file.name} is not valid JSON: {e}")
        return json_file, r

    r = validate_evaluator_output(data)
    if target.is_dir():
        validate_image_urls(target / "image-urls.json", r)
        validate_listing_draft(target / "listing-draft.md", r)
        validate_api_payloads(target.resolve(), data, r)
    return json_file, r


def main():
    parser = argparse.ArgumentParser(description="Pre-publish validation for eBay listing payloads")
    parser.add_argument("targets", nargs="+",
                        help="Listing folder(s) or evaluator-output.json file(s); globs like listings/*/ are expanded")
    parser.add_argument("--json", action="store_true", help="Print results as JSON")
    args = parser.parse_args()

    # PowerShell and cmd don't expand globs; do it here. Folders a glob matches
    # that aren't listings (e.g. listings/archive/) are skipped.
    targets = []
    for t in args.targets:
        if any(c in t for c in "*?["):
            targets += [p for p in sorted(Path().glob(t.rstrip("/\\")))
                        if (p.is_file() and p.suffix == ".json")
                        or (p / "evaluator-output.json").exists()]
        else:
            targets.append(Path(t))
    if not targets:
        parser.error("no listing folders matched")

    results = [validate_target(t) for t in targets]
    failed = any(r.errors for _, r in results)

    if args.json:
        print(json.dumps([{
            "file": str(f), "valid": not r.errors,
            "errors": r.errors, "warnings": r.warnings,
        } for f, r in results], indent=2))
        sys.exit(1 if failed else 0)

    for f, r in results:
        if len(results) > 1:
            print(f"\n=== {f.parent.name if f.name == 'evaluator-output.json' else f} ===")
        if r.errors:
            print(f"\nERRORS ({len(r.errors)}):")
            for e in r.errors:
                print(f"  x {e}")
        if r.warnings:
            print(f"\nWARNINGS ({len(r.warnings)}):")
            for w in r.warnings:
                print(f"  ! {w}")
        print("\nVALIDATION FAILED - fix errors before listing" if r.errors
              else "\nVALIDATION PASSED - ready for listing draft")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
