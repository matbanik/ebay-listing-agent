---
name: ebay-api
description: Call the eBay Sell/Buy REST APIs through tools/ebay_api.py (no MCP server). Categories, item specifics, condition and return policy metadata, active-listing ceiling, image upload, inventory item, offer, fees, publish. Use for every eBay API call in the Evaluator, Lister and Review steps.
---

# eBay API Skill (`tools/ebay_api.py`)

One Python CLI covers every eBay call the pipeline makes. It replaces the ebay-mcp server: nothing loads at session start, and every agent harness runs the same commands.

```bash
python tools/ebay_api.py <command> [args]          # production (default)
python tools/ebay_api.py --env sandbox <command>   # sandbox (needs sandbox keys in .env)
```

- **Output:** JSON on stdout.
- **Errors:** eBay's full error body goes to stderr as `{"error": {status, method, url, body, hints}}`, with exit code 1.
- **Gate refusals:** a refused command exits with code 2 and prints `REFUSED: ...` on stderr. Treat exit 2 as "stop and ask the human". Never retry it with `--confirm` or `--skip-validate` on your own.

## Credentials

- Credentials are read from `.env` at the repo root (gitignored): `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_USER_REFRESH_TOKEN`, `EBAY_REDIRECT_URI` (RuName), `EBAY_ENVIRONMENT`. Real environment variables override the file. Never print or commit these values.
- Access tokens are cached in `.ebay-token-cache.json` (gitignored) and refreshed automatically.
- Browse uses an application token; every other command uses the user token.
- The refresh token expires about every 18 months. Errors 1001 or 1100 that persist mean it needs renewing:
  1. `python tools/ebay_api.py auth-url` prints a consent URL. The human opens it and signs in.
  2. `python tools/ebay_api.py exchange-code "<redirect URL or code>"` stores the new refresh token in `.env`.

## Commands

### Read-only (safe to run any time)

| Command | Use | Workflow |
|---|---|---|
| `policies` | List the fulfillment, payment and return policies | setup |
| `categories "<keywords>"` | Category suggestions from tree 0 (EBAY_US) | 04 step 3 |
| `aspects <catId> [--required] [--max-values N]` | Item specifics, required first | 04 step 3 |
| `condition-policies <catId>` | Condition IDs and `ConditionEnum` values the category accepts | 03 step 4 |
| `return-policies <catId>` | Return windows the category allows (14-day only in a few categories) | 03/04 |
| `browse "<query>" [--condition used\|new] [--buy-it-now] [--limit N]` | Active listings with delivered price (item + shipping) and min/median/max. **Ceiling only, never a pricing target** | 03 step 6 |
| `get-item <sku>` | Inventory item | 05 |
| `get-offer <offerId>` | Offer, including `status` (UNPUBLISHED / PUBLISHED) and `listing.listingId` | 05 |
| `offers --sku <sku>` | All offers for a SKU (empty list if none) | 04/05 |
| `reconcile [slug ...] [--archive]` | Live status (ACTIVE / SOLD / ENDED / NEVER_LISTED / NO_OFFER) of every folder in `listings/` and `listings/archive/`. `--archive` moves SOLD folders to `listings/archive/` and stamps `listing-draft.md`. See the `reconcile-listings` skill | 07 |
| `fees <offerId>` | Listing fees for an **unpublished** offer (a published one returns error 25402) | 04 step 6, 05 |

Add `--raw` to `categories`, `aspects` and `browse` to get eBay's unreduced response.

### Writes (each one appends a line to `listings/{slug}/api-log.jsonl`)

| Command | What it does | Gates |
|---|---|---|
| `upload-images <slug> [--replace] [--files a.jpg b.jpg]` | Uploads `{slug}-NN.jpg` in name order (hero = `-01`) to EPS through the Media API. Writes the URLs to `image-urls.json` as an array. It appends unless you pass `--replace`. Maximum 24 images | none |
| `put-item <slug>` | `PUT inventory_item/{slug}` from `inventory-item.json`. `product.imageUrls` is filled from `image-urls.json`, so the order always matches | runs the validator; refuses `packageWeightAndSize`; needs `--confirm` if the SKU has a live listing |
| `create-offer <slug>` | `POST offer` from `offer.json` (the offer stays unpublished). Writes the returned ID back as `_offerId` | runs the validator and the format checks; refuses if `_offerId` is already set or `sku` ≠ folder name |
| `update-offer <slug> [--offer-id ID]` | `PUT offer/{_offerId}` from `offer.json` | runs the validator; checks the SKU matches; needs `--confirm` if the offer is PUBLISHED |
| `delete-offer <offerId>` | Deletes an offer | refuses unless `status` is UNPUBLISHED (deleting a published offer would end the live listing) |
| `publish <offerId>` | Without `--confirm`: prints a preview (SKU, title, price, Best Offer floor, condition, images, fees) and exits 2. With `--confirm`: publishes and returns `listingId` and the URL | refuses unless UNPUBLISHED. **`--confirm` only after explicit human approval in this session** |

`--skip-validate` exists for debugging the tool itself. Don't use it in normal listing work.

> **`update-offer` is a full replace, not a patch.** eBay overwrites the whole offer with what you send. Always edit the complete `offer.json` and send all of it. A fragment would wipe the policies, price or description. `sku`, `marketplaceId` and `format` are stripped automatically because they can't be changed after the offer is created.

## Payload files (per listing)

The Lister writes the exact request bodies into the listing folder. Keys starting with `_` are notes and are never sent. `validate_payload.py` checks both files.

**`listings/{slug}/inventory-item.json`** is the `createOrReplaceInventoryItem` body. The SKU is the folder name.

