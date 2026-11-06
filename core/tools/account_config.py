"""
Seller account settings shared by ebay_api.py and validate_payload.py.

The values that differ per seller live in account.json at the repo root, which is
gitignored. They are the business policy IDs, the inventory location and the
pipeline thresholds. `python tools/ebay_api.py setup` writes the file from the live
account; account.example.json shows its shape.

EBAY_ACCOUNT_FILE overrides the path (tests, or a second account).

EBAY_WORKSPACE moves all private data (.env, account.json, the token cache,
listings/ and raw_data/) to another folder, so the code can stay in a clean
checkout. Without it, the workspace is the repo root.
"""

import json
import os
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent


def workspace_root():
    """Folder holding .env, account.json, listings/ and raw_data/ (EBAY_WORKSPACE, else the repo root)."""
    ws = os.environ.get("EBAY_WORKSPACE")
    if not ws:
        return CODE_ROOT
    path = Path(ws).expanduser().resolve()
    if not path.is_dir():
        raise SystemExit(f"EBAY_WORKSPACE={ws} is not a folder")
    return path


ROOT = workspace_root()
DEFAULT_ACCOUNT_FILE = ROOT / "account.json"

# Fail-safe defaults; ADOPTION-QUESTIONS.md explains each one
DEFAULT_PIPELINE = {
    "price_review_threshold": 200,      # USD; above this a human must review
    "min_confidence": 0.70,             # below this on any metric, ask first
    "shipping_model": "free_baked_in",  # free shipping, cost added to the price
    "fvf_rate": 0.136,                  # final value fee, most categories, no store
    "per_order_fee": 0.40,
    "return_days_default": 30,
}

POLICY_KEYS = ("fulfillment", "payment", "return")


def account_path():
    return Path(os.environ.get("EBAY_ACCOUNT_FILE") or DEFAULT_ACCOUNT_FILE)


def load_account(path=None):
    """Return the account dict with pipeline defaults filled in, or None if the file is missing."""
    path = Path(path) if path else account_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        raise SystemExit(f"{path} is not valid JSON: {e}")
    data.setdefault("seller", {})
    data.setdefault("policies", {})
    data["pipeline"] = {**DEFAULT_PIPELINE, **(data.get("pipeline") or {})}
    return data


def account_problems(account):
    """What is missing before offers can be created (empty list = ready)."""
    if account is None:
        return [f"{account_path().name} not found: run `python tools/ebay_api.py setup`"]
    problems = [f"policies.{k} missing" for k in POLICY_KEYS if not account["policies"].get(k)]
    if not account["seller"].get("merchantLocationKey"):
        problems.append("seller.merchantLocationKey missing")
    return problems


def pipeline_value(key, account=None):
    account = load_account() if account is None else account
    return (account or {}).get("pipeline", DEFAULT_PIPELINE).get(key, DEFAULT_PIPELINE[key])

