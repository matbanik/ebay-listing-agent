# Pricing Strategy Reference

## The API Access Problem

> **No eBay API returns sold data** (Feb 2025+). Finding API decommissioned, Marketplace Insights restricted to enterprise.

## Data Source Hierarchy

| Priority | Source | Access | What It Gives |
|----------|--------|--------|---------------|
| 1 | **Terapeak** (Seller Hub) | Free manual UI | 365-day sold data, sell-through rate |
| 2 | **Apify** `caffein.dev/ebay-sold-listings` | API, ~$0.01-0.05/query | Scraped sold prices |
| 3 | **eBay Advanced Search** (Sold filter) | Free manual | 90-day sold data |
| 4 | **Browse API** active listings | `tools/ebay_api.py browse` | Active prices = **ceiling only** |
| 5 | **WorthPoint** | $29.99/month | Vintage/rare (700M+ records) |
| 6 | **PriceCharting** | Free tier | Games, cards, collectibles only |

## Pricing Algorithm

The canonical version (with the evaluator output format) is in `.agent/skills/price-discovery/SKILL.md`; this is a summary.

### 1. Collect Comps
- 10–50 sold items matching brand + model + condition
- Use shortest window that yields ≥ 5 comps:
  - 30 days (fast sellers) → 60 days (default) → 90 days (slow)
- Filter to **Buy It Now** sales only

### 2. Trim Outliers
- Remove top 10% and bottom 10% of prices

### 3. Calculate Baseline
- **Median** (not mean) of remaining prices

### 4. Apply Condition Adjustments

| Transition | Adjustment |
|-----------|------------|
| New → Like New | −10% to −20% |
| New → Very Good | −20% to −40% |
| New → Good | −40% to −60% |
| Each tier down | ~−10% to −20% |
| Missing accessories | −10% to −30% |
| With original packaging | +5% to +10% |

### 5. Add Shipping
- We list with free shipping, so add the estimated shipping cost to the baseline

### 6. Apply Strategy and Round
- Pick **one** strategy from the table below. The Premium + Best Offer markup (10-20% above median) **is** the negotiation buffer: don't add another on top
- Apply psychological pricing ($41.30 → $39.95)

### 7. Best Offer Floor and Net Proceeds
- Auto-decline at ≈ 80-85% of list price, never below your minimum acceptable price
- Fees are charged on the whole order including shipping:
  `net = price − price × FVF − $0.40 − shipping_cost`
- FVF: 13.6% most categories (no store), 12.7% with Basic store, 9.35% most consumer electronics, 15.3% books/media. Per-order fee $0.40 ($0.30 for orders ≤ $10)

## Low-Comp Handling (< 5 Sold)

1. **Broaden search** — drop color/variant
2. **Extend time** — 90d → 365d via Terapeak
3. **Cross-platform** — Mercari, Poshmark, StockX
4. **Active listings** = ceiling only (30-50% above actual sold)
5. **Truly unique** — auction starting at your floor price

## Key Metric: Sell-Through Rate

```
STR = Items sold in 90d / (Items sold + Currently listed) × 100
```

| Rate | Signal | Strategy |
|------|--------|----------|
| < 30% | Oversupplied | Price below median |
| 30-60% | Healthy | Price at median |
| > 60% | Strong demand | Price above median |

## Pricing Strategies

| Strategy | When | How |
|----------|------|-----|
| **Competitive** | Most items | At or up to 15% below median sold |
| **Premium + Best Offer** | Valuable/rare | 10-20% above median, enable BO |
| **Systematic Drops** | Slow movers | Start at market, −10% at 14d, −15% at 30d |
| **Auction** | Unique/collectible | 7-day, start at minimum acceptable |
