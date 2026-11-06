---
name: process-images
description: Batch process raw product photos for eBay listings. Resize, convert, auto-orient, remove backgrounds, detect quality issues. Uses Pillow, ImageMagick, ffmpeg, and rembg.
---

# Process Images Skill

Prepare raw product photos from Google Photos for eBay listings. Handles HEIC conversion, resizing, background removal, quality detection, and metadata management.

## Available System Tools

| Tool | Version | Use For |
|------|---------|---------|
| **Pillow** (Python) | pip install Pillow | Core resize, crop, format conversion, EXIF transpose |
| **rembg** (Python) | pip install rembg | AI background removal (U²-Net, local, free) |
| **ImageMagick** | 7.1.2-12 (installed) | Batch format conversion, ICC profiles, advanced metadata |
| **ffmpeg** | N-121164 (installed) | Strip Live Photo .mov files, video thumbnails |
| **piexif** (Python) | pip install piexif | EXIF metadata injection (Takeout timestamp rescue) |
| **OpenCV** (Python) | pip install opencv-python | Blur detection (Laplacian), dark image detection |

## eBay Image Specs (2025-2026)

- **Minimum**: 500×500px — **Recommended**: 1600×1600px — **Maximum**: 9000×9000px
- **File size**: ≤12MB (target <7MB for mobile)
- **Format**: JPEG preferred (quality 92, what the script writes), PNG, WebP, HEIC, AVIF accepted
- **Aspect**: Square (1:1) or 4:5 for mobile — item fills 80-90% of frame
- **Content**: No watermarks, text overlays, borders, or promotional graphics
- **Count**: Up to 24 per listing (free)

## Processing Pipeline

Execute in this order for each image:

```
Steps 1, 2, 5-7 and metadata stripping are done by tools/process_images.py.
1. HEIC/AVIF → JPEG (ImageMagick reads them natively)
2. Auto-orient from EXIF (Pillow ImageOps.exif_transpose)
3. Quality checks:
   a. Blur detection — OpenCV Laplacian variance < 100 → reject
   b. Dark detection — mean grayscale < 60 → reject
4. Background removal (rembg) → replace alpha with #FFFFFF
5. Square crop — center item, 80-90% fill, white padding
6. Resize down to 1600px longest side (never upscale; < 500px → reject)
7. Strip EXIF/GPS (keep ICC), JPEG export at quality 92
8. Verify final size < 7MB
Upload happens later, in /lister-workflow, after the Curator puts the hero first:
9. Upload to eBay EPS in final order (python tools/ebay_api.py upload-images {slug} --replace, Media API)
10. URLs saved as a JSON array to listings/{slug}/image-urls.json
```

## ImageMagick Commands

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

## ffmpeg Commands

```bash
# Strip Live Photo .mov companions (keep only .jpg)
# (Just delete .mov/.mp4 files from export — no conversion needed)

# Extract thumbnail from video listing
ffmpeg -i video.mp4 -ss 00:00:01 -vframes 1 -q:v 2 thumbnail.jpg
```

## Google Takeout Metadata Rescue

Original timestamps are in Takeout's JSON sidecars. Use them for sorting/grouping only: process_images.py strips EXIF from the listing copies anyway.

```python
import json, piexif
from pathlib import Path

def rescue_timestamp(image_path: Path):
    """Find matching JSON sidecar and inject original timestamp into EXIF."""
    # Since late 2024 sidecars are IMG_1234.jpg.supplemental-metadata.json, and long
    # names get truncated (.supplemental-me.json, .suppl.json, .s.json).
    # Older exports use IMG_1234.jpg.json.
    json_candidates = sorted(image_path.parent.glob(image_path.name + '.s*.json')) + [
        image_path.with_suffix(image_path.suffix + '.json'),
        image_path.parent / (image_path.stem + '.json'),
    ]
    for json_path in json_candidates:
        if json_path.exists():
            meta = json.loads(json_path.read_text(encoding='utf-8'))
            ts = meta.get('photoTakenTime', {}).get('timestamp')
            if ts:
                from datetime import datetime
                dt = datetime.fromtimestamp(int(ts))
                exif_date = dt.strftime('%Y:%m:%d %H:%M:%S')
                # Inject into EXIF
                exif_dict = piexif.load(str(image_path))
                exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = exif_date
                exif_dict['0th'][piexif.ImageIFD.DateTime] = exif_date
                piexif.insert(piexif.dump(exif_dict), str(image_path))
            break
```

## Quality Gate Checks

```python
import cv2
import numpy as np

def is_blurry(image_path: str, threshold: float = 100.0) -> bool:
    """Laplacian variance blur detection. Below threshold = blurry."""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    return cv2.Laplacian(img, cv2.CV_64F).var() < threshold

def is_too_dark(image_path: str, threshold: float = 60.0) -> bool:
    """Mean brightness check. Below threshold = too dark."""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    return np.mean(img) < threshold
```

## Background Removal (rembg)

```python
from rembg import remove
from PIL import Image

def remove_background(input_path, output_path):
    """Remove background and replace with white."""
    with Image.open(input_path) as img:
        result = remove(img)  # Returns RGBA
    # Replace transparency with white
    white_bg = Image.new('RGB', result.size, (255, 255, 255))
    white_bg.paste(result, mask=result.split()[3])  # Use alpha as mask
    white_bg.save(output_path, 'JPEG', quality=92, optimize=True)
```

## When to Use Each Tool

| Task | Best Tool | Why |
|------|-----------|-----|
| Single image resize | Pillow | Fast, in-memory, Python-native |
| Batch format conversion | ImageMagick `mogrify` | One command, handles hundreds |
| HEIC → JPEG | ImageMagick (`process_images.py`) | Native HEIC/AVIF support; no pillow-heif needed |
| Background removal | rembg | Free, local, U²-Net quality |
| Blur/dark detection | OpenCV | Industry standard, Laplacian variance |
| EXIF metadata | piexif (inject) or `magick -strip` (remove) | piexif for surgical edits, ImageMagick for bulk strip |
| Live Photo cleanup | ffmpeg or just delete .mov | ffmpeg only if you need video thumbnails |
| ICC profile handling | ImageMagick | Best sRGB conversion support |
