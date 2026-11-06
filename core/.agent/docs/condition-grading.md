# eBay Condition Grading Reference

## Universal Rule: Grade One Level Down When Uncertain

> **When in doubt, grade conservatively.** Over-grading leads to INAD claims, forced returns, and negative feedback. If the AI is unsure between "Very Good" and "Good," list as "Good."
> The Curator applies this **once**. The Evaluator does not drop the grade a second time; if it disagrees, it flags `changed_from_curator` for human review.

Always include the disclaimer: *"Condition assessed from photos only."* Never write "tested", "fully functional" or "confirmed working" unless the seller confirmed it (`condition.tested_by_human: true` in evaluator-output.json).

`API Enum` is the Inventory API `ConditionEnum` value sent in `createOrReplaceInventoryItem`. The `Grade` column is what buyers see, and it varies by category.

## Hard Goods / Electronics

| ID | API Enum | Grade | Description |
|----|----------|-------|-------------|
| 1000 | NEW | New | Sealed, all original packaging, tags, accessories |
| 1500 | NEW_OTHER | New (Other) / Open box | New but opened, or missing original packaging |
| 1750 | NEW_WITH_DEFECTS | New with defects | New/unused but has cosmetic imperfections |
| 2000-2030 | CERTIFIED_REFURBISHED, EXCELLENT_/VERY_GOOD_/GOOD_REFURBISHED | Refurbished tiers | Refurbished Program only; not for ordinary used items |
| 2500 | SELLER_REFURBISHED | Seller refurbished | Restored to working order by the seller |
| 2750 | LIKE_NEW | Like New | Used but appears new, negligible wear |
| 3000 | USED_EXCELLENT | Used | Generic used; the **only** used grade many electronics categories accept |
| 4000 | USED_VERY_GOOD | Very Good | Minor cosmetic wear |
| 5000 | USED_GOOD | Good | Normal wear consistent with regular use |
| 6000 | USED_ACCEPTABLE | Acceptable | Significant wear or cosmetic damage |
| 7000 | FOR_PARTS_OR_NOT_WORKING | For parts or not working | Non-functional, damaged, or incomplete |

## Clothing & Accessories

| ID | API Enum | Grade (as displayed) | Description |
|----|----------|-------|-------------|
| 1000 | NEW | New with tags | Unworn, all tags attached |
| 1500 | NEW_OTHER | New without tags | Unworn, tags removed |
| 1750 | NEW_WITH_DEFECTS | New with defects | Unworn, has flaws |
| 2990 | PRE_OWNED_EXCELLENT | Pre-owned - Excellent | Like-new, virtually zero wear visible |
| 3000 | USED_EXCELLENT | Pre-owned - Good | Expected light wear from regular use |
| 3010 | PRE_OWNED_FAIR | Pre-owned - Fair | Noticeable flaws: stains, tears, fading |

> There are no `NEW_WITH_TAGS`, `NEW_WITHOUT_TAGS`, `PRE_OWNED_GOOD`, `VERY_GOOD`, `GOOD`, `ACCEPTABLE`, `FOR_PARTS` or `BRAND_NEW` enum values. The API rejects them.

## Category-Specific Lookup

> **Condition IDs are NOT universal.** Different categories accept different subsets.
> Always validate by querying `getItemConditionPolicies` or `getItemAspectsForCategory` for the target category before listing.

## AI Condition Assessment Protocol

1. **OCR PASS** — Scan for manufacturer tags, serial numbers, labels
2. **SURFACE SCAN** — Scratches, scuffs, discoloration, staining, fading
3. **STRUCTURAL CHECK** — Cracks, dents, bends, chips, missing parts
4. **WEAR PATTERN** — High-contact areas: edges, buttons, hinges, ports
5. **COMPLETENESS** — Accessories, packaging, cables present?
6. **GRADE** — Map to condition; drop one level only if uncertain (Curator only)

## Confidence-Based Routing

| Confidence | Action |
|------------|--------|
| ≥ 0.85 | Proceed |
| 0.70 – 0.84 | Proceed, note the uncertainty in the report |
| < 0.70 | Route to human review |
| Evaluator disagrees with Curator | Always flag for human review |