```json
{
  "product": {
    "title": "Brand Model Key Feature",
    "description": "<div ...>HTML ... <p>Condition assessed from photos only.</p></div>",
    "aspects": { "Brand": ["..."], "Model": ["..."], "MPN": ["..."] },
    "brand": "...", "mpn": "...", "upc": ["Does Not Apply"]
  },
  "condition": "USED_EXCELLENT",
  "conditionDescription": "Specific marks and wear. Condition assessed from photos only.",
  "availability": { "shipToLocationAvailability": { "quantity": 1 } }
}
```

- Leave out `imageUrls`; `put-item` fills it in.
- Never include `packageWeightAndSize`. It causes the Invalid ShippingPackage error with the flat-rate policy.
- Aspect values are arrays of strings.

**`listings/{slug}/offer.json`** is the `createOffer` body.

```json
{
  "sku": "{slug}",
  "marketplaceId": "EBAY_US",
  "format": "FIXED_PRICE",
  "listingDuration": "GTC",
  "availableQuantity": 1,
  "categoryId": "57988",
  "merchantLocationKey": "<seller.merchantLocationKey>",
  "pricingSummary": { "price": { "value": "89.99", "currency": "USD" } },
  "listingPolicies": {
    "fulfillmentPolicyId": "<policies.fulfillment>",
    "paymentPolicyId": "<policies.payment>",
    "returnPolicyId": "<policies.return>",
    "bestOfferTerms": {
      "bestOfferEnabled": true,
      "autoDeclinePrice": { "value": "74.00", "currency": "USD" }
    }
  },
  "listingDescription": "<same HTML as product.description>"
}
```

- `price` is the evaluator's `recommended_price`, with shipping already included.
- `autoDeclinePrice` is the evaluator's `auto_decline_below` and must be lower than the price.
- Format checks run before sending:
  - FIXED_PRICE needs GTC and no auction prices.
  - AUCTION needs a `DAYS_n` duration, an `auctionStartPrice`, quantity 1, and not both Best Offer and Buy It Now. Buy It Now must be at least 30% above the start price.

**Account defaults** come from `account.json` at the repo root (gitignored; `python tools/ebay_api.py setup` writes it, `account.example.json` shows the shape). Copy the IDs from these keys; the validator errors on a disallowed or missing value and warns on any other difference:

| offer.json field | account.json key | Notes |
|---|---|---|
| `fulfillmentPolicyId` | `policies.fulfillment` | Free Standard Shipping, generic carrier. Never use an ID in `policies.disallowed_fulfillment` (calculated shipping) |
| `paymentPolicyId` | `policies.payment` | Immediate pay |
| `returnPolicyId` | `policies.return` | 30-day, buyer pays. Use `policies.return_14_day` only where `return-policies <catId>` lists 14 days |
| `merchantLocationKey` | `seller.merchantLocationKey` | |

If `account.json` is missing or incomplete, run `python tools/ebay_api.py setup`: it lists the account's policies and locations, picks each one that is unambiguous, and says which to pass (`--fulfillment ID`, `--location-key KEY`, ...). `setup --opt-in --confirm` enrolls in Business Policies and `setup --create-location --location-key KEY --postal-code ZIP --confirm` creates a location; both change the seller account, so ask first.

## Lister sequence

```bash
python tools/ebay_api.py upload-images {slug} --replace    # -> image-urls.json
python tools/ebay_api.py categories "{brand} {model}"
python tools/ebay_api.py aspects {catId} --required
python tools/ebay_api.py condition-policies {catId}
python tools/ebay_api.py return-policies {catId}
# write inventory-item.json + offer.json
python tools/validate_payload.py listings/{slug}/
python tools/ebay_api.py put-item {slug}
python tools/ebay_api.py create-offer {slug}                # -> _offerId in offer.json
python tools/ebay_api.py fees {offerId}
# STOP. Hand off to /review-workflow. The human approves, then:
python tools/ebay_api.py publish {offerId}                  # preview
python tools/ebay_api.py publish {offerId} --confirm        # only after explicit approval
```

## Errors

The `hints` field in the error output already maps these:

| Error | Cause | Fix |
|---|---|---|
| 25002 + "already exists" | An offer already exists for the SKU | Use `offers --sku`, set `_offerId`, then `update-offer` |
| 25002 + "System error" | Temporary eBay-side error (25002 is a generic code) | Wait a minute and retry |
| 25005 | eBay Motors category (tree 100, e.g. 177117) used on EBAY_US | Use the tree-0 category (riding apparel → 57988) |
| 25402 | `fees` called on a published offer | Expected; fees apply only before publishing |
| 25709 | Bad Content-Language / Accept-Language | Check `EBAY_CONTENT_LANGUAGE=en-US` in `.env` |
| 21919301 | UPC required by the category | `product.upc: ["Does Not Apply"]` |
| Invalid `ShippingPackage` | `packageWeightAndSize` sent | Remove it, run `put-item`, retry |
| Warning `ReturnsWithinOption` | Return window not allowed in this category | Switch to the 30-day policy (`policies.return`), then `update-offer` |
| 1001 / 1100 | Token invalid or missing a scope | Run once more; if it persists, use `auth-url` / `exchange-code` |
| 429 | Rate limited | Wait for the `Retry-After` time shown; don't loop |

These publish warnings are normal: "Funds on hold" (managed payments) and "Best Offer + immediate payment" (informational).

## Limits

- 250 listing revisions a day. More than that triggers a 24-hour block.
- Inventory API listings can't be revised in Seller Hub. Every change goes through `put-item` or `update-offer`.
- Unpublished offers don't appear in Seller Hub, not even under Drafts. `listing-draft.md` is the human's view of them.
- The Media API path (`commerce/media/v1_beta`) is a single constant in `ebay_api.py`, so it's quick to change if eBay moves it.
