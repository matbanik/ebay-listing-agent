---
description: Human review and approval of eBay listing draft
---

# 05 — Review Workflow

Human reviews the draft listing and either approves for publishing or requests changes.

## Prerequisites

- Completed `listing-draft.md` with eBay offer ID (from `/lister-workflow`)
- `python tools/validate_payload.py listings/{slug}/` passes

> Unpublished Inventory API offers do **not** appear in Seller Hub (not even under Drafts). Review happens from `listing-draft.md`, the images in the listing folder, and `python tools/ebay_api.py get-offer {offerId}` / `fees {offerId}` (see the `ebay-api` skill).

## Confidence-Gated Review

Not every listing requires full review. During **calibration** (first 50-100 listings), review everything. After calibration:

| Condition | Review Level |
|-----------|-------------|
| All confidence ≥ 0.85, comps ≥ 5, value < $200 | Quick scan (title + price + images) |
| Any flag from Evaluator | Full review |
| Value > $200 | Full review |
| Restricted category | Full review |
| Condition disagreement between agents | Full review |
| First listing in a new category | Full review |

## Steps

### 1. Present Listing Summary

Show the human:
- Product name, brand, model
- Images (hero shot + defect close-ups)
- Title and description preview
- Price (recommended + min/max range)
- Comp data summary (count, median, source)
- Category and filled item specifics
- Any flags or review reasons
- eBay fees (`python tools/ebay_api.py publish {offerId}` without `--confirm` prints the summary with fees and publishes nothing) and net proceeds at list price and at the Best Offer floor

### 2. Human Reviews the Draft

The human should verify:
- [ ] Title is accurate, SEO-optimized, ≤ 80 chars
- [ ] Description is honest and complete
- [ ] Images display correctly
- [ ] Price is competitive but fair
- [ ] Condition grade matches visible evidence
- [ ] Description says "Condition assessed from photos only" and makes no "tested"/"working" claim the human hasn't confirmed
- [ ] Shipping and return policies configured
- [ ] All item specifics filled
- [ ] Category is correct leaf category

### 3. Handle Review Outcome

**If APPROVED** → Proceed to Step 4

**If CHANGES NEEDED**:
- Human specifies changes
- Edit `inventory-item.json` / `offer.json`, then run `python tools/ebay_api.py put-item {slug}` / `update-offer {slug}`. Inventory API listings cannot be revised in Seller Hub, and the limit is 250 revisions a day. `update-offer` is a **full replace**, so always edit and send the complete `offer.json`. On a live listing both commands need `--confirm`, which is allowed only after the human approves that change
- Re-present for review
- Loop until approved

**If REJECTED**:
- Delete the unpublished offer so it doesn't linger: `python tools/ebay_api.py delete-offer {offerId}`. The command checks `status` first and refuses anything that isn't UNPUBLISHED, because on a published offer this would end the live listing
- Move item folder to `listings/archive/{slug}/` with status `rejected`
- Note rejection reason

### 4. Publish Listing

> **NEVER auto-publish.** Publish only offers the human approved **in this session**, by name or as an explicitly listed batch ("publish 1, 3 and 4"). Approval of one item or one earlier batch does not carry over. Items > $200 need their own explicit approval.

```bash
python tools/ebay_api.py publish {offerId}             # preview: SKU, title, price, floor, condition, fees (exits 2)
python tools/ebay_api.py publish {offerId} --confirm   # only for offers approved in this session
```

The offer ID is in `listing-draft.md` (and as `_offerId` in `offer.json`). `publish` refuses offers that aren't UNPUBLISHED. The response gives `listingId` and the item URL.

### 5. Update Records

Update `listing-draft.md`:
- Status: `draft` → `live`
- Add eBay listing ID (from publish response) and `https://www.ebay.com/itm/{listingId}`
- Add publish timestamp
- Record any publish warnings (e.g. "ReturnsWithinOption no longer supported" means the return policy was overridden; fix the offer's return policy)

### 6. Archive (After Sale/Expiry)

When item sells or listing expires:
- Status → `sold` or `expired`
- Move: `listings/{slug}/` → `listings/archive/{slug}/`
