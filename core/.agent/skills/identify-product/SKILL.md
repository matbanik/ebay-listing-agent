---
name: identify-product
description: Use AI vision models to identify brand, model, condition, and category from product photos. Supports tiered model strategy and structured JSON output.
---

# Identify Product Skill

Analyze product photos with AI vision to extract brand, model, condition grade, and category. Designed for the Curator agent.

## Model Strategy (Tiered)

| Tier | Model | Use When | Cost |
|------|-------|----------|------|
| **Primary** | Gemini Flash | All items — initial triage + ID | ~$0.10/M input tokens |
| **Second opinion** | Claude (the agent running the workflow) | Nuanced condition, conflicting evidence | Higher, for edge cases only |
| **Verification** | Google Lens API (SerpApi/Apify) | Deterministic product matching | Per-query |

## Prompt Structure

Use "describe first, then extract" in a single turn:

### System Prompt
```
You are an expert product identifier for eBay listings. You identify consumer products from photos with high accuracy. When uncertain about any field, return null rather than guessing. Never hallucinate brand names, model numbers, or features not visible in the images.
```

### User Prompt Template
```
Analyze the following {N} images of the SAME product.

Step 1 — VISUAL DESCRIPTION:
Describe what you see in detail: shape, color, materials, visible text/logos, labels, serial numbers, and any wear or damage.

Step 2 — STRUCTURED EXTRACTION:
Return a JSON object with these fields:

{
  "product": {
    "category": "string — eBay category path (e.g., 'Electronics > Headphones > Over-Ear')",
    "type": "string — product type",
    "brand": "string — or 'Unbranded' if no brand visible",
    "model": "string or null",
    "mpn": "string or null — manufacturer part number",
    "upc": "string or null — if barcode visible",
    "color": "string",
    "material": "string or null",
    "key_features": ["string array"],
    "visible_text": ["string array — all readable text/markings"]
  },
  "condition": {
    "grade": "ConditionEnum: NEW | NEW_OTHER | LIKE_NEW | USED_EXCELLENT | USED_VERY_GOOD | USED_GOOD | USED_ACCEPTABLE | FOR_PARTS_OR_NOT_WORKING (see references/condition-codes.json)",
    "condition_id": null,
    "notes": "string — specific defect descriptions",
    "confidence": 0.0-1.0
  },
  "identification_confidence": 0.0-1.0,
  "identification_method": "brand_visible | model_visible | visual_match | uncertain",
  "suggested_title": "string — max 80 chars, eBay SEO format",
  "suggested_slug": "string — lowercase-hyphenated folder name",
  "additional_photos_needed": ["string array — what angles are missing"]
}
```

## Chain-of-Thought Prompt for Condition

```
Analyze the condition of this item systematically:

1. OCR PASS: Scan for all visible text — manufacturer tags, serial numbers, labels, logos.
2. SURFACE SCAN: Look for scratches, scuffs, discoloration, staining, fading.
3. STRUCTURAL CHECK: Look for cracks, dents, bends, chips, missing parts.
4. WEAR PATTERN: Assess high-contact areas — edges, buttons, hinges, ports.
5. COMPLETENESS: What accessories, packaging, cables are visible?
6. GRADE: Map to eBay condition using conservative bias (when in doubt, grade ONE LEVEL DOWN — once; the Evaluator does not repeat it).
```

## Conservative Grading Rule

> **Universal seller consensus: "When in doubt, grade low."**
> Over-grading leads to INAD (Item Not As Described) claims, forced returns, negative feedback.
> If vision model assesses "Very Good," suggest "Good" as listing condition.
> Flag any item with condition confidence < 0.70 for human review.
> Always note: "Condition assessed from photos only; not tested for functionality."

## eBay Condition Codes (Category-Aware)

### Hard Goods / Electronics
| ID | Enum | Grade |
|----|------|-------|
| 1000 | NEW | Brand new, sealed, all tags |
| 1500 | NEW_OTHER | New but opened, or missing packaging |
| 1750 | NEW_WITH_DEFECTS | Unused but cosmetic flaws |
| 2750 | LIKE_NEW | Used, appears new, minimal wear |
| 3000 | USED_EXCELLENT | "Used" — the only used grade most electronics/hard-goods categories accept |
| 4000 | USED_VERY_GOOD | Minimal wear (mainly Books/Media categories) |
| 5000 | USED_GOOD | Moderate wear (mainly Books/Media categories) |
| 6000 | USED_ACCEPTABLE | Heavy wear (mainly Books/Media categories) |
| 7000 | FOR_PARTS_OR_NOT_WORKING | Non-functional, or function unknown and doubtful |

Grades describe **cosmetic** condition. Photos can't show that an item works, so never describe an item as "functional" or "tested" unless the seller says they tested it.

### Clothing / Accessories (2025 Overhaul)
| ID | Enum | Grade |
|----|------|-------|
| 1000 | NEW | New with tags |
| 1500 | NEW_OTHER | New without tags |
| 2990 | PRE_OWNED_EXCELLENT | Like-new, practically zero wear |
| 3000 | USED_EXCELLENT | Shown as "Pre-owned - Good": light wear, minor flaws |
| 3010 | PRE_OWNED_FAIR | Visible flaws, heavy wear |

> **Important**: Condition IDs are NOT universal. Query `getItemAspectsForCategory` or `getItemConditionPolicies` via Taxonomy/Metadata API to get valid IDs for the target category.

## Confidence-Based Routing

| Confidence | Action |
|------------|--------|
| ≥ 0.85 | Proceed to Evaluator |
| 0.70 – 0.84 | Proceed with flag for Evaluator to verify |
| < 0.70 | Stop and ask the user (AGENTS.md "Ask First"); a second model's opinion can go in the question, but it does not replace the user's answer |

## Edge Cases

- **Unbranded items**: Set brand to `"Unbranded"` (eBay convention, never guess)
- **Bundles**: Identify each item individually, provide bundle summary
- **Vintage**: Estimate era/decade, note if possibly reproduction, use Vintage subcategory (20+ years)
- **Damaged items**: Photograph every defect from multiple angles with scale reference
- **Generic items**: Use Google Lens API for cross-reference before defaulting to category-only ID
