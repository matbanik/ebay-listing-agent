---
description: Validate product identity and perform price discovery
---

# 03 — Evaluator Workflow

Validate the Curator's identification, estimate shipping costs, find sold comps, calculate pricing, and produce the listing specification for the Lister.

**Skills used**: `price-discovery`, `identify-product` (for condition code validation)

## Prerequisites

- Completed `curator-output.json` and `curator-report.md` in `listings/{item-slug}/`

## Steps

### 1. Read Curator Output

Load `listings/{item-slug}/curator-output.json` and review:
- Product identification (brand, model, category)
- Condition grade and confidence
- Any flags or low-confidence fields

### 2. Validate Product Identity

Search web to confirm identification:
```
"{brand} {model}" official specifications
"{brand} {model}" product page
```

Verify:
- [ ] Brand and model match official product
- [ ] Category is correct for eBay
- [ ] Key features match what's visible in images
- [ ] Original MSRP found (for reference)
- [ ] UPC/MPN located (or set "Does Not Apply")

### 3. Estimate Package Size & Shipping Cost

> **Critical**: We offer free shipping on all listings. The shipping cost MUST be baked into the item price. Under-estimating means we lose money on every sale.

**Step A — Get dimensions and weight:**

1. Check manufacturer's spec page for product weight
2. Search: `"{brand} {model}" specifications weight dimensions`
3. Check competitor eBay listings — look at "Shipping" tab for package type clues
4. If no data found, use the category defaults below:

| Category | Est. Item Weight | Box Overhead | Total Ship Weight |
|----------|-----------------|--------------|-------------------|
| Handlebar | 250–300g | +400g box | ~0.7–1.5 lb |
| Stem | 100–200g | +300g | ~0.5–1.0 lb |
| Saddle | 250–400g | +300g | ~1.0–1.5 lb |
| Aerobars | 350–500g | +400g | ~1.5–2.0 lb |
| Wheels | 1500–2500g | +600g | ~5–7 lb |
| Full groupset | 2000g+ | +800g | 6–10 lb |

