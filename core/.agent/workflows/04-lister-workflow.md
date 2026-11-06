---
description: Upload images and create an unpublished eBay offer via tools/ebay_api.py (Inventory API)
---

# 04 — Lister Workflow

Upload the listing's images, create the inventory item and an **unpublished** offer (createOrReplaceInventoryItem → createOffer), and hand off to `/review-workflow`. `publishOffer` happens only in `/review-workflow`, after the human approves.

**Skills used**: `create-listing` (content, SEO), `ebay-api` (every command, payload file, gate and error)

**Account defaults** (IDs in `account.json`; `python tools/ebay_api.py setup` writes it):
- Shipping: Free Standard Shipping, generic carrier (`ShippingMethodStandard`, 2 business day handling; `fulfillmentPolicyId` = `policies.fulfillment`). The seller buys the cheapest ground label (UPS / FedEx / USPS) at sale time. Don't use the calculated-shipping policies in `policies.disallowed_fulfillment`.
- Payment: Buy It Now / Immediate Pay (`paymentPolicyId` = `policies.payment`)
- Returns: **30-day, buyer pays** (`returnPolicyId` = `policies.return`). eBay US only offers 14-day returns in a few categories (camera drones/lenses, digital cameras, collectibles & art, jewelry, medical & mobility); elsewhere the 14-day policy (`policies.return_14_day`) triggers "ReturnsWithinOption no longer supported". Use 14-day only where the category's return policy metadata allows it.
- Location: `merchantLocationKey` = `seller.merchantLocationKey`

## Prerequisites

- Completed `curator-output.json` and `evaluator-output.json` in `listings/{item-slug}/`
- `python tools/validate_payload.py listings/{item-slug}/` passes
- `.env` at the repo root has valid credentials (`python tools/ebay_api.py policies` returns the account policies). No MCP server is needed
- `account.json` is complete (`python tools/ebay_api.py setup --dry-run` reports no problems)
- Item value > $200, confidence < 0.70 or a condition disagreement: the user has already said to go ahead

## Steps

### 1. Upload Images to eBay (EPS)

Images must be in final order (hero = `{item-slug}-01.jpg`, set by the Curator). Upload them all in one call:

// turbo
```bash
python tools/ebay_api.py upload-images {item-slug} --replace
```

This uses the Media API (`createImageFromFile`, `sell.inventory` scope). It uploads `{item-slug}-NN.jpg` in name order and writes `image-urls.json` as a JSON array in that order. Without `--replace` it appends. Maximum 24 images.

### 2. Read Both Reports

Review:
- `listings/{item-slug}/curator-report.md` — product identity, condition, images
- `listings/{item-slug}/evaluator-report.md` — validated specs, pricing (shipping already baked in), title suggestion

### 3. Find Best eBay Category

```bash
python tools/ebay_api.py categories "{brand} {model} {type}"
```

Select the most specific category. Get required item specifics:

