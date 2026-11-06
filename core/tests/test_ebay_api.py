"""Unit tests for tools/ebay_api.py (no network: a fake requests session)."""

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ebay_api  # noqa: E402
import validate_payload  # noqa: E402


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.content = b"" if body is None else json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


class FakeSession:
    """Routes (method, path-substring) to a queue of responses; records every call."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/identity/v1/oauth2/token"):
            return FakeResponse(200, {"access_token": f"tok{len(self.calls)}", "expires_in": 7200})
        target = url + ("?" + urlencode(kwargs["params"]) if kwargs.get("params") else "")
        for (m, needle), queue in self.routes.items():
            if m == method and needle in target:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"unexpected call {method} {url}")

    def api_calls(self, method=None):
        return [c for c in self.calls if "/oauth2/token" not in c[1] and (method is None or c[0] == method)]

    def token_calls(self):
        return [parse_qs(c[2]["data"] if isinstance(c[2]["data"], str) else
                         "&".join(f"{k}={v}" for k, v in c[2]["data"].items()))
                for c in self.calls if "/oauth2/token" in c[1]]


CONFIG = {
    "environment": "production", "client_id": "cid123456", "client_secret": "secret",
    "refresh_token": "refresh", "redirect_uri": "RuName", "marketplace": "EBAY_US", "language": "en-US",
    "api_host": "https://api.ebay.com", "media_host": "https://apim.ebay.com", "auth_host": "https://auth.ebay.com",
}


def make_client(tmp_path, routes=None):
    session = FakeSession(routes)
    sleeps = []
    client = ebay_api.EbayClient(dict(CONFIG), session=session, cache_path=tmp_path / "cache.json",
                                 sleep=sleeps.append)
    return client, session, sleeps


def run(client, *argv):
    return ebay_api.main(list(argv), client=client)


# Dummy seller settings; the real account.json is never read by tests
ACCOUNT = {
    "seller": {"marketplace": "EBAY_US", "merchantLocationKey": "EXAMPLE-LOC-01", "postalCode": "00000",
               "country": "US"},
    "policies": {"fulfillment": "100000000001", "payment": "100000000002", "return": "100000000003",
                 "return_14_day": "100000000004", "disallowed_fulfillment": ["100000000005"]},
}


@pytest.fixture(autouse=True)
def account_file(tmp_path, monkeypatch):
    path = tmp_path / "account.json"
    path.write_text(json.dumps(ACCOUNT))
    monkeypatch.setenv("EBAY_ACCOUNT_FILE", str(path))
    return path


# --------------------------------------------------------------------------- transport


def test_default_headers_include_language_and_marketplace(tmp_path):
    client, session, _ = make_client(tmp_path, {("GET", "/offer/1"): [FakeResponse(200, {"offerId": "1"})]})
    client.get("/sell/inventory/v1/offer/1")
    headers = session.api_calls()[0][2]["headers"]
    assert headers["Accept-Language"] == "en-US"  # missing -> error 25709
    assert headers["Content-Language"] == "en-US"
    assert headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
    assert headers["Authorization"].startswith("Bearer ")


def test_user_token_refresh_sends_no_scope_and_is_cached(tmp_path):
    client, session, _ = make_client(tmp_path, {("GET", "/offer/1"): [FakeResponse(200, {})]})
    client.get("/sell/inventory/v1/offer/1")
    client.get("/sell/inventory/v1/offer/1")
    tokens = session.token_calls()
    assert len(tokens) == 1
    assert tokens[0]["grant_type"] == ["refresh_token"]
    assert "scope" not in tokens[0]


def test_401_refreshes_once_then_succeeds(tmp_path):
    client, session, _ = make_client(tmp_path, {("GET", "/offer/1"): [
        FakeResponse(401, {"errors": [{"errorId": 1001}]}), FakeResponse(200, {"ok": True})]})
    assert client.get("/sell/inventory/v1/offer/1") == {"ok": True}
    assert len(session.token_calls()) == 2  # initial + forced refresh
    assert len(session.api_calls()) == 2


def test_second_401_raises(tmp_path):
    client, session, _ = make_client(tmp_path, {("GET", "/offer/1"): [FakeResponse(401, {"errors": []})]})
    with pytest.raises(ebay_api.EbayApiError) as e:
        client.get("/sell/inventory/v1/offer/1")
    assert e.value.status == 401
    assert len(session.api_calls()) == 2


def test_5xx_retries_with_backoff_then_raises(tmp_path):
    client, session, sleeps = make_client(tmp_path, {("GET", "/offer/1"): [FakeResponse(503, {})]})
    with pytest.raises(ebay_api.EbayApiError):
        client.get("/sell/inventory/v1/offer/1")
    assert len(session.api_calls()) == 4
    assert sleeps == [1, 2, 4]


def test_429_fails_immediately_with_retry_after(tmp_path):
    client, session, _ = make_client(tmp_path, {("GET", "/offer/1"): [
        FakeResponse(429, {"errors": []}, {"Retry-After": "30"})]})
    with pytest.raises(ebay_api.EbayApiError) as e:
        client.get("/sell/inventory/v1/offer/1")
    assert "retry after 30" in e.value.body["rate_limited"]
    assert len(session.api_calls()) == 1


def test_browse_uses_application_token(tmp_path, capsys):
    client, session, _ = make_client(tmp_path, {("GET", "/item_summary/search"): [FakeResponse(200, {
        "total": 1, "itemSummaries": [{"title": "x", "price": {"value": "10.00"},
                                        "shippingOptions": [{"shippingCost": {"value": "5.00"}}]}]})]})
    assert run(client, "browse", "thing", "--condition", "used") == 0
    assert session.token_calls()[0]["grant_type"] == ["client_credentials"]
    assert session.api_calls()[0][2]["params"]["filter"] == "conditions:{USED}"
    out = json.loads(capsys.readouterr().out)
    assert out["items"][0]["total"] == 15.0


def test_error_output_includes_hint(tmp_path, capsys):
    client, _, _ = make_client(tmp_path, {("GET", "/offer/1"): [
        FakeResponse(400, {"errors": [{"errorId": 25709, "message": "Invalid value for header"}]})]})
    assert run(client, "get-offer", "1") == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"]["status"] == 400
    assert "Content-Language" in err["error"]["hints"][0]


# --------------------------------------------------------------------------- config


def test_environment_variable_overrides_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("EBAY_CLIENT_ID=from-file\nEBAY_ENVIRONMENT=\"sandbox\"\n# comment\n")
    monkeypatch.setenv("EBAY_CLIENT_ID", "from-env")
    monkeypatch.delenv("EBAY_ENVIRONMENT", raising=False)
    cfg = ebay_api.load_config(env_file=env_file)
    assert cfg["client_id"] == "from-env"
    assert cfg["environment"] == "sandbox"
    assert cfg["api_host"] == "https://api.sandbox.ebay.com"
    assert cfg["media_host"] == "https://apim.sandbox.ebay.com"


def test_set_env_value_replaces_line(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nEBAY_USER_REFRESH_TOKEN=old\nB=2\n")
    ebay_api.set_env_value("EBAY_USER_REFRESH_TOKEN", "new", env_file)
    assert env_file.read_text() == "A=1\nEBAY_USER_REFRESH_TOKEN=new\nB=2\n"


# --------------------------------------------------------------------------- gates


def offer(status, sku="test-sku-xyz"):
    return FakeResponse(200, {"offerId": "9", "sku": sku, "status": status,
                              "pricingSummary": {"price": {"value": "50.0"}}})


def test_publish_without_confirm_is_preview_only(tmp_path, capsys):
    client, session, _ = make_client(tmp_path, {
        ("GET", "/offer/9"): [offer("UNPUBLISHED")],
        ("GET", "/inventory_item/"): [FakeResponse(200, {"product": {"title": "T", "imageUrls": ["u"]}})],
        ("POST", "/get_listing_fees"): [FakeResponse(200, {"feeSummaries": []})],
    })
    assert run(client, "publish", "9") == 2
    assert not [c for c in session.api_calls("POST") if c[1].endswith("/publish")]
    assert "REFUSED" in capsys.readouterr().err


def test_publish_refuses_published_offer(tmp_path):
    client, session, _ = make_client(tmp_path, {("GET", "/offer/9"): [offer("PUBLISHED")]})
    assert run(client, "publish", "9", "--confirm") == 2
    assert not session.api_calls("POST")


def test_publish_with_confirm(tmp_path, capsys):
    client, session, _ = make_client(tmp_path, {
        ("GET", "/offer/9"): [offer("UNPUBLISHED")],
        ("GET", "/inventory_item/"): [FakeResponse(200, {"product": {}})],
        ("POST", "/get_listing_fees"): [FakeResponse(200, {"feeSummaries": [
            {"fees": [{"feeType": "InsertionFee", "amount": {"value": "0.35"}}]}]})],
        ("POST", "/offer/9/publish"): [FakeResponse(200, {"listingId": "123"})],
    })
    assert run(client, "publish", "9", "--confirm") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["url"] == "https://www.ebay.com/itm/123"
    assert out["summary"]["fees"] == 0.35


def test_delete_offer_refuses_published(tmp_path):
    client, session, _ = make_client(tmp_path, {("GET", "/offer/9"): [offer("PUBLISHED")]})
    assert run(client, "delete-offer", "9") == 2
    assert not session.api_calls("DELETE")


def test_delete_offer_unpublished(tmp_path):
    client, session, _ = make_client(tmp_path, {("GET", "/offer/9"): [offer("UNPUBLISHED")],
                                                ("DELETE", "/offer/9"): [FakeResponse(204)]})
    assert run(client, "delete-offer", "9") == 0
    assert len(session.api_calls("DELETE")) == 1


# --------------------------------------------------------------------------- payload commands


def listing(tmp_path, offer_body=None, item_body=None, urls=None):
    folder = tmp_path / "test-sku-xyz"
    folder.mkdir()
    if offer_body is not None:
        (folder / "offer.json").write_text(json.dumps(offer_body))
    if item_body is not None:
        (folder / "inventory-item.json").write_text(json.dumps(item_body))
    if urls is not None:
        (folder / "image-urls.json").write_text(json.dumps(urls))
    return folder


OFFER = {"sku": "test-sku-xyz", "marketplaceId": "EBAY_US", "format": "FIXED_PRICE", "listingDuration": "GTC",
         "categoryId": "1", "pricingSummary": {"price": {"value": "50.00", "currency": "USD"}},
         "listingPolicies": {"bestOfferTerms": {"bestOfferEnabled": True,
                                                "autoDeclinePrice": {"value": "40.00", "currency": "USD"}}},
         "_note": "private"}


def test_create_offer_strips_private_keys_and_records_offer_id(tmp_path):
    folder = listing(tmp_path, OFFER)
    client, session, _ = make_client(tmp_path, {("POST", "/sell/inventory/v1/offer"): [
        FakeResponse(201, {"offerId": "777"})]})
    assert run(client, "create-offer", str(folder), "--skip-validate") == 0
    sent = json.loads(session.api_calls("POST")[0][2]["data"])
    assert "_note" not in sent and sent["sku"] == "test-sku-xyz"
    assert json.loads((folder / "offer.json").read_text())["_offerId"] == "777"
    assert (folder / "api-log.jsonl").exists()
    # a second create is refused
    assert run(client, "create-offer", str(folder), "--skip-validate") == 2


def test_create_offer_runs_validator(tmp_path):
    folder = listing(tmp_path, OFFER)  # no evaluator-output.json -> validator error
    client, session, _ = make_client(tmp_path)
    assert run(client, "create-offer", str(folder)) == 2
    assert not session.api_calls()


def test_create_offer_rejects_bad_floor(tmp_path):
    bad = json.loads(json.dumps(OFFER))
    bad["listingPolicies"]["bestOfferTerms"]["autoDeclinePrice"]["value"] = "60.00"
    folder = listing(tmp_path, bad)
    client, session, _ = make_client(tmp_path)
    assert run(client, "create-offer", str(folder), "--skip-validate") == 2
    assert not session.api_calls()


def test_update_offer_excludes_create_only_fields_and_gates_live(tmp_path):
    folder = listing(tmp_path, {**OFFER, "_offerId": "9"})
    client, session, _ = make_client(tmp_path, {("GET", "/offer/9"): [offer("PUBLISHED")],
                                                ("PUT", "/offer/9"): [FakeResponse(200, {})]})
    assert run(client, "update-offer", str(folder), "--skip-validate") == 2
    assert not session.api_calls("PUT")
    assert run(client, "update-offer", str(folder), "--skip-validate", "--confirm") == 0
    sent = json.loads(session.api_calls("PUT")[0][2]["data"])
    assert not {"sku", "marketplaceId", "format", "_offerId", "_note"} & sent.keys()


ITEM = {"product": {"title": "Thing", "aspects": {"Brand": ["X"]}}, "condition": "USED_EXCELLENT",
        "availability": {"shipToLocationAvailability": {"quantity": 1}}}


def test_put_item_fills_image_urls_and_gates_live(tmp_path):
    folder = listing(tmp_path, item_body=ITEM, urls=["https://i.ebayimg.com/a", "https://i.ebayimg.com/b"])
    client, session, _ = make_client(tmp_path, {
        ("GET", "/offer"): [FakeResponse(200, {"offers": [{"offerId": "9", "status": "PUBLISHED",
                                                           "listing": {"listingId": "123"}}]})],
        ("PUT", "/inventory_item/test-sku-xyz"): [FakeResponse(204)]})
    assert run(client, "put-item", str(folder), "--skip-validate") == 2
    assert not session.api_calls("PUT")
    assert run(client, "put-item", str(folder), "--skip-validate", "--confirm") == 0
    sent = json.loads(session.api_calls("PUT")[0][2]["data"])
    assert sent["product"]["imageUrls"] == ["https://i.ebayimg.com/a", "https://i.ebayimg.com/b"]


def test_put_item_new_sku_needs_no_confirm(tmp_path):
    folder = listing(tmp_path, item_body=ITEM, urls=["https://i.ebayimg.com/a"])
    client, session, _ = make_client(tmp_path, {
        ("GET", "/offer"): [FakeResponse(404, {"errors": [{"errorId": 25713}]})],
        ("PUT", "/inventory_item/test-sku-xyz"): [FakeResponse(204)]})
    assert run(client, "put-item", str(folder), "--skip-validate") == 0


def test_put_item_refuses_package_weight(tmp_path):
    folder = listing(tmp_path, item_body={**ITEM, "packageWeightAndSize": {}}, urls=["https://i.ebayimg.com/a"])
    client, session, _ = make_client(tmp_path)
    assert run(client, "put-item", str(folder), "--skip-validate") == 2
    assert not session.api_calls()


def test_upload_images_appends_in_order(tmp_path):
    folder = tmp_path / "test-sku-xyz"
    folder.mkdir()
    for n in ("02", "01", "10"):
        (folder / f"test-sku-xyz-{n}.jpg").write_bytes(b"jpg")
    (folder / "other.jpg").write_bytes(b"jpg")
    (folder / "image-urls.json").write_text('["https://i.ebayimg.com/old"]')
    urls = iter(["https://i.ebayimg.com/1", "https://i.ebayimg.com/2", "https://i.ebayimg.com/10"])
    client, session, _ = make_client(tmp_path)

    def request(method, url, **kwargs):
        session.calls.append((method, url, kwargs))
        if url.endswith("/oauth2/token"):
            return FakeResponse(200, {"access_token": "t", "expires_in": 7200})
        assert url == "https://apim.ebay.com/commerce/media/v1_beta/image/create_image_from_file"
        assert "Content-Type" not in kwargs["headers"]  # multipart boundary set by requests
        return FakeResponse(201, {"imageUrl": next(urls)})

    session.request = request
    assert run(client, "upload-images", str(folder)) == 0
    names = [c[2]["files"]["image"][0] for c in session.api_calls()]
    assert names == ["test-sku-xyz-01.jpg", "test-sku-xyz-02.jpg", "test-sku-xyz-10.jpg"]
    assert json.loads((folder / "image-urls.json").read_text()) == [
        "https://i.ebayimg.com/old", "https://i.ebayimg.com/1", "https://i.ebayimg.com/2",
        "https://i.ebayimg.com/10"]


# --------------------------------------------------------------------------- offer format + validator


@pytest.mark.parametrize("change,expect", [
    ({"listingDuration": "DAYS_7"}, "GTC"),
    ({"pricingSummary": {"price": {"value": "10"}, "auctionStartPrice": {"value": "5"}}}, "AUCTION"),
    ({"format": "AUCTION", "listingDuration": "GTC", "pricingSummary": {"auctionStartPrice": {"value": "5"}}},
     "day-count"),
    ({"format": "AUCTION", "listingDuration": "DAYS_7",
      "pricingSummary": {"auctionStartPrice": {"value": "10"}, "price": {"value": "12"}}}, "30%"),
])
def test_offer_format_errors(change, expect):
    body = {**{k: v for k, v in OFFER.items() if k != "listingPolicies"}, **change}
    assert any(expect in e for e in ebay_api.offer_format_errors(body))


def test_offer_format_ok():
    assert ebay_api.offer_format_errors(OFFER) == []


def test_validator_checks_payload_files(tmp_path):
    folder = tmp_path / "test-sku-xyz"
    folder.mkdir()
    (folder / "inventory-item.json").write_text(json.dumps({
        **ITEM, "packageWeightAndSize": {}, "conditionDescription": "Light scuffs.",
        "product": {**ITEM["product"], "description": "<p>Fully tested and working.</p>"}}))
    (folder / "offer.json").write_text(json.dumps({
        **OFFER, "merchantLocationKey": "EXAMPLE-LOC-01", "listingDescription": "<p>Nice</p>",
        "listingPolicies": {**OFFER["listingPolicies"], "fulfillmentPolicyId": "100000000005",
                            "paymentPolicyId": "100000000002", "returnPolicyId": "100000000004"}}))
    r = validate_payload.Report()
    validate_payload.validate_api_payloads(folder, {"condition": {}, "pricing": {"recommended_price": 55}}, r)
    errors, warnings = " | ".join(r.errors), " | ".join(r.warnings)
    assert "packageWeightAndSize" in errors
    assert "claims 'tested'" in errors
    assert "100000000005" in errors  # disallowed fulfillment policy
    assert "offer.json listingDescription: missing" in errors
    assert "14-day" in warnings
    assert "differs from evaluator" in warnings


def _write_offer_folder(tmp_path, **offer_changes):
    folder = tmp_path / "test-sku-xyz"
    folder.mkdir()
    (folder / "inventory-item.json").write_text(json.dumps(ITEM))
    (folder / "offer.json").write_text(json.dumps({
        **OFFER, "merchantLocationKey": "EXAMPLE-LOC-01", "listingDescription": "<p>Nice</p>",
        "listingPolicies": {**OFFER["listingPolicies"], "fulfillmentPolicyId": "100000000001",
                            "paymentPolicyId": "100000000002", "returnPolicyId": "100000000003"},
        **offer_changes}))
    return folder


def test_validator_refuses_offers_without_account_file(tmp_path, account_file):
    account_file.unlink()
    folder = _write_offer_folder(tmp_path)
    r = validate_payload.Report()
    validate_payload.validate_api_payloads(folder, {"condition": {}, "pricing": {"recommended_price": 50}}, r)
    assert any("account.json not found" in e and "setup" in e for e in r.errors)


def test_validator_reads_thresholds_from_account_file(account_file):
    account_file.write_text(json.dumps({**ACCOUNT, "pipeline": {"price_review_threshold": 40}}))
    assert validate_payload.pipeline_value("price_review_threshold") == 40
    assert validate_payload.pipeline_value("min_confidence") == 0.70  # default fills the gap


def test_error_hints_match_25002_by_message_text():
    def hints(message):
        body = {"errors": [{"errorId": 25002, "message": message}]}
        return ebay_api.EbayApiError(400, "POST", "u", body).to_dict().get("hints", [])

    assert any("update-offer" in h for h in hints("Offer entity already exists"))
    sys_hints = hints("A user error has occurred. System error. Unable to process your request.")
    assert any("transient" in h for h in sys_hints)
    assert not any("update-offer" in h for h in sys_hints)


# --------------------------------------------------------------------------- reconcile


def _offers(status, listing_status=None, sold=0, listing_id="111"):
    offer = {"offerId": "9", "sku": "x", "status": status,
             "pricingSummary": {"price": {"value": "19.99", "currency": "USD"}}}
    if listing_status:
        offer["listing"] = {"listingId": listing_id, "listingStatus": listing_status, "soldQuantity": sold}
    return {"offers": [offer], "total": 1}


@pytest.mark.parametrize("offers, expect", [
    (_offers("PUBLISHED", "ACTIVE")["offers"], "ACTIVE"),
    (_offers("UNPUBLISHED", "OUT_OF_STOCK", sold=1)["offers"], "SOLD"),
    (_offers("UNPUBLISHED", "ENDED")["offers"], "ENDED"),
    (_offers("UNPUBLISHED")["offers"], "NEVER_LISTED"),
    ([], "NO_OFFER"),
])
def test_classify_offers(offers, expect):
    assert ebay_api.classify_offers(offers)[0] == expect


def _reconcile_tree(tmp_path):
    root = tmp_path / "listings"
    for d in ["sold-item", "live-item", "archive/old-sold", "archive/never-item"]:
        (root / d).mkdir(parents=True)
    (root / "sold-item" / "listing-draft.md").write_text("﻿# Listing Draft — Sold\n\n## Status: LIVE\n",
                                                          encoding="utf-8")
    routes = {
        ("GET", "sku=sold-item"): [FakeResponse(200, _offers("UNPUBLISHED", "OUT_OF_STOCK", sold=1))],
        ("GET", "sku=live-item"): [FakeResponse(200, _offers("PUBLISHED", "ACTIVE"))],
        ("GET", "sku=old-sold"): [FakeResponse(200, _offers("UNPUBLISHED", "OUT_OF_STOCK", sold=1))],
        ("GET", "sku=never-item"): [FakeResponse(200, _offers("UNPUBLISHED"))],
    }
    return root, routes


def test_reconcile_reports_without_moving(tmp_path, capsys):
    root, routes = _reconcile_tree(tmp_path)
    client, session, _ = make_client(tmp_path, routes)
    assert run(client, "reconcile", "--root", str(root)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"] == {"SOLD": ["sold-item", "old-sold"], "ACTIVE": ["live-item"],
                              "NEVER_LISTED": ["never-item"]}
    assert {i["slug"]: i.get("action") for i in out["items"]}["sold-item"] == "archive"
    assert (root / "sold-item").is_dir()  # read-only without --archive
    assert not session.api_calls("POST") and not session.api_calls("PUT") and not session.api_calls("DELETE")


def test_reconcile_archive_moves_sold_and_stamps(tmp_path, capsys):
    root, routes = _reconcile_tree(tmp_path)
    client, _, _ = make_client(tmp_path, routes)
    assert run(client, "reconcile", "--root", str(root), "--archive") == 0
    assert not (root / "sold-item").exists() and not (root / "live-item" / "listing-draft.md").exists()
    draft = (root / "archive" / "sold-item" / "listing-draft.md").read_text(encoding="utf-8")
    assert draft.startswith("# Listing Draft") and "Reconciled" in draft and ": SOLD**" in draft
    assert "listingId 111" in draft and "## Status: LIVE" in draft
    assert "NEVER_LISTED" in (root / "archive" / "never-item" / "listing-draft.md").read_text(encoding="utf-8")
    # a second run replaces the stamp instead of stacking it
    client, _, _ = make_client(tmp_path, routes)
    run(client, "reconcile", "--root", str(root), "--archive")
    assert (root / "archive" / "sold-item" / "listing-draft.md").read_text(encoding="utf-8").count("reconcile:start") == 1


def test_reconcile_never_overwrites_existing_archive_folder(tmp_path, capsys):
    root, routes = _reconcile_tree(tmp_path)
    (root / "archive" / "sold-item").mkdir()
    client, _, _ = make_client(tmp_path, routes)
    run(client, "reconcile", "--root", str(root), "--archive", "sold-item")
    out = json.loads(capsys.readouterr().out)
    assert out["items"][0]["action"].startswith("NOT moved") and (root / "sold-item").is_dir()


# --------------------------------------------------------------------------- setup


def _policy_routes(fulfillment=("100000000001",), payment=("100000000002",), returns=(("100000000003", 30),),
                   locations=("EXAMPLE-LOC-01",)):
    acct = "/sell/account/v1"
    return {
        ("GET", f"{acct}/fulfillment_policy"): [FakeResponse(200, {"fulfillmentPolicies": [
            {"fulfillmentPolicyId": i, "name": f"ship {i}"} for i in fulfillment]})],
        ("GET", f"{acct}/payment_policy"): [FakeResponse(200, {"paymentPolicies": [
            {"paymentPolicyId": i, "name": f"pay {i}"} for i in payment]})],
        ("GET", f"{acct}/return_policy"): [FakeResponse(200, {"returnPolicies": [
            {"returnPolicyId": i, "name": f"ret {i}", "returnPeriod": {"value": d}} for i, d in returns]})],
        ("GET", "/sell/inventory/v1/location"): [FakeResponse(200, {"locations": [
            {"merchantLocationKey": k, "merchantLocationStatus": "ENABLED",
             "location": {"address": {"postalCode": "00000", "country": "US"}}} for k in locations]})],
    }


def test_setup_writes_account_when_each_choice_is_unique(tmp_path, account_file, capsys):
    account_file.unlink()
    client, session, _ = make_client(tmp_path, _policy_routes(returns=(("100000000003", 30), ("100000000004", 14))))
    assert run(client, "setup") == 0
    written = json.loads(account_file.read_text())
    assert written["policies"]["fulfillment"] == "100000000001"
    assert written["policies"]["return"] == "100000000003"      # the only 30-day policy
    assert written["policies"]["return_14_day"] == "100000000004"
    assert written["seller"] == {"marketplace": "EBAY_US", "merchantLocationKey": "EXAMPLE-LOC-01",
                                 "postalCode": "00000", "country": "US"}
    assert written["pipeline"]["price_review_threshold"] == 200
    assert session.api_calls("POST") == []                       # discovery only, no account changes


def test_setup_does_not_guess_between_several_policies(tmp_path, account_file):
    account_file.unlink()
    client, _, _ = make_client(tmp_path, _policy_routes(fulfillment=("100000000001", "100000000009")))
    assert run(client, "setup", "--dry-run") == 0
    assert not account_file.exists()
    client, _, _ = make_client(tmp_path, _policy_routes(fulfillment=("100000000001", "100000000009")))
    assert run(client, "setup", "--fulfillment", "100000000009") == 0
    assert json.loads(account_file.read_text())["policies"]["fulfillment"] == "100000000009"


def test_setup_keeps_existing_choices_and_rejects_unknown_ids(tmp_path, account_file):
    client, _, _ = make_client(tmp_path, _policy_routes(fulfillment=("100000000001", "100000000005"),
                                                        payment=("100000000002", "100000000008")))
    assert run(client, "setup") == 0
    written = json.loads(account_file.read_text())
    assert written["policies"]["payment"] == "100000000002"     # kept, though 2 exist
    assert written["policies"]["disallowed_fulfillment"] == ["100000000005"]
    client, _, _ = make_client(tmp_path, _policy_routes())
    assert run(client, "setup", "--payment", "999") == 2


def test_setup_account_changes_need_confirm(tmp_path):
    routes = {**_policy_routes(), ("POST", "/sell/account/v1/program/opt_in"): [FakeResponse(200, {})],
              ("POST", "/sell/inventory/v1/location/NEW-LOC"): [FakeResponse(204)]}
    client, session, _ = make_client(tmp_path, routes)
    assert run(client, "setup", "--opt-in") == 2
    assert run(client, "setup", "--create-location", "--location-key", "NEW-LOC", "--postal-code", "00000") == 2
    assert session.api_calls("POST") == []
    assert run(client, "setup", "--opt-in", "--confirm") == 0
    body = json.loads(session.api_calls("POST")[0][2]["data"])
    assert body == {"programType": "SELLING_POLICY_MANAGEMENT"}


def test_workspace_root(monkeypatch, tmp_path):
    import account_config
    monkeypatch.delenv("EBAY_WORKSPACE", raising=False)
    assert account_config.workspace_root() == account_config.CODE_ROOT
    monkeypatch.setenv("EBAY_WORKSPACE", str(tmp_path))
    assert account_config.workspace_root() == tmp_path.resolve()
    monkeypatch.setenv("EBAY_WORKSPACE", str(tmp_path / "missing"))
    with pytest.raises(SystemExit):
        account_config.workspace_root()
