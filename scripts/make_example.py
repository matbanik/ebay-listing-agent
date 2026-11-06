"""
Regenerate examples/acme-hl300-headlamp/: one synthetic listing with every
pipeline artifact filled in (curator, evaluator, Lister payloads, reports).

Everything is invented: "Acme" is a placeholder brand, the comps are made up,
and the photos are drawn by this script, so they hold no EXIF at all. IDs come
from core/account.example.json. Category 106984 (Headlamps) and its aspects and
condition enums are real eBay US values (checked 2026-11-06).

    python scripts/make_example.py
    cd core && EBAY_ACCOUNT_FILE=account.example.json python tools/validate_payload.py ../examples/acme-hl300-headlamp/
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw

PKG = Path(__file__).resolve().parent.parent
SLUG = "acme-hl300-headlamp"
OUT = PKG / "examples" / SLUG
ACCOUNT = json.loads((PKG / "core" / "account.example.json").read_text(encoding="utf-8"))

TITLE = "Acme HL300 LED Headlamp 300 Lumen USB-C Rechargeable Red Light Black Used"
PRICE, FLOOR, LOW, HIGH = 24.99, 20.00, 21.99, 27.99
DISCLAIMER = "Condition assessed from photos only."
CONDITION_TEXT = ("Pre-owned. The lens is clear with no visible cracks. The strap is clean and still elastic. "
                  "The housing has light scuffs on the top edge. Not tested by the seller. " + DISCLAIMER)
SPECIFICS = {
    "Brand": "Acme", "Model": "HL300", "MPN": "HL300-BK", "Type": "Headlamp", "Power Source": "USB",
    "Lighting Technology": "LED", "Color": "Black", "Material": "ABS",
    "Features": ["Rechargeable", "Waterproof"],
}

S = "font-family:Arial,Helvetica,sans-serif;max-width:800px;margin:0 auto;padding:0 12px;font-size:16px;line-height:1.5;color:#222"
H3 = "font-size:18px;margin:18px 0 6px"
LI = "margin:3px 0"


def ul(items):
    return "<ul style='padding-left:20px;margin:0'>" + "".join(f"<li style='{LI}'>{i}</li>" for i in items) + "</ul>"


DESCRIPTION = (
    f"<div style='{S}'><h2 style='font-size:22px;margin:8px 0'>Acme HL300 Rechargeable LED Headlamp, Black</h2>"
    "<p>Pre-owned <strong>Acme HL300</strong> headlamp with white and red LED modes and a built-in USB-C battery.</p>"
    f"<h3 style='{H3}'>Specifications</h3>"
    + ul(["Output: up to 300 lumens (manufacturer rating)", "Modes: high, low, red, strobe",
          "Charging: USB-C (cable not included)", "Water resistance: IPX4 (manufacturer rating)",
          "Tilting lamp head, adjustable elastic strap"])
    + f"<h3 style='{H3}'>What's Included</h3>"
    + ul(["Headlamp with strap", "No box, cable or paperwork. Only the items pictured are included"])
    + f"<h3 style='{H3}'>Condition</h3>"
    f"<p>{CONDITION_TEXT.replace(DISCLAIMER, '<em>' + DISCLAIMER + '</em>')}</p></div>"
)


def draw_photo(path, angle):
    """A plain studio-style drawing of a headlamp on white, 1600x1600."""
    im = Image.new("RGB", (1600, 1600), "white")
    d = ImageDraw.Draw(im)
    d.ellipse((260, 520, 1340, 1180), outline=(40, 40, 40), width=46)           # strap
    body = (560, 600, 1040, 900) if angle == 0 else (600, 640, 1000, 880)
    d.rounded_rectangle(body, radius=70, fill=(28, 28, 30))                     # housing
    cx, cy = (body[0] + body[2]) // 2, (body[1] + body[3]) // 2
    d.ellipse((cx - 110, cy - 110, cx + 110, cy + 110), fill=(210, 215, 220))   # lens
    d.ellipse((cx - 60, cy - 60, cx + 60, cy + 60), fill=(250, 250, 235))
    d.ellipse((body[2] - 70, body[1] + 30, body[2] - 30, body[1] + 70), fill=(190, 30, 30))  # red LED
    if angle == 1:
        d.line((body[0] + 60, body[1] + 8, body[0] + 220, body[1] + 4), fill=(120, 120, 120), width=6)  # scuff
    im.save(path, "JPEG", quality=88)  # Pillow writes no EXIF unless asked


def write(name, data):
    path = OUT / name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    images = [f"{SLUG}-01.jpg", f"{SLUG}-02.jpg"]
    for i, name in enumerate(images):
        draw_photo(OUT / name, i)
    urls = [f"https://i.ebayimg.com/images/g/EXAMPLE{n:02d}/s-l1600.jpg" for n in (1, 2)]
    pol, seller = ACCOUNT["policies"], ACCOUNT["seller"]

    write("curator-output.json", {
        "product": {
            "category": "Sporting Goods > Camping & Hiking > Flashlights, Lanterns & Lights > Headlamps",
            "type": "LED Headlamp", "brand": "Acme", "model": "HL300", "mpn": "HL300-BK", "upc": None,
            "color": "Black", "material": "ABS housing, elastic strap",
            "key_features": ["300 lumen white LED", "Red light mode", "USB-C rechargeable", "Tilting head"],
            "visible_text": ["ACME", "HL300", "USB-C"],
            "identification_confidence": 0.9, "identification_method": "model_visible"},
        "condition": {"grade": "USED_EXCELLENT", "condition_id": 3000, "confidence": 0.8,
                      "tested_by_human": False, "notes": CONDITION_TEXT,
                      "defects": ["Light scuffs on the top edge of the housing"]},
        "images": {"processed_paths": images, "hero_index": 0, "quality_scores": [182.4, 164.0],
                   "rejected": []},
        "metadata": {"curator_timestamp": "2026-11-06T12:00:00Z", "slug": SLUG, "model_used": "example",
                     "requires_human_review": False, "review_reasons": []},
        "suggested_title": TITLE,
        "additional_photos_needed": ["Charging port close-up", "Lamp lit (if the seller can test it)"],
    })

    write("evaluator-output.json", {
        "identification": {
            "confirmed": True, "ebay_product_id": None, "title": TITLE, "category_id": "106984",
            "category_name": "Sporting Goods > Camping & Hiking > Flashlights, Lanterns & Lights > Headlamps",
            "brand": "Acme", "model": "HL300", "original_msrp": 39.99,
            "official_source_url": "https://example.com/acme-hl300", "upc": "Does Not Apply"},
        "pricing": {"recommended_price": PRICE, "min_price": LOW, "max_price": HIGH,
                    "strategy": "COMPETITIVE", "format": "FIXED_PRICE", "best_offer_enabled": True,
                    "auto_decline_below": FLOOR, "confidence": 0.75},
        "comps": {
            "count": 5, "median": 23.5, "range": [18.0, 29.0], "data_freshness_days": 90,
            "source": "Example data (invented). Real runs use eBay sold search or Terapeak; prices are delivered (item + shipping)",
            "sell_through_rate": None,
            "items": [
                {"title": "Acme HL300 Headlamp Black", "price": 18.0, "condition": "Used, worn strap",
                 "date": "2026-10-02", "type": "AUCTION", "url": "https://example.com/sold/1"},
                {"title": "Acme HL300 LED Headlamp USB-C", "price": 22.0, "condition": "Used",
                 "date": "2026-10-11", "type": "BIN", "url": "https://example.com/sold/2"},
                {"title": "ACME HL300 300lm Headlamp", "price": 23.5, "condition": "Used",
                 "date": "2026-10-20", "type": "BIN", "url": "https://example.com/sold/3"},
                {"title": "Acme HL300 Rechargeable Headlamp + Cable", "price": 26.0, "condition": "Used, with cable",
                 "date": "2026-10-28", "type": "BIN", "url": "https://example.com/sold/4"},
                {"title": "Acme HL300 Headlamp Open Box", "price": 29.0, "condition": "New other",
                 "date": "2026-11-01", "type": "BIN", "url": "https://example.com/sold/5"}]},
        "condition": {"final_grade": "USED_EXCELLENT", "condition_id": 3000, "changed_from_curator": False,
                      "change_reason": None, "condition_description": CONDITION_TEXT, "tested_by_human": False},
        "listing_specs": {"description_html": DESCRIPTION, "item_specifics": SPECIFICS,
                          "shipping_recommendation": "FREE_DOMESTIC", "return_policy": "30_DAY_BUYER_PAYS",
                          "duration": "GTC"},
        "shipping": {"estimatedWeightLb": 0.5, "estimatedServiceCost": 5.0,
                     "estimationSource": "Headlamp ~3 oz packed in a small padded mailer, under 8 oz; USPS Ground Advantage",
                     "notes": "Price includes the shipping estimate (free shipping, cost baked in)."},
        "approval": {"auto_listable": False, "requires_human_review": True,
                     "review_reasons": ["Publishing needs explicit human approval"],
                     "overall_quality_score": 0.8},
        "metadata": {"evaluator_timestamp": "2026-11-06T12:30:00Z", "slug": SLUG},
    })

    write("image-urls.json", urls)
    write("inventory-item.json", {
        "product": {"title": TITLE, "description": DESCRIPTION,
                    "aspects": {k: v if isinstance(v, list) else [v] for k, v in SPECIFICS.items()},
                    "upc": ["Does Not Apply"], "imageUrls": urls},
        "condition": "USED_EXCELLENT", "conditionDescription": CONDITION_TEXT,
        "availability": {"shipToLocationAvailability": {"quantity": 1}},
    })
    write("offer.json", {
        "sku": SLUG, "marketplaceId": seller["marketplace"], "format": "FIXED_PRICE", "listingDuration": "GTC",
        "availableQuantity": 1, "categoryId": "106984", "merchantLocationKey": seller["merchantLocationKey"],
        "pricingSummary": {"price": {"value": f"{PRICE:.2f}", "currency": "USD"}},
        "listingPolicies": {"fulfillmentPolicyId": pol["fulfillment"], "paymentPolicyId": pol["payment"],
                            "returnPolicyId": pol["return"],
                            "bestOfferTerms": {"bestOfferEnabled": True,
                                               "autoDeclinePrice": {"value": f"{FLOOR:.2f}", "currency": "USD"}}},
        "listingDescription": DESCRIPTION,
    })

    write("curator-report.md", f"""# Curator Report: Acme HL300 Headlamp

