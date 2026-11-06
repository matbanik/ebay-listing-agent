---
name: redact-images
description: Find and blur sensitive text in listing photos (license/authentication codes, registration keys, MAC addresses, shipping-label names/addresses) using local OCR (RapidOCR), then verify nothing is still readable.
---

# Redact Images Skill

Blur sensitive text in listing photos before they are uploaded to eBay. Run it during import, after `organize_raw.py` has copied the images into `listings/{slug}/` and before the Lister uploads them.

## When to Use

Scan every label close-up and screenshot for:

| Redact | Why |
|--------|-----|
| Authentication / registration / license codes (SonicWall, Fortinet, Cisco, Microsoft keys) | A buyer of a *different* unit could register yours; vendors tie support/licensing to these |
| Wi-Fi passwords, admin passwords, PINs on stickers | Direct access |
| Names, addresses, phone numbers, tracking numbers | Personal data |
| IMEIs, MAC addresses (when asked) | Blacklisting / spoofing risk |

**Keep visible**: brand, model, MPN, product code, serial number (buyers use it to check warranty/support status), FCC ID, voltage/ratings. Serial numbers stay unless the user asks otherwise.

## Tooling

`tools/redact_text.py`: RapidOCR (PaddleOCR models on ONNX Runtime) + OpenCV.
- Local and CPU-only: no Tesseract install, no torch, no cloud upload of the photos
- OCR runs at 1× and 2× (upscaling catches small label text the 1× pass misses)
- Fuzzy matching folds OCR confusables (8/B, 0/O/Q, 1/I/L, 5/S...) so a garbled read like `A812-CO34` still matches `AB12-CD34`
- Writes in place (JPEG Q92, ICC kept, no EXIF). Unredacted originals remain in `raw_data/processed/`
- Re-OCRs each written image and exits 1 if a `--text`/`--regex` target is still readable

```bash
pip install rapidocr_onnxruntime opencv-python Pillow numpy
```

## Commands

```bash
# Known value, plus whatever follows the label (covers screenshots where OCR splits it)
python tools/redact_text.py listings/{slug}/{slug}-0{2,5}.jpg \
    --text AB12-CD34 --after-label "Authentication Code"

# Preview the regions without writing
python tools/redact_text.py listings/{slug}/*.jpg --text AB12-CD34 --dry-run

# Pattern instead of a known value (exact regex on the raw OCR text)
python tools/redact_text.py listings/{slug}/*.jpg --regex "[0-9A-F]{2}(:[0-9A-F]{2}){5}"

# OCR missed it: give the region by hand (x,y,w,h in image pixels, 1600px images)
python tools/redact_text.py listings/{slug}/{slug}-03.jpg --box 400,300,180,40
```

Styles: `--style blur` (default; kernel as large as the region, 3 passes, not reversible), `pixelate`, `box` (flat median fill).

## Procedure

1. **Find the values.** Read the codes off the screenshots/labels yourself (or with `--dry-run`, which prints every OCR match). Use both `--text <value>` and `--after-label "<label>"`: the label catches places where OCR mangles the value.
2. **Run** on every image that shows the value: label close-ups, wide shots where the label is legible, and screenshots (dashboards often show the code in two panels).
3. **Check the exit code.** Exit 1 means a target can still be read; add a `--box` for that spot and run again on that image.
4. **Look at it.** OCR verification can miss a *partial* leak (one surviving character next to the blur). Crop each redacted area and view it:
   ```bash
   magick listings/{slug}/{slug}-04.jpg -crop 600x200+550+560 +repage -resize 200% scratch/crop.png
   ```
   Every character of the value must be gone. If an edge character survives, restore that image from `raw_data/processed/` and re-run (redacting an already-blurred image gives OCR nothing to anchor on), or cover it with `--box`.
5. **Record it** in the curator report's notes ("authentication code blurred in -03, -04, -06, -07") so the Lister/Reviewer knows the blur is intentional.

## Gotchas

- Redact **before** `/lister-workflow` uploads the images: once on eBay's EPS CDN, a URL can't be recalled.
- Re-running on an image that is already redacted usually finds nothing. To redo an image, copy its original back from `raw_data/processed/` first.
- Span positions inside a long OCR line are estimated from average character width; the tool widens them by one character on each side. Wide labels with narrow values (or the reverse) can still be off, which is why step 4 exists.
- Don't blur so much that the listing looks like it hides damage: blur only the value, not the whole label.
