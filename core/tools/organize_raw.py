"""
Raw Image Organizer — Help group raw photos into product sets.

Usage:
    python organize_raw.py                    # Interactive mode
    python organize_raw.py --list             # List images available to organize
    python organize_raw.py --move IMG1 IMG2 --to product-name

Images are taken from raw_data/processed/ (output of process_images.py) when it
exists, otherwise from raw_data/. Use --source to pick another folder. Files are
copied, never moved; numbering continues after any images already in the listing.

Requirements:
    pip install Pillow
"""

import argparse
import re
import shutil
import sys
import unicodedata
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.bmp', '.tiff'}


def get_project_root() -> Path:
    """Get the project root directory (the repo root)."""
    return Path(__file__).parent.parent


def slugify(name: str) -> str:
    """Convert a product name to a URL-safe slug."""
    # Transliterate accents (é -> e) before dropping anything non-ASCII
    slug = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    slug = slug.lower().strip()
    slug = re.sub(r'[^a-z0-9\s_-]', '', slug)  # Remove special chars
    slug = re.sub(r'[\s_]+', '-', slug)     # Replace spaces/underscores with hyphens
    slug = re.sub(r'-+', '-', slug)         # Collapse multiple hyphens
    slug = slug.strip('-')
    return slug


def list_images(directory: Path) -> list:
    """List all image files under a directory, excluding processed/ copies of raw folders."""
    if not directory.exists():
        return []
    images = []
    for f in directory.rglob('*'):
        if not f.is_file() or f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        # When listing a raw folder, skip the processed/ copies nested inside it
        if directory.name != 'processed' and 'processed' in f.relative_to(directory).parts:
            continue
        images.append(f)
    return sorted(images)


def default_source(project_root: Path) -> Path:
    """Prefer processed images; fall back to raw_data/."""
    processed_dir = project_root / 'raw_data' / 'processed'
    return processed_dir if processed_dir.exists() else project_root / 'raw_data'


def get_image_info(path: Path) -> dict:
    """Get basic image info."""
    try:
        with Image.open(path) as img:
            return {
                'name': path.name,
                'size': f"{path.stat().st_size / 1024:.0f}KB",
                'dimensions': f"{img.size[0]}x{img.size[1]}",
                'format': img.format,
            }
    except Exception:
        return {
            'name': path.name,
            'size': f"{path.stat().st_size / 1024:.0f}KB",
            'dimensions': 'unknown',
            'format': path.suffix,
        }


def move_to_listing(images: list, slug: str, project_root: Path):
    """Copy images into a listing folder with standardized names."""
    listing_dir = project_root / 'listings' / slug
    listing_dir.mkdir(parents=True, exist_ok=True)

    # Continue numbering after existing images so a second run never overwrites
    pattern = re.compile(rf'^{re.escape(slug)}-(\d+)\.', re.IGNORECASE)
    existing = [int(m.group(1)) for f in listing_dir.iterdir() if (m := pattern.match(f.name))]
    start = max(existing, default=0) + 1

    for i, img_path in enumerate(images, start):
        new_name = f"{slug}-{i:02d}{img_path.suffix.lower()}"
        dest = listing_dir / new_name
        shutil.copy2(img_path, dest)
        print(f"  Copied: {img_path.name} -> {slug}/{new_name}")
        if img_path.suffix.lower() not in ('.jpg', '.jpeg'):
            print(f"    WARNING: {new_name} is not a JPEG -- run process_images.py first")

    print(f"\n  {len(images)} images organized into listings/{slug}/")
    print(f"  Next step: Run /curator-workflow for this item")


def interactive_mode(source_dir: Path, project_root: Path):
    """Interactive mode to group images."""
    images = list_images(source_dir)
    if not images:
        print(f"No images found in {source_dir}")
        return

    print(f"\nFound {len(images)} images in {source_dir}:\n")
    for i, img in enumerate(images, 1):
        info = get_image_info(img)
        print(f"  [{i:3d}] {info['name']:40s}  {info['dimensions']:12s}  {info['size']}")

    print(f"\n{'='*60}")
    print("Group images by product:")
    print("  Enter product name, then image numbers (comma-separated)")
    print("  Type 'done' when finished\n")

    while True:
        name = input("Product name (or 'done'): ").strip()
        if name.lower() == 'done':
            break

        slug = slugify(name)
        if not slug:
            print("  Name produces an empty slug. Try again.")
            continue
        print(f"  Slug: {slug}")

        nums = input("  Image numbers (e.g., 1,2,3): ").strip()
        try:
            indices = [int(n.strip()) - 1 for n in nums.split(',')]
        except ValueError:
            print("  Invalid input. Try again.")
            continue
        bad = [i + 1 for i in indices if not 0 <= i < len(images)]
        if bad:
            print(f"  No image numbered {bad}. Try again.")
            continue

        move_to_listing([images[i] for i in indices], slug, project_root)


def main():
    parser = argparse.ArgumentParser(description='Organize raw photos into product groups')
    parser.add_argument('--list', action='store_true', help='List images available to organize')
    parser.add_argument('--move', nargs='+', help='Image filenames (relative to the source folder) to copy')
    parser.add_argument('--to', type=str, help='Product name/slug to copy images to')
    parser.add_argument('--source', type=str,
                        help='Folder to take images from (default: raw_data/processed, else raw_data)')
    args = parser.parse_args()

    project_root = get_project_root()
    source = Path(args.source) if args.source else default_source(project_root)

    if args.list:
        images = list_images(source)
        if images:
            print(f"\n{len(images)} images in {source}:\n")
            for img in images:
                info = get_image_info(img)
                print(f"  {str(img.relative_to(source)):40s}  {info['dimensions']:12s}  {info['size']}")
        else:
            print(f"No images in {source}")

    elif args.move and args.to:
        slug = slugify(args.to)
        if not slug:
            print(f"'{args.to}' produces an empty slug.")
            sys.exit(1)
        missing = [name for name in args.move if not (source / name).is_file()]
        if missing:
            print(f"Not found in {source}: {', '.join(missing)}")
            sys.exit(1)
        move_to_listing([source / name for name in args.move], slug, project_root)

    elif args.move or args.to:
        parser.error('--move and --to must be used together')

    else:
        interactive_mode(source, project_root)


if __name__ == '__main__':
    main()
