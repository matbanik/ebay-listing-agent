"""
Reference integrity: every repo path a shipped Markdown file names must exist.

Checked references:
- Markdown links `[text](target)` (not http/mailto/#anchor), resolved from the file's folder.
- Inline code spans that look like repo paths: the first segment is a name that
  exists at the package root or in core/ (`tools/x.py`, `.agent/skills/...`), or
  the span is a bare `.md` / `.py` file name.
- `tools/*.py` and `scripts/*.py` anywhere, including inside commands and code
  blocks (a path inside a command is how a missing tool slips past span checks).

A path resolves against the file's folder, core/ (the docs inside core/ are written
from the adopter repo root) or the package root. Paths the pipeline creates at run
time, or that MANIFEST.md lists as not shipped, are in EXPECTED_ABSENT.

    python scripts/refcheck.py            # exit 0 clean, 7 dangling references
"""

import re
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent

# Created at run time or deliberately not shipped (see core/MANIFEST.md "Not included")
EXPECTED_ABSENT = re.compile(
    r"^(?:core/)?(?:listings|raw_data|backups)/"         # working folders: contents are runtime
    r"|^(?:research|archive)(?:/|$)"                    # source-repo folders not shipped
    r"|(?:^|/)\.env$|(?:^|/)account\.json$|(?:^|/)tokens\.json$|api-log\.jsonl$"
    r"|(?:^|/)scrub\.local\.txt$"                       # each maintainer's private deny-list
)

# Whole files kept as dated records; their paths describe a layout that no longer exists
HISTORICAL = re.compile(r"^docs/research-prompts/research-prompt-[\w-]+\.md$")

LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
SPAN = re.compile(r"`([^`\n]+)`")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
TOOL = re.compile(r"(?<![\w./-])((?:core/)?(?:tools|scripts)/[\w.-]+\.(?:py|ps1|sh))\b")
NOT_A_PATH = re.compile(r"[\s{}<>*$%|=(),;\"']|://|^/|^~|^-|^@")  # @file is an import, not a path


def shipped_files(root):
    """Files that would be committed: tracked plus untracked-but-not-ignored."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
                             capture_output=True, text=True, check=True).stdout
        if (root / ".git").exists():
            return sorted(root / p for p in out.split("\0") if p and (root / p).is_file())
    except (OSError, subprocess.CalledProcessError):
        pass
    skip = {".git", "__pycache__", ".pytest_cache"}
    return sorted(p for p in root.rglob("*") if p.is_file() and not skip & set(p.relative_to(root).parts)
                  and p.name != "scrub.local.txt")


def _clean(ref):
    ref = ref.split("#", 1)[0]
    ref = re.sub(r":\d+(?:-\d+)?$", "", ref)
    return ref.rstrip(".,;:")


def _resolves(ref, md, root, names):
    bases = [md.parent, root / "core", root]
    if any((b / ref).exists() for b in bases):
        return True
    rel = ref[3:] if ref.startswith("../") else ref
    if EXPECTED_ABSENT.search(rel.rstrip("/")) or EXPECTED_ABSENT.search(rel):
        return True
    return "/" not in ref.rstrip("/") and ref in names


def check(root=PKG, files=None):
    """[failure strings] for every dangling reference under root."""
    files = shipped_files(root) if files is None else files
    names = {p.name for p in files}
    first_segments = {p.relative_to(root).parts[0] for p in files}
    first_segments |= {p.relative_to(root / "core").parts[0] for p in files
                       if p.is_relative_to(root / "core") and len(p.relative_to(root / "core").parts) > 1}
    first_segments |= {"listings", "raw_data", "backups", "research", "archive"}
    failures = []
    for md in files:
        rel_md = md.relative_to(root).as_posix()
        if md.suffix.lower() != ".md" or HISTORICAL.match(rel_md):
            continue
        text = md.read_text(encoding="utf-8")
        refs = set()
        for m in LINK.finditer(text):
            target = m.group(1)
            if not re.match(r"(?i)(https?:|mailto:|#)", target):
                refs.add((_clean(target), True))
        for m in SPAN.finditer(FENCE.sub("", text)):
            span = _clean(m.group(1).strip())
            if not span or NOT_A_PATH.search(span):
                continue
            head = span.split("/", 1)[0]
            bare_file = "/" not in span and re.search(r"\.(md|py)$", span)
            if ("/" in span and head in first_segments) or bare_file:
                refs.add((span, False))
        for m in TOOL.finditer(text):
            refs.add((m.group(1), False))
        for ref, is_link in sorted(refs):
            if is_link and not (md.parent / ref).exists():
                failures.append(f"{rel_md}: link target not found: {ref}")
            elif not is_link and not _resolves(ref, md, root, names):
                failures.append(f"{rel_md}: path not found: {ref}")
    return failures


def main():
    failures = check()
    for line in failures:
        print(line)
    print(f"refcheck: {len(failures)} dangling reference(s)")
    return 7 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
