"""
eBay Image Processor — Batch resize and optimize images for eBay listings.

Usage:
    python process_images.py                          # Process raw_data/ (recursively)
    python process_images.py --input path/to/images   # Process specific folder (recursively)
    python process_images.py --force                  # Re-process images that already have output
    python process_images.py --test                   # Process with test image

Requirements:
    ImageMagick 7 (`magick` on PATH) — does the actual processing, including HEIC/AVIF
    pip install Pillow                                  # Only needed for --test
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# eBay recommended settings
TARGET_SIZE = 1600          # Longest side in pixels
MIN_SIZE = 500              # eBay rejects images whose longest side is below this
JPEG_QUALITY = 92           # JPEG quality (90+ recommended by eBay)
SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp', '.heic', '.heif', '.avif',
}

# Output folders are never treated as input, so re-runs don't process their own output
OUTPUT_DIR_NAME = 'processed'


def get_project_root() -> Path:
    """Get the project root directory (the repo root)."""
    return Path(__file__).parent.parent


def get_dimensions(input_path: Path) -> tuple[int, int] | None:
    """Return (width, height) of the first frame, or None if ImageMagick can't read it."""
    result = subprocess.run(
        ["magick", "identify", "-format", "%w %h", f"{input_path}[0]"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        w, h = result.stdout.split()[:2]
        return int(w), int(h)
    except ValueError:
        return None


def process_image(input_path: Path, output_path: Path, target_size: int = TARGET_SIZE) -> bool:
    """
    Process a single image for eBay using ImageMagick:
    - Auto-orient based on EXIF
    - Resize down to target_size (longest side); never upscale
    - Flatten transparency onto white and pad to square (1:1)
    - Strip EXIF/XMP metadata (including GPS location) but keep the ICC color profile
    - Convert to JPEG with quality JPEG_QUALITY
    """
    try:
        dims = get_dimensions(input_path)
        if dims is None:
            print(f"  [FAIL] {input_path.name}: ImageMagick cannot read this file")
            return False
        longest = max(dims)
        if longest < MIN_SIZE:
            print(f"  [FAIL] {input_path.name}: {dims[0]}x{dims[1]} is below eBay's "
                  f"{MIN_SIZE}px minimum -- retake the photo")
            return False
        side = min(longest, target_size)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "magick", f"{input_path}[0]",
            "-auto-orient",
            "-resize", f"{target_size}x{target_size}>",
            "-background", "white",
            "-alpha", "remove", "-alpha", "off",
            "-gravity", "center",
            "-extent", f"{side}x{side}",
            "+profile", "!icc,*",
            "-quality", str(JPEG_QUALITY),
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"  [FAIL] {input_path.name}: ImageMagick error: {result.stderr.strip()}")
            return False

        orig_size = input_path.stat().st_size / 1024
        new_size = output_path.stat().st_size / 1024
        note = f"  (only {longest}px -- {TARGET_SIZE}px recommended)" if longest < TARGET_SIZE else ""
        print(f"  [OK] {input_path.name} -> {output_path.name}  "
              f"({orig_size:.0f}KB -> {new_size:.0f}KB){note}")
        return True

    except Exception as e:
        print(f"  [FAIL] {input_path.name}: {e}")
        return False


def find_images(input_dir: Path, output_dir: Path) -> list[Path]:
    """Find images under input_dir recursively, skipping output folders and hidden files."""
    output_dir = output_dir.resolve()
    images = []
    for f in input_dir.rglob('*'):
        if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel_parts = f.relative_to(input_dir).parts
        if any(p.startswith('.') or p == OUTPUT_DIR_NAME for p in rel_parts):
            continue
        if f.resolve().is_relative_to(output_dir):
            continue
        images.append(f)
    return sorted(images)


def process_folder(input_dir: Path, output_dir: Path, target_size: int = TARGET_SIZE,
                   force: bool = False) -> dict:
    """Process all images under a folder. Returns stats dict."""
    stats = {'processed': 0, 'skipped': 0, 'failed': 0}

    if not input_dir.exists():
        print(f"ERROR: Input directory does not exist: {input_dir}")
        stats['failed'] += 1
        return stats

    image_files = find_images(input_dir, output_dir)

    if not image_files:
        print(f"No images found in {input_dir}")
        print(f"  Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        return stats

    print(f"\nProcessing {len(image_files)} images from {input_dir}")
    print(f"  Output: {output_dir}")
    print(f"  Target: {target_size}px longest side, square, JPEG Q{JPEG_QUALITY}, metadata stripped")
    print()

    claimed: dict[Path, Path] = {}
    for img_path in image_files:
        # Mirror subfolders so photos from different batches can't collide
        rel = img_path.relative_to(input_dir).with_suffix('.jpg')
        output_path = output_dir / rel

        if output_path in claimed:
            print(f"  [FAIL] {img_path.name}: output name collides with {claimed[output_path].name} "
                  f"-- rename one of them")
            stats['failed'] += 1
            continue
        claimed[output_path] = img_path

        if output_path.exists() and not force:
            print(f"  [SKIP] {img_path.name} -- already processed (use --force to redo)")
            stats['skipped'] += 1
            continue

        if process_image(img_path, output_path, target_size):
            stats['processed'] += 1
        else:
            stats['failed'] += 1

    return stats


def create_test_image(output_dir: Path):
    """Create a test image for validation."""
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow is required for --test. Install with: pip install Pillow")
        sys.exit(1)
    test_path = output_dir / 'test-image.png'
    img = Image.new('RGB', (3000, 2000), color=(200, 200, 200))
    # Add some variation
    for x in range(0, 3000, 100):
        for y in range(0, 2000, 100):
            r = (x * 255) // 3000
            g = (y * 255) // 2000
            img.paste((r, g, 128), (x, y, min(x + 50, 3000), min(y + 50, 2000)))
    img.save(test_path)
    print(f"Created test image: {test_path} (3000x2000)")
    return test_path


def main():
    parser = argparse.ArgumentParser(description='Process images for eBay listings')
    parser.add_argument('--input', '-i', type=str, help='Input directory, searched recursively (default: raw_data/)')
    parser.add_argument('--output', '-o', type=str, help=f'Output directory (default: {{input}}/{OUTPUT_DIR_NAME})')
    parser.add_argument('--test', action='store_true', help='Create and process a test image')
    parser.add_argument('--force', action='store_true', help='Re-process images that already have output')
    parser.add_argument('--size', type=int, default=TARGET_SIZE, help=f'Target longest side (default: {TARGET_SIZE})')
    args = parser.parse_args()

    if not shutil.which('magick'):
        print("ERROR: ImageMagick 7 ('magick') not found on PATH")
        sys.exit(1)

    project_root = get_project_root()

    if args.test:
        test_dir = project_root / 'raw_data' / 'test'
        test_dir.mkdir(parents=True, exist_ok=True)
        create_test_image(test_dir)
        input_dir = test_dir
        output_dir = test_dir / OUTPUT_DIR_NAME
    else:
        input_dir = Path(args.input) if args.input else project_root / 'raw_data'
        output_dir = Path(args.output) if args.output else input_dir / OUTPUT_DIR_NAME

    stats = process_folder(input_dir, output_dir, args.size, args.force)

    print(f"\n{'='*50}")
    print(f"Results: {stats['processed']} processed, {stats['skipped']} skipped, {stats['failed']} failed")

    if stats['failed'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