**Date**: 2026-11-06
**Status**: pending-evaluation

## Product Identity

- **Name**: Acme HL300 LED Headlamp
- **Brand**: Acme (printed on the housing)
- **Model**: HL300 (printed on the housing)
- **Category**: Sporting Goods > Camping & Hiking > Flashlights, Lanterns & Lights > Headlamps
- **Key Features**: 300 lumen white LED, red mode, USB-C rechargeable, tilting head

## Condition Assessment

- **Grade**: USED_EXCELLENT (3000, shown as "Used")
- **Visible Wear**: light scuffs on the top edge of the housing
- **Defects**: none beyond the scuffs
- **Completeness**: headlamp and strap only; no cable, box or paperwork

## Images

| # | Filename | Description |
|---|----------|-------------|
| 1 | {images[0]} | Hero shot (front) |
| 2 | {images[1]} | Angle showing the scuff |

## Curator Notes

Synthetic example. Not tested by the seller, so the listing makes no "working" claim. {DISCLAIMER}
""")
    write("evaluator-report.md", f"""# Evaluator Report: Acme HL300 Headlamp

**Date**: 2026-11-06
**Status**: pending-listing

## Validated Identity

- **Official Name**: Acme HL300 Rechargeable LED Headlamp
- **Manufacturer**: Acme (placeholder brand for this example)
- **Model Number**: HL300 (MPN HL300-BK)
- **Original MSRP**: $39.99
- **Source**: https://example.com/acme-hl300

