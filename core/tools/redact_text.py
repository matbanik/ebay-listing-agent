"""
Text Redactor — Find sensitive text in listing photos with OCR and blur it out.

Typical targets: license/authentication codes, registration keys, MAC addresses,
IMEIs, personal names or addresses on shipping labels.

Usage:
    # Redact a known value wherever it appears (fuzzy, tolerates OCR misreads)
    python redact_text.py listings/{slug}/*.jpg --text AB12-CD34

    # Redact whatever value follows a label (value not known in advance)
    python redact_text.py listings/{slug}/*.jpg --after-label "Authentication Code"

    # Regex on the raw OCR text (exact, no fuzzy matching)
    python redact_text.py img.jpg --regex "[0-9A-F]{2}(:[0-9A-F]{2}){5}"

    # OCR missed it: give the region by hand (x,y,w,h in image pixels)
    python redact_text.py img.jpg --box 1210,1088,130,22

    # Preview matches without writing
    python redact_text.py listings/{slug}/*.jpg --text AB12-CD34 --dry-run

Images are rewritten in place (JPEG quality 92, ICC profile kept, no EXIF); the
unredacted originals stay in raw_data/processed/. After writing, each image is
OCR'd again and the run exits 1 if a target can still be read.

Requirements:
    pip install rapidocr_onnxruntime opencv-python Pillow numpy
"""

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import cv2
    import numpy as np
    from PIL import Image
    from rapidocr_onnxruntime import RapidOCR
except ImportError as e:
    print(f"ERROR: {e.name} is required. Install with: "
          "pip install rapidocr_onnxruntime opencv-python Pillow numpy")
    sys.exit(1)

JPEG_QUALITY = 92
DEFAULT_SCALES = (1.0, 2.0)   # 2x upscale catches small label text the 1x pass misses
FUZZY_THRESHOLD = 0.75        # similarity needed for --text / --after-label matches

# Characters OCR commonly confuses, folded to one canonical form before fuzzy matching
CONFUSABLE = str.maketrans({
    'B': '8', 'O': '0', 'Q': '0', 'D': '0', 'I': '1', 'L': '1', 'J': '1',
    'S': '5', 'Z': '2', 'G': '6', 'A': '4', 'T': '7',
})


@dataclass
class Detection:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Region:
    x0: int
    y0: int
    x1: int
    y1: int
    reason: str


def canon(text: str) -> tuple[str, list[int]]:
    """Uppercase alphanumerics with confusables folded; also return each char's index in text."""
    chars, idx = [], []
    for i, ch in enumerate(text):
        if ch.isalnum():
            chars.append(ch.upper().translate(CONFUSABLE))
            idx.append(i)
    return ''.join(chars), idx


def fuzzy_find(haystack: str, needle: str, threshold: float) -> tuple[int, int] | None:
    """Best window of haystack similar to needle (both canonical). Returns (start, end) or None."""
    n = len(needle)
    if n == 0 or len(haystack) == 0:
        return None
    best, best_span = 0.0, None
    for size in {max(1, n - 1), n, n + 1}:
        for start in range(0, max(1, len(haystack) - size + 1)):
            window = haystack[start:start + size]
            ratio = difflib.SequenceMatcher(None, window, needle).ratio()
            if ratio > best:
                best, best_span = ratio, (start, start + len(window))
    return best_span if best >= threshold else None


def char_span_to_x(det: Detection, start: int, end: int) -> tuple[float, float]:
    """Estimate the x-range of raw characters [start, end) assuming even character widths."""
    per_char = (det.x1 - det.x0) / max(1, len(det.text))
    return det.x0 + start * per_char, det.x0 + end * per_char


def run_ocr(engine: RapidOCR, img: np.ndarray, scales) -> list[Detection]:
    detections = []
    for s in scales:
        work = img if s == 1 else cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        result, _ = engine(work)
        for box, text, _conf in result or []:
            xs = [p[0] / s for p in box]
            ys = [p[1] / s for p in box]
            detections.append(Detection(text, min(xs), min(ys), max(xs), max(ys)))
    return detections


def find_regions(dets: list[Detection], texts, regexes, labels, threshold) -> list[Region]:
    regions = []

    def add(det: Detection, raw_start: int, raw_end: int, reason: str):
        x0, x1 = char_span_to_x(det, raw_start, raw_end)
        if raw_start > 0 or raw_end < len(det.text):
            # Character widths vary (OCR also drops spaces), so the estimate can be a
            # character off: widen by one character so no edge glyph survives
            per_char = (det.x1 - det.x0) / max(1, len(det.text))
            x0, x1 = max(det.x0, x0 - per_char), min(det.x1, x1 + per_char)
        regions.append(Region(int(x0), int(det.y0), int(x1 + 0.5), int(det.y1 + 0.5), reason))

    for det in dets:
        c, idx = canon(det.text)

        for t in texts:
            target, _ = canon(t)
            span = fuzzy_find(c, target, threshold)
            if span:
                add(det, idx[span[0]], idx[span[1] - 1] + 1, f"text '{t}' ~ '{det.text}'")

        for rx in regexes:
            for m in re.finditer(rx, det.text):
                add(det, m.start(), m.end(), f"regex /{rx}/ ~ '{det.text}'")

        for lab in labels:
            label, _ = canon(lab)
            span = fuzzy_find(c[:len(label) + 3], label, threshold)
            if not span:
                continue
            rest = len(c) - span[1]
            if rest >= 3:
                # Value is in the same OCR box, right after the label
                add(det, idx[span[1]], len(det.text), f"after '{lab}' ~ '{det.text}'")
            else:
                # Value is a separate box to the right on the same line
                h = det.y1 - det.y0
                for other in dets:
                    overlap = min(det.y1, other.y1) - max(det.y0, other.y0)
                    if (other is not det and overlap > 0.5 * h
                            and det.x1 - h <= other.x0 <= det.x1 + 4 * h):
                        add(other, 0, len(other.text), f"after '{lab}' ~ '{other.text}'")
    return regions


