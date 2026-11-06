---
name: create-listing
description: Create eBay listing via the 3-call Inventory API flow (createInventoryItem → createOffer → publishOffer, the last only after human approval). Includes Cassini SEO, payload validation, and error handling.
---

# Create Listing Skill

Create eBay listings with `tools/ebay_api.py` (see the `ebay-api` skill for every command, gate and error). This skill covers the 3-call API flow, SEO optimization for Cassini, pre-publish validation, and common error recovery.

## Prerequisites (One-Time Setup)

Before any listing can be created, these must exist:
- [ ] eBay Developer account approved
- [ ] OAuth user token with `sell.inventory` scope
- [ ] Business policies created via Account API:
  - **Fulfillment policy** — free domestic shipping, 1-day handling (Cassini boost)
  - **Payment policy** — eBay Managed Payments
  - **Return policy** — 30-day returns. eBay US offers 14-day only in a few categories (cameras/drones, collectibles & art, jewelry, medical & mobility). Top Rated Plus additionally needs the returns to be **free** and 0–1 day handling, and only applies to Top Rated sellers.
- [ ] Inventory location exists, and `python tools/ebay_api.py setup` has recorded it and the policy IDs in `account.json`
- [ ] `.env` at the repo root holds the app keys and refresh token; `python tools/ebay_api.py policies` returns the account policies

## The 3-Call Listing Flow

```
Step 1: createOrReplaceInventoryItem (PUT /inventory_item/{SKU})
   └→ Creates the product record with details, images, condition

Step 2: createOffer (POST /offer)
   └→ Connects SKU to marketplace, category, price, policies
   └→ Unpublished — not visible to buyers, and NOT shown in Seller Hub (not even Drafts)

Step 3: publishOffer (POST /offer/{offerId}/publish)
   └→ Makes listing LIVE — this is IRREVERSIBLE
   └→ ⚠️ ALWAYS requires human approval before executing
```

## Step 1: Create Inventory Item

Write `listings/{slug}/inventory-item.json` (the full body is in the `ebay-api` skill), then:

```bash
python tools/ebay_api.py put-item {slug}
```

- SKU = folder slug.
- `product.title` is at most 80 characters.
- `product.description` is mobile-optimized HTML.
- `aspects` come from `aspects {catId}`.
- `brand`, `mpn` and `upc` go in the body. Use `upc: ["Does Not Apply"]` for items without a UPC.
- `imageUrls`: leave it out. `put-item` fills it from `image-urls.json` (the `upload-images` output), hero first.
- `condition`: a `ConditionEnum` value the category accepts (`condition-policies {catId}`). 3000 / `USED_EXCELLENT` = "Used" for most hard goods.
- `conditionDescription`: specific condition notes, including "Condition assessed from photos only."
- No `packageWeightAndSize`.

### UPC "Does Not Apply" Workaround

> [!WARNING]
> Error 21919301 will reject listings missing UPC/ISBN in categories that require it.
> For vintage, custom, or unbranded items: set `upc: ["Does Not Apply"]`

## Step 2: Create Offer (Unpublished)

Write `listings/{slug}/offer.json` (the full body and account default IDs are in the `ebay-api` skill), then:

```bash
python tools/ebay_api.py create-offer {slug}   # writes _offerId back into offer.json
python tools/ebay_api.py fees {offerId}
```

- `format`: `FIXED_PRICE` with `listingDuration: GTC`, or `AUCTION` with `DAYS_n`.
- `categoryId`: from `categories "<keywords>"`.
- `pricingSummary.price`: the evaluator's `recommended_price`.
- `bestOfferTerms.autoDeclinePrice`: the evaluator's `auto_decline_below`.
- Policies: the account defaults.
- `listingDescription`: the same HTML as `product.description`.

## Step 3: Publish (HUMAN APPROVAL REQUIRED)

```bash
python tools/ebay_api.py publish {offerId}             # preview + fees, exits 2
python tools/ebay_api.py publish {offerId} --confirm   # only after approval
```

> **NEVER auto-publish.** Show the human the listing summary and the preview, which includes the fees.
> Run `--confirm` only after explicit human approval given in the current session.

## eBay Title SEO (Cassini Algorithm)

### Formula
```
Brand + Model/MPN + Key Feature + Condition + Size/Color
```
Max **80 characters**. First ~52 characters carry the most SEO weight.