> eBay Motors categories (tree 100, e.g. 177117 Motorcycle Jackets) are not valid for `EBAY_US` offers: `get_listing_fees`/publish fail with error 25005, and the Inventory API rejects `marketplaceId: EBAY_MOTORS_US`. Use the category tree 0 suggests instead (riding apparel → 57988 Men's Coats, Jackets & Vests, where condition 3000 shows as "Pre-owned - Good").

```bash
python tools/ebay_api.py aspects {catId}            # required aspects first; --required for only those
python tools/ebay_api.py condition-policies {catId} # confirm final_grade is accepted
python tools/ebay_api.py return-policies {catId}    # confirm the 30-day window (or 14-day) is allowed
```

### 4. Craft Listing Content

**Title** (max 80 chars, Cassini-optimized):
- Include: brand, model, key differentiator specs, condition keyword
- No "Free Shipping", "Look", "!!" or promotional terms in title
- Example: `FSA SL-K Carbon Compact Drop Handlebar 380mm 31.8mm Road Bike`

**Description** (HTML):
- Opening paragraph with key selling points
- Specifications table (width, length, clamp diameter, weight, material etc.)
- Condition details with transparency — be specific about marks/wear
- "Condition assessed from photos only." — and no "tested"/"working" claims unless `condition.tested_by_human` is true
- What's included
- Do NOT repeat shipping or return info — eBay displays policy details automatically on every listing

**Item Specifics**:
- Fill all required aspects for the category (mandatory = listing won't publish without them)
- Fill optional aspects that improve search visibility
- `Brand` is almost always required

### 5. Create Inventory Item

Use the `final_grade` from evaluator-output.json. It must be a real Inventory API `ConditionEnum` value the category accepts (see `identify-product/references/condition-codes.json`). For used hard goods this is usually `USED_EXCELLENT` (shown as "Used").

Write `listings/{item-slug}/inventory-item.json`. The template is in the `ebay-api` skill.
- `product.title`: the crafted title.
- `product.description`: the HTML description.
- `product.aspects`: the item specifics (Brand is required), each value an array of strings.
- `condition`: `final_grade`.
- `conditionDescription`: specific condition notes (what marks, where, how bad).
- Leave out `imageUrls`. `put-item` fills it from `image-urls.json`, in order.
- Do NOT include `packageWeightAndSize`. It causes ShippingPackage errors with flat-rate policies, and `put-item` refuses it.

```bash
python tools/ebay_api.py put-item {item-slug}
```

### 6. Create Offer (unpublished)

Write `listings/{item-slug}/offer.json`. The template is in the `ebay-api` skill.
- `sku`: {item-slug}.
- `marketplaceId: EBAY_US`, `format: FIXED_PRICE`, `listingDuration: GTC`.
- `categoryId`: the selected category.
- `pricingSummary.price`: the evaluator's recommended price (shipping already baked in).
- `listingPolicies`:
  - `fulfillmentPolicyId`: `policies.fulfillment`, Free Standard Shipping (any carrier).
  - `paymentPolicyId`: `policies.payment`, Buy It Now.
  - `returnPolicyId`: `policies.return`, 30-day, buyer pays.
  - `bestOfferTerms`: `bestOfferEnabled: true`, and `autoDeclinePrice` = the evaluator's `auto_decline_below`.
- `merchantLocationKey`: `seller.merchantLocationKey`.
- `listingDescription`: the HTML description.

```bash
python tools/validate_payload.py listings/{item-slug}/   # also checks inventory-item.json and offer.json
python tools/ebay_api.py create-offer {item-slug}        # writes _offerId back into offer.json
python tools/ebay_api.py fees {offerId}                  # the fees eBay will charge
```

If `create-offer` fails with 25002 and the message says the offer already exists, find that offer with `offers --sku {item-slug}`, put its ID in `_offerId`, and use `update-offer`. A 25002 that says "System error" is temporary: wait a minute and retry.

An unpublished offer is **not visible in Seller Hub** (not even under Drafts). `listing-draft.md` is the only place the human can review it.

### 7. Write the Listing Draft Record

Create `listings/{item-slug}/listing-draft.md` from `templates/listing-draft-template.md`:
- Status: `DRAFT — awaiting approval`
- Offer ID, SKU, title, price, Best Offer floor, condition (enum + ID + buyer-facing label), return policy, image count
- Fill in real values. Never paste PowerShell expressions like `$($x.price)` into the file

### 8. Hand Off to Review

Present the draft and ask for approval. Do **not** run `publish` here:
```
📋 READY FOR REVIEW: {Product Name}
- Offer ID: {offerId}
- Price: ${price} (Free Shipping), Best Offer floor ${floor}
- Condition: {label} ({enum})
- Fees: ${fees}
Run /review-workflow to approve and publish.
```

## Publishing Notes (used by /review-workflow)

Warnings on `publish` that are normal and non-fatal:
- "Funds on hold" warning = managed payments notice
- "Best Offer + immediate payment" = informational, Best Offer still works

A "ReturnsWithinOption no longer supported" warning means the return policy's window isn't allowed in this category; eBay substitutes its own. Switch `offer.json` to the 30-day policy (`policies.return`) and run `update-offer`.

If you get `Invalid <ShippingPackage>` error:
- Remove `packageWeightAndSize` from `inventory-item.json` (not needed for flat-rate shipping) and run `put-item`
- Retry `publish`

Listings created through the Inventory API **cannot be revised in Seller Hub**; every change (price, description, condition) goes through `put-item` / `update-offer`. `update-offer` is a **full replace**: always send the complete `offer.json`. For a live listing, both need `--confirm` after the human approves the change.

## Quality Checklist

- [ ] Images uploaded in final order; `image-urls.json` is an array, hero first
- [ ] Title ≤ 80 characters, keyword-rich, no promotional text
- [ ] Description complete with specs and condition; photo-only disclaimer present
- [ ] All required item specifics filled (Brand mandatory)
- [ ] Correct category selected; condition enum accepted by that category
- [ ] Price includes shipping cost (baked in from evaluator)
- [ ] Free Standard Shipping policy (`policies.fulfillment`, generic carrier) applied
- [ ] Return policy allowed for the category (30-day `policies.return` by default)
- [ ] Best Offer enabled with the evaluator's auto-decline floor
- [ ] `inventory-item.json` and `offer.json` saved in the listing folder; validator passes
- [ ] Offer left **unpublished**; listing-draft.md written with real values
