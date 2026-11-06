# eBay Image Requirements & Processing Guide

## eBay Image Specs (2025-2026)

| Spec | Requirement |
|------|-------------|
| **Minimum** | 500×500px |
| **Recommended** | 1600×1600px |
| **Maximum** | 9000×9000px, 12MB |
| **Format** | JPEG preferred, PNG, WebP, HEIC, AVIF accepted |
| **Aspect** | Square 1:1 (or 4:5 for mobile) |
| **Fill** | Item fills 80-90% of frame |
| **Background** | White or clean, solid preferred |
| **Content** | No watermarks, text overlays, borders, promo graphics |
| **Count** | Up to 24 per listing (free) |

## Processing Pipeline

```
(Steps 1, 2, 5-7 = tools/process_images.py)
1. HEIC/AVIF → JPEG (ImageMagick, native)
2. Auto-orient from EXIF
3. Quality checks:
   a. Blur: OpenCV Laplacian variance < 100 → reject
   b. Dark: Mean grayscale < 60 → reject
4. Background removal (rembg) → white #FFFFFF
5. Square crop: center item, 80-90% fill, white pad
6. Resize down to 1600px longest side (never upscale)
7. Strip EXIF/GPS (keep ICC), export JPEG quality 92
8. Verify: < 7MB final size
```

## System Tools Available

| Tool | Command | Best For |
|------|---------|----------|
| **Pillow** (Python) | `from PIL import Image` | Core resize, crop, format |
| **rembg** | `pip install rembg` | AI background removal |
| **ImageMagick** 7.1.2 | `magick mogrify` | Batch ops, ICC profiles |
| **ffmpeg** N-121164 | `ffmpeg` | Video thumbnails |
| **OpenCV** | `pip install opencv-python` | Blur/dark detection |
| **piexif** | `pip install piexif` | EXIF timestamp injection |

## Key ImageMagick Commands

```bash
# What tools/process_images.py runs per image (prefer the script; it also
# validates size, mirrors folders and skips already-processed files):
#   -resize ...>       only shrinks, never upscales
#   -background        must come BEFORE -extent, or the padding isn't white
#   +profile "!icc,*"  strips EXIF/GPS/XMP but keeps the color profile
magick "input.heic[0]" -auto-orient -resize "1600x1600>" -background white \
  -alpha remove -alpha off -gravity center -extent 1600x1600 \
  +profile "!icc,*" -quality 92 output.jpg

# Batch HEIC -> JPEG in place (writes new .jpg files next to the originals)
magick mogrify -format jpg -quality 92 *.heic

# Strip all metadata including GPS (also drops ICC; +profile "!icc,*" keeps it)
magick mogrify -strip *.jpg

# Batch info (dimensions, format, size)
magick identify -format "%f %wx%h %b\n" *.jpg

# ICC profile conversion (sRGB for web). IM7: "magick", not "magick convert"
magick input.jpg -profile sRGB.icc output.jpg
```

## Google Takeout Handling

Takeout puts original timestamps in JSON sidecars named `IMG_1234.jpg.supplemental-metadata.json` (since late 2024; long names get truncated, e.g. `.supplemental-me.json`), or `IMG_1234.jpg.json` in older exports:

```json
{
  "photoTakenTime": {
    "timestamp": "1704067200"
  }
}
```

Use `piexif` to reinject dates — or just use for sorting (see `process-images` skill).

## Hero Shot Selection

Best image for the listing's primary photo:
1. Full product visible, centered
2. Clean white background (or removed)
3. Highest resolution, sharpest focus
4. Shows brand/model if visible
5. No defects prominently visible (save for condition photos)

## Photo Checklist (Per Item)

- [ ] Front view (hero shot)
- [ ] Back view
- [ ] Each side
- [ ] Close-up of brand/model markings
- [ ] Close-up of each defect
- [ ] Serial number / barcode (if present)
- [ ] Accessories / what's included
- [ ] Scale reference for small items