### Rules
- ✅ Dense, empirical keywords (brand, model, specs)
- ✅ Front-load the primary search term
- ✅ Include modifiers: "authentic," "sealed," "with tags" — "tested"/"working" only if the seller actually tested it
- ❌ No "WOW!", "L@@K!", "RARE", "AMAZING" (Cassini penalizes)
- ❌ No ALL CAPS words (brand stylings like "XREAL" and model codes are fine)
- ❌ No asterisks, excessive punctuation
- ❌ No keyword repetition

### Examples
```
Apple iPhone 14 Pro 256GB Unlocked Space Black Very Good Condition
Sony WH-1000XM5 Wireless Noise Canceling Headphones Silver Like New
Nintendo Switch OLED Model White Complete in Box
```

## Item Specifics (Critical for Visibility)

> Leaving item specifics blank drops listing traffic by ~28%.
> Cassini uses specifics for sidebar filter matching — unfilled = invisible.

1. Query: `python tools/ebay_api.py aspects {catId}` (required aspects listed first; `--required` shows only those)
2. Fill ALL required aspects (listing will be rejected without them)
3. Fill ALL recommended aspects (massive search visibility boost)
4. For items without UPC: `"Does Not Apply"`
5. For unbranded items: `"Unbranded"`

## HTML Description (Mobile-Optimized)

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
<div style="font-family: Arial, sans-serif; font-size: 16px; max-width: 800px; margin: 0 auto;">
  <h2>{Product Name}</h2>
  <p>{Key selling points paragraph}</p>

  <h3>Specifications</h3>
  <ul>
    <li><strong>Brand:</strong> {brand}</li>
    <li><strong>Model:</strong> {model}</li>
    <!-- ... more specs -->
  </ul>

  <h3>Condition</h3>
  <p>{Honest condition description with specific defect details}</p>

  <h3>What's Included</h3>
  <ul>
    <li>{item}</li>
    <li>{accessories}</li>
  </ul>
</div>
```

- ❌ No JavaScript (causes API rejection)
- ❌ No fixed-width tables (breaks mobile)
- ❌ No iframes, forms, `<object>`/`<embed>`, `javascript:` links or `on…=` handlers
- ✅ Use `<ul>` lists, not tables
- ✅ 16px minimum font size
- ✅ Max-width 800px for readability

## Listing Policies Guide

| Policy | Cassini-Optimal | When to Override |
|--------|-----------------|------------------|
| **Shipping** | Free domestic, 1-day handling | Heavy/low-margin → calculated shipping |
| **Returns** | 30-day buyer-paid returns | Free 30-day returns → Top Rated Plus (if Top Rated) + ranking boost |
| **Duration** | GTC (Good 'Til Cancelled) | Rare/collectible → 7-day auction |

## Pre-Publish Validation Checklist

Before calling `publishOffer`, verify:
- [ ] Title ≤ 80 characters
- [ ] Price is valid float > 0
- [ ] Condition ID is valid for the target category
- [ ] At least 1 image URL is HTTPS
- [ ] UPC provided or set to "Does Not Apply"
- [ ] All required item specifics filled
- [ ] Category ID is a valid leaf category
- [ ] Business policies (fulfillment, payment, return) are attached
- [ ] Quantity > 0
- [ ] "Condition assessed from photos only"; no unverified "tested" claims
- [ ] `python tools/validate_payload.py listings/{slug}/` passes
- [ ] Fees checked with `python tools/ebay_api.py fees {offerId}`
- [ ] **Human has explicitly approved**

## API Limits & Gotchas

- **250 listing revisions/day** — excessive edits trigger 24h API block
- **Inventory API listings cannot be edited via Seller Hub** — all revisions must go through API (confirmed in eBay's Inventory API overview)
- **Image upload**: Trading API `UploadSiteHostedPictures` is decommissioned 2026-09-30; use Media API `createImageFromFile` (what `ebay_api.py upload-images` does)
- **Sandbox** (`api.sandbox.ebay.com`) — test data only, `getCategorySuggestions` returns dummy data
- **OAuth tokens expire**: `ebay_api.py` refreshes access tokens automatically. The refresh token lasts about 18 months; renew it with `auth-url` and then `exchange-code`
- Environment toggle: `--env sandbox` or `EBAY_ENVIRONMENT=sandbox` vs `production`
