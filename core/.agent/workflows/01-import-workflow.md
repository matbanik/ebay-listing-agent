---
description: Download and process images from Google Photos for eBay listing
---

# 01 — Import Workflow

Prepare raw product images for the listing pipeline. Images are **not** uploaded to eBay here; the Lister uploads them once the Curator has fixed the final order (hero first).

## Steps

### 1. Download Images

Download product photos from Google Photos:
- Go to https://photos.google.com/
- Select all photos of the product(s) to list
- Click **Download** (⬇️ icon or Shift+D)
- Save to `raw_data/` in the repo (subfolders are fine, e.g. `raw_data/images/`)

> **Tip**: Group photos by product before downloading. Name download batches clearly.

### 2. Process Images for eBay

// turbo
```bash
python tools/process_images.py --input raw_data/
```

The script (ImageMagick 7 required):
- Searches `raw_data\` recursively, mirroring subfolders into `raw_data\processed\`
- Resizes down to 1600px longest side (never upscales) and pads to a white square
- Flattens transparency, auto-orients from EXIF
- **Strips EXIF/GPS metadata** (keeps the ICC color profile), saves JPEG quality 92
- Rejects images under 500px (eBay minimum) and flags output-name collisions
- Skips images already processed; add `--force` to redo them

### 3. Organize Into Listing Folder

List the processed images, then copy a product's images into its listing folder:

// turbo
```bash
python tools/organize_raw.py --list
python tools/organize_raw.py --move images/IMG_1234.jpg images/IMG_1235.jpg --to "Sony WH-1000XM5"
```

This creates `listings\{slug}\{slug}-01.jpg`, `-02.jpg`, … (slug derived from the name). Running it again for the same slug continues the numbering instead of overwriting. Run it without arguments for interactive grouping.

### 4. Review Processed Images

Visually inspect the listing folder:
- Check that products are clearly visible
- Verify no important details were cropped
- Ensure colors look accurate
- Remove blurry or duplicate images (back up first; see AGENTS.md)
- **Blur sensitive text** (license/authentication codes, registration keys, Wi-Fi passwords, names/addresses) on labels and screenshots with `tools/redact_text.py` (`redact-images` skill), then crop-check each redacted spot. This must happen before the Lister uploads anything

### 5. Proceed to Curation

Run `/curator-workflow` to identify the product and pick the hero image.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| HEIC/AVIF from iPhone | ImageMagick reads them natively; nothing extra to install |
| Images too small (<500px) | Cannot upscale — retake photos |
| Metadata JSON files (Takeout) | Ignored. Sidecars are named `IMG_1234.jpg.supplemental-metadata.json` (often truncated, e.g. `.supplemental-me.json`) |
| "output name collides" | Two source files with the same name in one folder (e.g. `a.png` and `a.jpg`); rename one |
