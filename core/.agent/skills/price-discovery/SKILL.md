---
name: price-discovery
description: Determine fair market value from eBay sold comps, active listings, and cross-platform data. Uses Terapeak, Apify, and statistical analysis.
---

# Price Discovery Skill

Find sold comparable sales ("comps") and calculate a fair listing price. Designed for the Evaluator agent.

## The API Access Problem

> [!CAUTION]
> **No official eBay API returns sold item data** as of 2025-2026.
> - Finding API `findCompletedItems` — **decommissioned Feb 2025**
> - Marketplace Insights API — **restricted to enterprise partners** (individual devs routinely denied)
> - Browse API — returns **active listings only** (no sold/completed filter)
> - `tools/ebay_api.py` (`ebay-api` skill) covers Sell APIs for seller actions plus Browse; it does NOT provide sold data

## Data Sources (Ranked by Reliability)

| Source | Access | Data Quality | Cost |
|--------|--------|-------------|------|
| **Terapeak** (eBay Seller Hub) | Manual web UI | Best — 365-day history, sell-through rates | Free with eBay account |
| **Apify** `caffein.dev/ebay-sold-listings` | API | Good — actual sold prices | ~$0.01–0.05/query |
| **eBay Advanced Search** (Sold filter) | Manual web | Good — 90-day sold data | Free |
| **Browse API** active listings | `python tools/ebay_api.py browse "<query>"` | Ceiling only — NOT actual sold prices | Free |
| **WorthPoint** | Subscription | Excellent for vintage/rare — 700M+ records | $29.99/month |
| **PriceCharting** | Web/API | Games, cards, collectibles only | Free tier available |
| **CamelCamelCamel** | Web | Amazon cross-reference for MSRP baseline | Free |

## Apify Sold Listings Code

```python
from apify_client import ApifyClient

def get_sold_comps(keyword: str, api_token: str) -> list:
    """Fetch recently sold eBay items matching keyword."""
    client = ApifyClient(api_token)
    # 'keyword' (single string) is deprecated; the actor takes a 'keywords' array
    run = client.actor('caffein.dev/ebay-sold-listings').call({
        'keywords': [keyword],
    })
    items = []
    for item in client.dataset(run['defaultDatasetId']).iterate_items():
        items.append({
            'title': item.get('title'),
            'price': item.get('price'),
            'currency': item.get('currency'),
            'date': item.get('soldDate'),
            'condition': item.get('condition'),
            'url': item.get('url'),
        })
    return items
```

## Pricing Algorithm

### Step 1: Collect Comps
- Gather 10–50 recent sold items matching brand + model + condition tier
- **Time windows** (use shortest that yields ≥5 comps):
  - 30 days for fast-moving items (electronics, popular brands)
  - 60 days as default
  - 90 days for slower-selling items
- Filter to **Buy It Now sales only** for consistency (exclude auctions unless few comps)

### Step 2: Outlier Trimming
- Remove top 10% and bottom 10% of prices
- This eliminates fire-sales, bundled lots, and bidding wars

### Step 3: Calculate Baseline
- **Median** of remaining prices = baseline fair market value
- Not mean — eBay sold data is inherently skewed

### Step 4: Condition Adjustments

| From → To | Adjustment |
|-----------|------------|
| New → Like New/Open Box | −10% to −20% |
| New → Very Good | −20% to −40% |
| New → Good | −40% to −60% |
| Each tier step down | ~−10% to −20% |
| Missing accessories | −10% to −30% (varies by item) |
| With original packaging | +5% to +10% |
| Collectibles | Condition can create **10× price difference** |

### Step 5: Add Shipping
We list with free shipping, so add the evaluator's `shipping.estimatedServiceCost` to the adjusted baseline.

### Step 6: Apply Strategy and Round
- Position against the median using **one** strategy from the table below. Competitive = at or up to 15% below median; Premium + Best Offer = 10–20% above median. That 10–20% **is** the Best Offer negotiation buffer. Do not add a second buffer on top.
- Apply psychological pricing ($41.30 → $39.95 or $44.99)

### Step 7: Best Offer Floor and Net Proceeds
- `auto_decline_below` ≈ 80–85% of the list price, and never below your minimum acceptable price
- eBay's fees are charged on the total the buyer pays, including shipping:
  ```
  net = price − price × FVF − 0.40 − shipping_cost
  ```
  FVF is 13.6% in most categories without a store (Basic store: 12.7%, most consumer electronics 9.35%, books/media 15.3%). The per-order fee is $0.40, or $0.30 for orders ≤ $10.
- Report `net` at both the list price and the floor

## Price Output Format

```json
{
  "pricing": {
    "recommended_price": 89.99,
    "min_price": 75.00,
    "max_price": 110.00,
    "strategy": "COMPETITIVE",
    "format": "FIXED_PRICE",
    "best_offer_enabled": true,
    "auto_decline_below": 70.00,
    "confidence": 0.85
  },
  "comps": {
    "count": 12,
    "median": 85.00,
    "range": [65.00, 120.00],
    "data_freshness_days": 60,
    "source": "terapeak"
  }
}
```

## Low-Comp Strategies (< 5 Sold Comps)

Follow this hierarchy:
1. **Broaden search** — remove color, variant, or specific modifiers
2. **Extend time window** — 90 days → 365 days via Terapeak
3. **Check alternative platforms** — Mercari, Poshmark (both have "Sold" filters), StockX, Discogs
4. **Use active listing prices** as ceiling only — typically 30–50% higher than actual sold prices
5. **Truly unique items** — list as auction starting at your minimum acceptable price

## Professional Reseller Pricing Strategies

| Strategy | When to Use | How |
|----------|-------------|-----|
| **Competitive** | Most items | Price at or 5-15% below median sold price |
| **Premium + Best Offer** | Valuable/rare items | 10-20% above median, enable Best Offer |
| **7-14-30 drops** | Slow sellers | Start at market, -10% at 14d, -15% at 30d |

## Key Metric: Sell-Through Rate

```
Sell-Through Rate = (Items sold in 90d) / (Items sold + Currently listed) × 100
```
- **< 30%**: Oversupplied category — price lower
- **30-60%**: Healthy demand — price at median
- **> 60%**: Strong demand — can price above median
