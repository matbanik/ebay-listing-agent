# Manifest

Every file in `core/` and what it does. Copy all of `core/` into a new repository, or run it in place with your data in a separate folder (`EBAY_WORKSPACE`, see `SETUP.md`). Nothing outside `core/` is needed at run time.

## Entry points

| File | Purpose |
|---|---|
| `AGENTS.md` | Agent instructions: commands, skills, workflows, roles, boundaries (Always / Ask First / Never). Read first by any agent harness |
| `CLAUDE.md` | One line (`@AGENTS.md`) so Claude Code loads AGENTS.md |
| `SETUP.md` | Fresh clone to a working pipeline: install, `.env`, `ebay_api.py setup` → `account.json`, checks |
| `requirements.txt` | Python dependencies |
| `.env.example` | Credential variable names with placeholder values. Copy to `.env` (gitignored) |
| `account.example.json` | Shape of `account.json` with dummy IDs. The real file is written by `ebay_api.py setup` and gitignored |
| `.gitignore` | Keeps credentials, seller IDs, photos, listing folders, backups and logs out of git |

## Tools (`tools/`)

| File | Purpose |
|---|---|
| `ebay_api.py` | Every eBay REST call: OAuth, setup, taxonomy, aspects, condition policies, browse, image upload, inventory item, offer, fees, publish, reconcile. Publish, delete and live changes need `--confirm` |
| `account_config.py` | Loads and checks `account.json` (`EBAY_ACCOUNT_FILE` overrides the path); pipeline defaults |
| `validate_payload.py` | Pre-offer gate: schemas, condition enum and ID, photo-only disclaimer, "tested" claims, price review threshold, policy IDs, image URLs |
| `process_images.py` | Resize, pad and orient photos for eBay; strips EXIF and GPS; reads HEIC |
| `organize_raw.py` | Copies processed images into `listings/{slug}/` with numbered names |
| `redact_text.py` | Finds sensitive text with OCR and blurs it (auth codes, keys, addresses), then re-checks with OCR |

## Skills (`.agent/skills/`)

| Skill | Purpose |
|---|---|
| `process-images/` | Image pipeline (Pillow, ImageMagick, optional rembg) and quality checks |
| `identify-product/` | Vision identification of brand, model and category, plus condition grading. `references/condition-codes.json` maps grades to eBay enums |
| `price-discovery/` | Sold comps, active ceiling, pricing algorithm |
| `create-listing/` | Inventory API flow (item → offer → publish after approval), title and description rules |
| `ebay-api/` | `ebay_api.py` commands, payload files, `account.json` keys, safety gates, error fixes |
| `redact-images/` | When and how to run `redact_text.py` |
| `reconcile-listings/` | Live vs sold status of each listing folder; archiving sold items |

## Workflows (`.agent/workflows/`)

| File | Purpose |
|---|---|
| `01-import-workflow.md` | Bring photos in from `raw_data/`, process them, group them by item |
| `02-curator-workflow.md` | Identify each item and grade its condition → `curator-output.json` |
| `03-evaluator-workflow.md` | Confirm identity, price from comps → `evaluator-output.json` |
| `04-lister-workflow.md` | Upload images, write payloads, create an **unpublished** offer |
| `05-review-workflow.md` | Human approval, then `publish --confirm` |
| `06-batch-workflow.md` | Workflows 01–05 for several items |
| `07-reconcile-workflow.md` | Check live and sold status, archive sold listings |

## Reference docs (`.agent/docs/`)

| File | Purpose |
|---|---|
| `condition-grading.md` | eBay condition definitions per category group, grading from photos, confidence routing |
| `ebay-image-guide.md` | eBay photo specs, the processing pipeline, ImageMagick commands, Google Takeout handling, hero shot choice |
| `pricing-strategy.md` | Comp sources, the pricing algorithm (outliers, condition, shipping, Best Offer floor), low-comp handling, sell-through |

## Contracts and templates

| File | Purpose |
|---|---|
| `schemas/curator-output.json` | Curator → Evaluator contract (JSON Schema) |
| `schemas/evaluator-output.json` | Evaluator → Lister contract |
| `schemas/account.json` | Documents every `account.json` key |
| `templates/curator-report-template.md` | Human-readable curator report |
| `templates/evaluator-report-template.md` | Human-readable pricing report |
| `templates/listing-draft-template.md` | Listing status and review checklist |

## Tests and state

| File | Purpose |
|---|---|
| `tests/test_ebay_api.py` | Unit tests for the API client, setup, gates and validator, with a fake HTTP session and no network. Run `python -m pytest tests/ -q` |
| `.agent/context/current-focus.md` | Seed: what the agent is working on now |
| `.agent/context/known-issues.md` | Seed: problems found and their workarounds |
| `listings/.gitkeep`, `listings/archive/.gitkeep`, `raw_data/.gitkeep`, `backups/.gitkeep` | Empty working folders. Their contents are gitignored |

## Not included, on purpose

- **Real listings, photos and reports:** listing photos can carry GPS data, and the folders hold seller-specific data. `examples/` (outside `core/`) has one synthetic listing instead.
- **`.env`, `account.json`, token caches, `api-log.jsonl`:** credentials and seller IDs. Each adopter creates their own.
- **`research/`:** deep-research outputs written before `ebay_api.py` existed. Only the prompts ship, in `docs/research-prompts/`.
- **`archive/`:** retired scripts from the maintainer's original setup.
- **Session state** (the maintainer's `.agent/context/`): replaced by the empty seeds above.
