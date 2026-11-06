---
name: reconcile-listings
description: Compare every listings/{slug}/ folder with its live eBay status (ACTIVE, SOLD, ENDED, NEVER_LISTED, NO_OFFER) and archive sold items to listings/archive/. Use when asked which listings are live or sold, to clean up the listings folder, or before starting a new batch.
---

# Reconcile Listings Skill

One read-only command checks every listing folder against eBay. With `--archive` it also moves the sold folders.

```bash
python tools/ebay_api.py reconcile                 # report only (no file changes, no eBay writes)
python tools/ebay_api.py reconcile --archive       # move SOLD folders to listings/archive/ and stamp them
python tools/ebay_api.py reconcile sony-wh-1000xm5  # only these folders
```

## How status is decided

The command calls `GET /sell/inventory/v1/offer?sku={sku}` for each folder in `listings/` and `listings/archive/`.
- **SKU:** `sku` in `offer.json`, or the folder name when there is no `offer.json`.
- **Scope:** reads use the existing `sell.inventory` scope. No new consent is needed.

| Status | eBay data | Meaning |
|--------|-----------|---------|
| `ACTIVE` | offer `PUBLISHED`, `listing.listingStatus` `ACTIVE` | Live on eBay |
| `SOLD` | listing `OUT_OF_STOCK` (or ended) with `soldQuantity` ≥ 1. The offer drops back to `UNPUBLISHED` | Sold. Archive it |
| `ENDED` | has a `listingId` but not active, `soldQuantity` 0 | Ended unsold. Relist or archive by hand |
| `NEVER_LISTED` | offer exists, no `listing` | Offer was created but never published |
| `NO_OFFER` | no offers for the SKU | Not on eBay at all (SKU mismatch, or offer deleted) |

## What `--archive` does

- **Sold folders in `listings/`:**
  1. Writes a stamp block under the first heading of `listing-draft.md`. The block sits between `<!-- reconcile:start -->` and `<!-- reconcile:end -->`, carries the date, status, listing ID and offer ID, and supersedes older status text.
  2. Moves the folder to `listings/archive/{slug}/`.
- **Folders already in `listings/archive/` that are SOLD, ENDED or NEVER_LISTED:** refreshes their stamp.
- **Refuses** to move a folder when `listings/archive/{slug}` already exists (`"action": "NOT moved: ..."`).
- **Never touches** ACTIVE, ENDED or NO_OFFER folders in `listings/`. It flags them under `action` for a human decision.
- **Never deletes anything** and makes no eBay write calls.
- **Idempotent.** A re-run replaces the stamp instead of stacking it.

## Output

JSON with:
- `checked`: the date.
- `summary`: `{status: [slugs]}`.
- `items`: one per folder, with `slug`, `location`, `sku`, `status`, `offerId`, `listingId`, `listingStatus`, `soldQuantity`, `price` (the listed price, not the sale price), `url` and `action`.
- `next`: what to do next.

Flags in `action`:
- `archive`: sold and still in `listings/`. Run with `--archive`.
- `still live but archived: move back to listings/`: move it back by hand with `git mv`.
- `review: not live and not sold`: ask the human whether to relist or archive.

## Git

- The move is a plain filesystem rename. Git sees each tracked folder as deleted plus untracked until it is staged; `git add -A listings/` records it as a rename.
- `api-log.jsonl` is gitignored and moves with its folder.
- Commit only when the user asks (see AGENTS.md and the global git rules).

## Limits

- **No sale price, buyer or date sold.** Those need the `sell.fulfillment` scope and `getOrders`, which this pipeline has not been granted. To add them:
  1. `python tools/ebay_api.py auth-url --scope https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly`
  2. `exchange-code`
  3. Extend `cmd_reconcile`.
- **Multi-quantity listings** that are still `ACTIVE` with sales count as ACTIVE (`soldQuantity` is reported).
- **Listings created outside the Inventory API** (Seller Hub, the old Trading API) have no offer, so they show as `NO_OFFER`.