**Step B — Estimate the cheapest ground shipping cost (national average, from the seller's zip, `seller.postalCode` in `account.json`):**

| Ship Weight | USPS Ground Advantage | USPS Priority Mail |
|------------|----------------------|-------------------|
| < 8 oz | $4–6 | $9–11 |
| 8–16 oz | $6–8 | $9–11 |
| 1–2 lb | $8–10 | $10–13 |
| 2–3 lb | $10–13 | $12–15 |
| 3–5 lb | $12–16 | $14–18 |
| 5–10 lb | $16–22 | $18–26 |

Use the **cheapest ground** estimate. The fulfillment policy (`policies.fulfillment` in `account.json`) is generic Free Standard Shipping (`ShippingMethodStandard`), so the seller buys the cheapest label at sale time: USPS Ground Advantage for light items, and for heavy or bulky boxes (over ~10 lb or large dimensional weight) whichever of UPS Ground, FedEx Ground or Ground Advantage quotes lowest. Never quote Priority Mail.

**Step C — Record in evaluator-output.json:**
```json
"shipping": {
  "estimatedWeightLb": 1.5,
  "estimatedServiceCost": 12.00,
  "estimationSource": "manufacturer specs + USPS calculator",
  "notes": "Box is 12x6x4in, cheapest ground carrier"
}
```

### 4. Validate Condition Code

Get the valid condition IDs for the target category (Metadata API `getItemConditionPolicies`, `ebay-api` skill):

```bash
python tools/ebay_api.py categories "{brand} {model}"      # if the category ID isn't known yet
python tools/ebay_api.py condition-policies {catId}        # condition IDs + ConditionEnum values
python tools/ebay_api.py return-policies {catId}           # return windows allowed (for return_policy)
```

If the command fails, report the error to the user. Don't guess the accepted conditions.
- Reference `condition-codes.json` in `identify-product` skill; send only real `ConditionEnum` values
- Most hard-goods categories (electronics, health devices, many cycling parts) accept only `USED_EXCELLENT` (3000, displayed as "Used") for used items. `USED_VERY_GOOD` (4000) / `USED_GOOD` (5000) are mainly Books/Media. Use the finer grade only if the category policy lists it; otherwise use 3000 and put the detail in `condition_description`
- New/uninstalled but opened: `NEW_OTHER` (1500)
- `final_grade` and `condition_id` must agree (validate_payload.py checks this)
- Do **not** grade down again; the Curator already applied the conservative bias
- If Evaluator disagrees with Curator's grade → **ask the user**

> **Note**: `PRE_OWNED_EXCELLENT` (2990) and `PRE_OWNED_FAIR` (3010) are apparel-only.

### 5. Price Discovery — Sold Comps (price-discovery skill)

Follow the algorithm from `price-discovery` SKILL.md:

1. **Collect**: Terapeak first (manual), or Apify `caffein.dev/ebay-sold-listings` (use the `keywords` array input)
2. **Trim**: Remove top/bottom 10% outliers
3. **Baseline**: Median of remaining prices
4. **Adjust**: Apply condition delta from pricing table
5. **Add Shipping**: Add estimated shipping cost (Step 3) to baseline — buyer sees "Free Shipping"
6. **Round**: Psychological pricing (e.g. $87.12 → $89.99). This is the list price.
7. **Best Offer floor**: `auto_decline_below` ≈ 80–85% of the list price, never below the net-proceeds floor (below)

**Net-proceeds check** (eBay fees apply to the whole order including shipping):
```
net = price − (price × 0.136) − 0.40 − shipping_cost
```
13.6% is the final value fee for most categories without a store (Basic store: 12.7%, most consumer electronics 9.35%). Record `net` at the list price and at `auto_decline_below` in the report. If `net` at the floor is below what the seller would accept, raise the floor or flag it.

> **Do NOT use `browse` for pricing.** Browse API returns active listings only — use as ceiling, never as target. But DO check active listings to see if competitors offer free shipping or charge separate; adjust accordingly.

### 6. Price Discovery — Active Competition

Check current market:
```bash
python tools/ebay_api.py browse "{brand} {model}" --condition used --buy-it-now
```
Each item shows `price`, `shipping` and the delivered `total`, and `stats` gives min/median/max of the delivered totals. Note: price range, seller count, listing quality, whether they include free shipping.

Compare **delivered** prices (item + shipping; for calculated shipping, add our Step 3 estimate). Our list price already includes shipping, so it lines up with a competitor's item price plus their shipping charge, not with their item price alone. When the user sets a price by looking at competitors' item prices, treat it as an item price and add our ground shipping estimate on top to get the list price. Then check where that delivered price ranks against the active asks.

### 7. Generate Evaluator Output

Create **both**:
1. `listings/{item-slug}/evaluator-report.md` — human-readable summary (template: `templates/evaluator-report-template.md`)
2. `listings/{item-slug}/evaluator-output.json` — typed contract per `schemas/evaluator-output.json`, including the `shipping` block from Step 3

Description and condition text rules:
- Include **"Condition assessed from photos only."** in `condition_description`
- Never write "tested", "fully functional" or "confirmed working" unless the user confirmed they tested the item. Record that as `condition.tested_by_human: true`. A false functional claim makes every return an eBay Money Back Guarantee "not as described" case
- `return_policy` must describe the policy the Lister will actually attach (see `/lister-workflow`)

### 8. Run Pre-Publish Validation

```bash
python tools/validate_payload.py listings/{item-slug}/
```

Fix any errors before proceeding.

### 9. Determine Routing

| Condition | Route |
|-----------|-------|
| All confidence ≥ 0.70, no flags | Proceed to `/lister-workflow` |
| Any confidence < 0.70 | Ask the user before listing |
| Evaluator changed Curator's condition | Ask the user before listing |
| Item value > $200 | Ask the user before listing (`requires_human_review: true`) |
| < 5 sold comps found | Flag in `review_reasons`; shown at review |
| Category is restricted | Ask the user before listing |

## Quality Checklist

- [ ] Product identity validated against official sources
- [ ] Package weight estimated from specs or comp analysis
- [ ] Shipping cost estimated and added to item price
- [ ] Condition ID confirmed against the category's condition policy; grade and ID agree
- [ ] "Condition assessed from photos only" present; no "tested" claims unless `tested_by_human`
- [ ] At least 5 sold comps collected (or low-comp strategy documented)
- [ ] Pricing follows the algorithm (shipping baked in, net proceeds checked at list price and floor)
- [ ] Active listing competition assessed (including whether comps offer free shipping)
- [ ] Both evaluator-report.md and evaluator-output.json created
- [ ] JSON validates against schemas/evaluator-output.json
- [ ] validate_payload.py passes
