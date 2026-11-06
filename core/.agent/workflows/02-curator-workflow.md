---
description: AI product identification and image organization from raw photos
---

# 02 — Curator Workflow

Identify products from images, assess condition, organize into listing folders, and produce structured output for the Evaluator.

**Skills used**: `identify-product`, `process-images`

## Prerequisites

- Processed images copied into `listings/{item-slug}/` as `{item-slug}-NN.jpg` (run `/import-workflow` first)

## Steps

### 1. List the Listing's Images

```bash
ls listings/{item-slug}/*.jpg
```

### 2. Run Quality Checks (process-images skill)

For each image, run blur and dark detection per `process-images` SKILL.md:
- Reject if Laplacian variance < 100 (blurry)
- Reject if mean grayscale < 60 (too dark)
- Optionally run background removal (rembg) on the hero candidate

### 3. Analyze Images with AI Vision (identify-product skill)

Use the prompt template from `identify-product` SKILL.md:
- Product identification (brand, model, category, features). Never guess a brand or model number that is not visible or verifiable.
- Condition assessment using the 6-step protocol. Grade one level down **only when uncertain**, and only here (the Evaluator does not grade down again).
- Use real Inventory API `ConditionEnum` values (see `identify-product/references/condition-codes.json`). For used electronics and other hard goods this is usually `USED_EXCELLENT` (3000, shown as "Used"); `USED_VERY_GOOD`/`USED_GOOD` exist mainly in Books/Media.
- Hero shot selection
- Slug suggestion

Condition notes must say **"Condition assessed from photos only."** Do not write "tested" or "working": a lit LED in a photo is not a function test.

**If any confidence < 0.70**: stop and ask the user (AGENTS.md "Ask First").

### 4. Put the Hero Image First

The first image uploaded becomes the eBay gallery photo, so file order **is** listing order. Rename files so the hero is `{item-slug}-01.jpg`:

```
{item-slug}-01.jpg  (hero shot)
{item-slug}-02.jpg  (back view)
{item-slug}-03.jpg  (defect close-ups)
...
```

After renaming, set `images.hero_index` to `0` in curator-output.json and list `processed_paths` in the new order.

### 5. Generate Curator Output

Create **both**:
1. `listings/{item-slug}/curator-report.md` — human-readable summary (template: `templates/curator-report-template.md`)
2. `listings/{item-slug}/curator-output.json` — typed contract per `schemas/curator-output.json`

The JSON output is the machine-parseable handoff to the Evaluator.

### 6. Determine Routing

| Condition | Route |
|-----------|-------|
| All confidence ≥ 0.85 | Proceed to `/evaluator-workflow` |
| Any confidence 0.70–0.84 | Proceed; note the uncertainty in `review_reasons` |
| Any confidence < 0.70 | Stop and ask the user for manual ID |

## Quality Checklist

- [ ] Product correctly identified (brand, model), nothing guessed
- [ ] Condition grade assigned with 6-step protocol, valid ConditionEnum value
- [ ] Graded one level down only where uncertain
- [ ] "Condition assessed from photos only" in the notes; no "tested" claims
- [ ] All relevant images included, blurry/dark rejected
- [ ] Hero shot renamed to `-01`, `hero_index` = 0
- [ ] Slug follows convention (lowercase, hyphens)
- [ ] Both curator-report.md and curator-output.json created
- [ ] JSON validates against schemas/curator-output.json