## Price Discovery

### Recently Sold on eBay (last 90 days; invented for the example)

| Date | Condition | Price | Type |
|------|-----------|-------|------|
| 2026-10-02 | Used, worn strap | $18.00 | Auction |
| 2026-10-11 | Used | $22.00 | BIN |
| 2026-10-20 | Used | $23.50 | BIN |
| 2026-10-28 | Used, with cable | $26.00 | BIN |
| 2026-11-01 | New other | $29.00 | BIN |

**Sold Summary**: Median $23.50, Range $18–$29, N=5 (delivered prices)

### Recommended Pricing

- **Suggested Price**: ${PRICE} (comps median plus ~$5 ground shipping, which we cover)
- **Min / Max**: ${LOW} / ${HIGH}
- **Listing Format**: Buy It Now with Best Offer, auto-decline below ${FLOOR:.2f}
- **Rationale**: Used, no cable: priced in the middle of the used comps once shipping is included

## Listing Recommendations

- **Suggested Title**: {TITLE}
- **Best Category**: Headlamps (106984)
- **Shipping Suggestion**: Free (cost baked into the price)
""")
    write("listing-draft.md", f"""# Listing Draft: Acme HL300 Headlamp

**Date**: 2026-11-06
**Status**: draft (synthetic example; never sent to eBay)
**eBay Offer ID**: (set by `create-offer`)
**eBay Item ID**: (set by `publish`)

## Listing Details

- **Title**: {TITLE}
- **Category**: Headlamps (106984)
- **Condition**: USED_EXCELLENT (3000, "Used")
- **Condition Description**: {CONDITION_TEXT}
- **Price**: ${PRICE} (Best Offer, auto-decline below ${FLOOR:.2f})
- **Format**: Buy It Now
- **Shipping**: Free (`policies.fulfillment`)
- **Returns**: 30-day, buyer pays (`policies.return`)
- **Duration**: GTC

## Item Specifics

| Aspect | Value |
|--------|-------|
""" + "".join(f"| {k} | {', '.join(v) if isinstance(v, list) else v} |\n" for k, v in SPECIFICS.items()) + f"""
## Images Uploaded

| # | Filename | eBay URL |
|---|----------|----------|
| 1 | {images[0]} | {urls[0]} |
| 2 | {images[1]} | {urls[1]} |

## Review Checklist

- [x] Title accurate and ≤80 chars
- [x] Price validated against sold comps
- [x] Item specifics complete
- [x] Description honest; photo-only disclaimer present; no "tested" claim
- [x] Shipping and return policy from account.json
- [ ] **Human approved** (required before `publish --confirm`)

## Listing History

| Date | Action | Notes |
|------|--------|-------|
| 2026-11-06 | Draft created | Synthetic example |
""")
    print(f"wrote {OUT.relative_to(PKG)} ({len(list(OUT.iterdir()))} files)")


if __name__ == "__main__":
    main()
