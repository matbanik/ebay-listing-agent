# eBay Listing Pipeline — AI Agent Instructions

Multi-agent pipeline: Google Photos → AI identification → price discovery → eBay listing → human approval.

First run on a new machine or account: `SETUP.md` (install, `.env`, `ebay_api.py setup` → `account.json`).

## Commands

```bash
# Image processing
python tools/process_images.py --input raw_data/     # Resize, pad, strip EXIF/GPS (HEIC OK)
python tools/organize_raw.py --list                   # List processed images
python tools/organize_raw.py --move images/IMG_1.jpg images/IMG_2.jpg --to "Product Name"
python tools/redact_text.py listings/{slug}/*.jpg --text AB12-CD34 --after-label "Authentication Code"  # Blur codes/keys

# eBay API (no MCP server; see .agent/skills/ebay-api/SKILL.md). Credentials in .env, seller IDs in account.json (both gitignored)
python tools/ebay_api.py policies                          # Business policies (setup check)
python tools/ebay_api.py setup [--dry-run]                 # Policy IDs + inventory location -> account.json
python tools/ebay_api.py categories "brand model"           # Category suggestions
python tools/ebay_api.py aspects {catId} --required         # Item specifics
python tools/ebay_api.py condition-policies {catId}         # Accepted condition IDs
python tools/ebay_api.py browse "brand model" --condition used  # Active ceiling (not sold prices)
python tools/ebay_api.py upload-images {slug} --replace     # EPS upload, hero first -> image-urls.json
python tools/ebay_api.py put-item {slug}                    # inventory-item.json -> inventory item
python tools/ebay_api.py create-offer {slug}                # offer.json -> UNPUBLISHED offer
python tools/ebay_api.py fees {offerId}
python tools/ebay_api.py publish {offerId} --confirm        # Review step only, after human approval
python tools/ebay_api.py reconcile [--archive]              # Live/sold status of every folder; --archive moves sold to listings/archive/
# add --env sandbox (before the command) to test against the sandbox

# Validation
python tools/validate_payload.py listings/{slug}/     # Pre-publish check (schema, condition, disclaimer, images)
python tools/validate_payload.py listings/*/ --json   # All listings, machine-readable
```

## Skills

| Skill | Path | Purpose |
|-------|------|---------|
| `process-images` | `.agent/skills/process-images/SKILL.md` | Image pipeline (Pillow + ImageMagick + rembg) |
| `identify-product` | `.agent/skills/identify-product/SKILL.md` | AI vision product ID + condition grading |
| `price-discovery` | `.agent/skills/price-discovery/SKILL.md` | Sold comps + pricing algorithm |
| `create-listing` | `.agent/skills/create-listing/SKILL.md` | eBay 3-call API flow + Cassini SEO |
| `ebay-api` | `.agent/skills/ebay-api/SKILL.md` | `tools/ebay_api.py` commands, payload files, safety gates, error fixes |
| `redact-images` | `.agent/skills/redact-images/SKILL.md` | OCR-find and blur auth codes, keys, personal data in photos |
| `reconcile-listings` | `.agent/skills/reconcile-listings/SKILL.md` | Live vs sold status of every listing; archive sold items |

## Workflows

| # | Command | Purpose |
|---|---------|---------|
| 01 | `/import-workflow` | Process images, group them per item |
| 02 | `/curator-workflow` | AI product identification |
| 03 | `/evaluator-workflow` | Validation + pricing |
| 04 | `/lister-workflow` | Upload images, create **unpublished** offer |
| 05 | `/review-workflow` | Human approval → publish |
| 06 | `/batch-workflow` | Full pipeline for multiple items |
| 07 | `/reconcile-workflow` | Check live/sold status, archive sold listings |

## Agent Roles

- **Curator**: Analyzes images → product ID, condition, image organization. Uses `identify-product` + `process-images` skills.
- **Evaluator**: Validates ID, finds sold comps, calculates price. Uses `price-discovery` skill.
- **Lister**: Uploads images, writes `inventory-item.json` + `offer.json`, and creates an unpublished offer with `tools/ebay_api.py`. Uses `create-listing` + `ebay-api` skills. Stops there: publishing happens only in `/review-workflow` after human approval.

## Project Structure