def pad_and_merge(regions: list[Region], w: int, h: int) -> list[Region]:
    padded = []
    for r in regions:
        # OCR boxes already hug the glyphs vertically; keep vertical padding small so
        # tightly spaced table rows above/below stay readable
        px = max(3, int(0.3 * (r.y1 - r.y0)))
        py = max(2, int(0.1 * (r.y1 - r.y0)))
        padded.append(Region(max(0, r.x0 - px), max(0, r.y0 - py),
                             min(w, r.x1 + px), min(h, r.y1 + py), r.reason))
    merged: list[Region] = []
    for r in sorted(padded, key=lambda r: (r.y0, r.x0)):
        for m in merged:
            if r.x0 <= m.x1 and r.x1 >= m.x0 and r.y0 <= m.y1 and r.y1 >= m.y0:
                m.x0, m.y0 = min(m.x0, r.x0), min(m.y0, r.y0)
                m.x1, m.y1 = max(m.x1, r.x1), max(m.y1, r.y1)
                break
        else:
            merged.append(r)
    return merged


def redact(img: np.ndarray, region: Region, style: str) -> None:
    roi = img[region.y0:region.y1, region.x0:region.x1]
    if roi.size == 0:
        return
    if style == 'box':
        roi[:] = np.median(roi.reshape(-1, 3), axis=0)
    elif style == 'pixelate':
        rh, rw = roi.shape[:2]
        small = cv2.resize(roi, (max(1, rw // 12), max(1, rh // 12)), interpolation=cv2.INTER_AREA)
        roi[:] = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)
    else:
        # Kernel as large as the region: every pixel becomes a regional average, which
        # can't be deblurred back to characters (a small-kernel blur sometimes can).
        k = max(roi.shape[:2]) | 1
        for _ in range(3):
            roi[:] = cv2.GaussianBlur(roi, (k, k), 0)


def parse_box(spec: str) -> Region:
    x, y, w, h = (int(v) for v in spec.split(','))
    return Region(x, y, x + w, y + h, f"manual box {spec}")


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR-find and blur sensitive text in images")
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--text', action='append', default=[], help="Known value to redact (fuzzy)")
    parser.add_argument('--regex', action='append', default=[], help="Regex on raw OCR text")
    parser.add_argument('--after-label', action='append', default=[], dest='labels',
                        help="Redact the value that follows this label")
    parser.add_argument('--box', action='append', default=[], help="Manual region x,y,w,h")
    parser.add_argument('--style', choices=['blur', 'pixelate', 'box'], default='blur')
    parser.add_argument('--scales', default='1,2', help="OCR scales (default 1,2)")
    parser.add_argument('--threshold', type=float, default=FUZZY_THRESHOLD)
    parser.add_argument('--out-dir', type=Path, help="Write here instead of in place")
    parser.add_argument('--dry-run', action='store_true', help="Show matches, write nothing")
    args = parser.parse_args()

    if not (args.text or args.regex or args.labels or args.box):
        parser.error("give at least one of --text, --regex, --after-label, --box")

    scales = [float(s) for s in args.scales.split(',')]
    engine = RapidOCR()
    leaks = 0

    for path in args.images:
        pil = Image.open(path)
        icc = pil.info.get('icc_profile')
        img = cv2.cvtColor(np.array(pil.convert('RGB')), cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]

        dets = run_ocr(engine, img, scales)
        found = find_regions(dets, args.text, args.regex, args.labels, args.threshold)
        regions = pad_and_merge(found + [parse_box(b) for b in args.box], w, h)

        print(f"\n{path}: {len(regions)} region(s)")
        for r in regions:
            print(f"  [{r.x0},{r.y0} {r.x1 - r.x0}x{r.y1 - r.y0}] {r.reason}")
        if not regions or args.dry_run:
            continue

        for r in regions:
            redact(img, r, args.style)

        out = (args.out_dir / path.name) if args.out_dir else path
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(
            out, 'JPEG', quality=JPEG_QUALITY, icc_profile=icc)

        # Verify: nothing targeted should still be readable
        remaining = find_regions(run_ocr(engine, img, scales), args.text, args.regex, [], args.threshold)
        if remaining:
            leaks += 1
            for r in remaining:
                print(f"  STILL READABLE: {r.reason} at [{r.x0},{r.y0}]")
        else:
            print(f"  redacted -> {out}")

    if leaks:
        print(f"\n{leaks} image(s) still contain readable targets; add --box for those regions")
    return 1 if leaks else 0


if __name__ == '__main__':
    sys.exit(main())
