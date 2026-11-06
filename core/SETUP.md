# Setup

How to get this pipeline from a fresh clone to a state where it can create eBay offers. Every step can be re-run.

## 1. Install

Needs Python 3.10+ and ImageMagick 7 (`magick` on PATH; it reads HEIC natively). ffmpeg is optional, only for Live Photo / video frames (see the `process-images` skill).

| OS | ImageMagick 7 | ffmpeg (optional) |
|---|---|---|
| Windows | `winget install ImageMagick.ImageMagick` | `winget install Gyan.FFmpeg` |
| macOS | `brew install imagemagick` | `brew install ffmpeg` |
| Linux | distro packages are often ImageMagick 6; use the AppImage from imagemagick.org | `apt install ffmpeg` (or your distro's) |

```bash
python -m pip install -r requirements.txt
magick -version          # must report 7.x
python -m pytest tests/ -q
```

## 2. API credentials (`.env`)

```bash
cp .env.example .env     # gitignored; never commit it
```

Fill in `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` and `EBAY_REDIRECT_URI` (the RuName) from developer.ebay.com, then get the user refresh token:

```bash
python tools/ebay_api.py auth-url                         # open the URL, sign in as the seller, accept
python tools/ebay_api.py exchange-code "<redirect URL>"   # writes EBAY_USER_REFRESH_TOKEN to .env
```

The `ebay-api` skill (`.agent/skills/ebay-api/SKILL.md`) covers scopes, token lifetimes and errors.

## 3. Seller settings (`account.json`)

The policy IDs and inventory location differ for every seller, so they live in `account.json` (gitignored) rather than in the docs or code. `setup` reads them from the live account:

```bash
python tools/ebay_api.py setup --dry-run     # shows what it found and what it can't decide
python tools/ebay_api.py setup               # writes account.json
```

- Setup picks a policy or location when there is exactly one candidate (for returns, the only 30-day policy). When there are several, it says which flag to pass: `--fulfillment ID`, `--payment ID`, `--return ID`, `--return-14-day ID` or `--location-key KEY`. Choices already in `account.json` are kept on re-runs.
- `--disallow-fulfillment ID` (repeatable) marks a shipping policy that the validator must refuse, for example a calculated-shipping policy that causes package errors.
- Two flags change the seller account, so they need `--confirm` and the account owner's approval:
  - `--opt-in --confirm` enrolls in Business Policies. Wait a few minutes, create shipping, payment and return policies in Seller Hub, then run setup again.
  - `--create-location --location-key KEY --postal-code ZIP [--city --state --country] --confirm` creates an inventory location.
- The `pipeline` section holds thresholds (price review gate, minimum confidence, fee rates). Edit them by hand; setup keeps your values. `account.example.json` shows the shape and `schemas/account.json` documents each key.
- `EBAY_ACCOUNT_FILE=path` points the tools at a different file (a second account, or tests).
- `EBAY_WORKSPACE=folder` moves all private data (`.env`, `account.json`, the token cache, `listings/`, `raw_data/`) to that folder, so the code can stay in a clean clone. It must be a real environment variable, not a line in `.env`.

## 4. Check

```bash
python tools/ebay_api.py setup --dry-run     # "problems": [] means ready
python tools/ebay_api.py policies
python tools/ebay_api.py reconcile           # every listing folder vs eBay (empty on a fresh clone)
```

Then follow the workflows in `AGENTS.md`, starting with `/import-workflow`.