```
ebay/
├── AGENTS.md                    # This file
├── .env                         # API credentials (gitignored; .env.example)
├── account.json                 # Policy IDs, location, thresholds (gitignored; `ebay_api.py setup`)
├── .agent/skills/               # Reusable SKILL.md capabilities
├── .agent/workflows/            # Numbered orchestration steps
├── .agent/docs/                 # Reference documentation + research
├── .agent/context/              # Active work state
├── raw_data/                    # Drop zone for Google Photos
├── listings/{item-slug}/        # Per-item folders:
│   ├── {slug}-01.jpg            #   Processed product images
│   ├── image-urls.json          #   eBay CDN URLs (from upload)
│   ├── curator-output.json      #   Curator agent contract
│   ├── curator-report.md        #   Human-readable ID report
│   ├── evaluator-output.json    #   Evaluator agent contract
│   ├── evaluator-report.md      #   Human-readable pricing report
│   ├── inventory-item.json      #   createOrReplaceInventoryItem body (Lister)
│   ├── offer.json               #   createOffer body; _offerId written back
│   ├── api-log.jsonl            #   Write-call log from ebay_api.py (gitignored)
│   └── listing-draft.md         #   Listing status + metadata
├── listings/archive/{slug}/     # Sold / rejected / ended items
├── templates/                   # Report templates (curator, evaluator, listing-draft)
├── tools/                       # Reusable parameterized scripts
├── schemas/                     # JSON schema contracts
├── tests/                       # Unit tests (pytest)
└── backups/                     # File backups before deletes (gitignored)
```

## Inter-Agent Data Flow

```
Import  → image-urls.json                → (available to Lister)
Curator → schemas/curator-output.json    → Evaluator
Evaluator → schemas/evaluator-output.json → Lister
Lister  → listing-draft.md (offer unpublished) → Review (human gate) → publishOffer
```

JSON schemas define typed contracts at every handoff. Markdown reports are human-readable summaries alongside the validated JSON.

## System Tools

| Tool | Version | Use For |
|------|---------|---------|
| ImageMagick | 7.1.2-12 | Batch format conversion, ICC profiles |
| ffmpeg | N-121164 | Video thumbnails, Live Photo cleanup |
| Python + Pillow | System | Core image processing pipeline |
| `ebay_api.py` | tools/ | All eBay REST calls (Inventory, Taxonomy, Metadata, Account, Browse, Media) with publish/delete/live-change gates; replaces ebay-mcp |
| `validate_payload.py` | tools/ | Pre-publish validation: schema, condition enum/ID, disclaimer, "tested" claims, $200 gate, image URLs |
| `process_images.py` | tools/ | Batch resize + convert for eBay specs, strips EXIF/GPS |
| `organize_raw.py` | tools/ | Copy processed images into `listings/{slug}/` with numbered names |
| `redact_text.py` | tools/ | Blur sensitive text (auth codes, keys, addresses) found by RapidOCR; verifies by re-OCR |

## Conventions

- **Slugs**: lowercase, hyphens, no special chars (e.g., `sony-wh-1000xm5`)
- **Images**: `{slug}-01.jpg`, `{slug}-02.jpg`, etc.
- **Condition**: Use real Inventory API `ConditionEnum` values the category accepts (used hard goods: usually `USED_EXCELLENT`/3000, shown as "Used"). Grade one level down when uncertain, once, in the Curator only
- **Returns**: 30-day buyer-pays policy by default; 14-day is only allowed in a few categories
- **Titles**: Max 80 chars, format: `Brand + Model + Feature + Condition`

## Boundaries

### Always Do
- Back up a file before deleting it: copy it to `backups/YYYY-MM-DD/` (gitignored), or use the backup tool you chose during adoption
- Create listing as draft — never auto-publish
- Use sandbox before production for API testing
- Fill all required AND recommended item specifics
- Include "Condition assessed from photos only" disclaimer
- Run `validate_payload.py` before creating an offer

### Ask First
- Publishing any listing (mandatory human gate)
- Items with confidence < 0.70 on any metric (`pipeline.min_confidence` in account.json)
- Items valued > $200 (`pipeline.price_review_threshold`)
- Condition disagreements between agents

### Never Do
- Auto-publish listings without human approval
- Guess brand names or model numbers
- Claim "tested" or "working" unless the user actually tested the item (`tested_by_human`)
- Use Finding API (decommissioned Feb 2025)
- Override user-specified values on API failure
- Delete files without the user's request and a backup
