---
description: Run full listing pipeline for all items in raw_data
---

# 06 — Batch Workflow

Process all unprocessed images through the full pipeline.

## Steps

### 1. Import All Images

Run `/import-workflow` for all images in `raw_data/`:

```bash
python tools/process_images.py --input raw_data/
```

### 2. Identify and Group Products

Review processed images and group by product:
- Use AI vision to identify each distinct product
- Copy each product's images into its own listing folder:

```bash
python tools/organize_raw.py --list
python tools/organize_raw.py --move images/IMG_1.jpg images/IMG_2.jpg --to "{product name}"
```

### 3. Run Pipeline Per Item

For each identified product, run sequentially:

```
/curator-workflow    → Identify and organize
/evaluator-workflow  → Validate and price
/lister-workflow     → Upload images, create unpublished offer
```

### 4. Batch Review

Present all draft listings to human for review:

```
┌─────────────────────────────────────────────┐
│ Batch Listing Review                        │
├─────┬──────────────────────┬────────┬───────┤
│  #  │ Product              │ Price  │ Status│
├─────┼──────────────────────┼────────┼───────┤
│  1  │ Sony WH-1000XM5      │ $189   │ Draft │
│  2  │ Nintendo Switch Lite  │ $129   │ Draft │
│  3  │ Kindle Paperwhite    │ $79    │ Draft │
└─────┴──────────────────────┴────────┴───────┘

Review each listing and approve/reject individually.
Include a Flags column (> $200, low confidence, < 5 comps, condition disagreement).
```

### 5. Publish Approved Listings

For each listing the human approved in this session, run `/review-workflow` step 4 (publish). Never publish unlisted or unapproved items, and give items > $200 their own explicit approval.

## Notes

- Process items one at a time through the AI vision step (curator)
- Price discovery can be parallelized with web searches
- Always wait for human approval before publishing any listing
- Track batch progress in `.agent/context/current-focus.md` (not in this workflow file)
