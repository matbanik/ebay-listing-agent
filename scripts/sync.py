"""
Refresh core/ from the private source repo the pipeline is developed in.

The source repo is where code changes land first (it runs real listings). This
script copies the shippable files into core/ according to SYNC, applies the
scrub ledger (REWRITES: the intended differences between source and package),
and refuses any source path that matches NEVER.

    python scripts/sync.py --source <path to source repo>            # copy + rewrite
    python scripts/sync.py --source <path> --check                    # exit 1 on drift
    python scripts/sync.py --source <path> --dry-run                  # list, write nothing

After a sync: `python scripts/sanitize.py --verify`, then the tests in core/.
UPDATE-CHECKLIST.md is the human-readable version of this file.

Exit codes: 0 ok / in sync, 1 drift (--check), 2 a ledger entry no longer
matches its file (the source changed; update REWRITES), 3 a NEVER path matched.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent

# (source glob, destination prefix, keep the source's relative path?)
SYNC = [
    ("AGENTS.md", "core", True),
    ("SETUP.md", "core", True),
    ("requirements.txt", "core", True),
    (".env.example", "core", True),
    ("account.example.json", "core", True),
    (".agent/skills/**/*", "core", True),
    (".agent/workflows/*.md", "core", True),
    (".agent/docs/condition-grading.md", "core", True),
    (".agent/docs/ebay-image-guide.md", "core", True),
    (".agent/docs/pricing-strategy.md", "core", True),
    ("schemas/*.json", "core", True),
    ("templates/*", "core", True),
    ("tools/*.py", "core", True),
    ("tests/*.py", "core", True),
    (".agent/docs/research-prompt-*.md", "docs/research-prompts", False),
]

# Source paths that must never be copied, whatever SYNC says
NEVER = re.compile(
    r"^(listings|raw_data|archive|research|backups)/|^\.agent/context/|(^|/)\.env$|^account\.json$"
    r"|tokens\.json$|token-cache|api-log\.jsonl$|\.log$|__pycache__|\.pyc$"
)

# Package-authored files under synced folders (not copied, never reported as stale)
AUTHORED = {
    "core/CLAUDE.md", "core/MANIFEST.md", "core/.gitignore",
    "core/.agent/context/current-focus.md", "core/.agent/context/known-issues.md",
    "docs/research-prompts/README.md",
}

# Scrub ledger: destination path -> [(source text, package text)]. Each source text
# must occur in the copied file; if it doesn't, the source changed and the entry
# needs updating (exit 2) rather than silently shipping the old wording.
BACKUP_RULE = ("Back up a file before deleting it: copy it to `backups/YYYY-MM-DD/` "
               "(gitignored), or use the backup tool you chose during adoption")
REWRITES = {
    "core/AGENTS.md": [
        ("- Save files to pomera notes before deletion", "- " + BACKUP_RULE),
        ("- Delete files without user request + pomera backup",
         "- Delete files without the user's request and a backup"),
        ("├── archive/                     # Retired scripts\n", ""),
        ("└── research/                    # LLM deep research results\n",
         "├── tests/                       # Unit tests (pytest)\n"
         "└── backups/                     # File backups before deletes (gitignored)\n"),
    ],
    "core/.agent/workflows/01-import-workflow.md": [
        ("(back up to pomera notes first; see AGENTS.md)", "(back up first; see AGENTS.md)"),
    ],
    "core/.agent/workflows/06-batch-workflow.md": [
        ("`.agent/context/current-focus.md` or pomera notes (not in this workflow file)",
         "`.agent/context/current-focus.md` (not in this workflow file)"),
    ],
}


def planned(source):
    """[(source file, destination relative path)] for every SYNC entry."""
    out, seen = [], set()
    for pattern, prefix, keep_tree in SYNC:
        matches = sorted(p for p in source.glob(pattern) if p.is_file())
        if not matches:
            raise SystemExit(f"SYNC entry matched nothing in the source: {pattern}")
        for src in matches:
            rel = src.relative_to(source).as_posix()
            if NEVER.search(rel):
                print(f"REFUSED: {rel} matches NEVER", file=sys.stderr)
                sys.exit(3)
            dest = f"{prefix}/{rel}" if keep_tree else f"{prefix}/{src.name}"
            if dest not in seen:
                seen.add(dest)
                out.append((src, dest))
    return out


def render(src, dest):
    data = src.read_bytes()
    pairs = REWRITES.get(dest)
    if not pairs:
        return data
    text = data.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n")
    for old, new in pairs:
        if old not in text:
            print(f"STALE LEDGER: {dest}: source text not found: {old[:70]!r}", file=sys.stderr)
            sys.exit(2)
        text = text.replace(old, new)
    return text.replace("\n", newline).encode("utf-8")


def source_commit(source):
    try:
        return subprocess.run(["git", "-C", str(source), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def uncommitted(source, plan):
    """Synced source files that differ from the source commit (synced from the working tree)."""
    rels = [src.relative_to(source).as_posix() for src, _ in plan]
    try:
        out = subprocess.run(["git", "-C", str(source), "status", "--porcelain", "--", *rels],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return sorted(line[3:] for line in out.splitlines() if line.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", required=True, type=Path, help="root of the private source repo")
    ap.add_argument("--check", action="store_true", help="report drift, write nothing, exit 1 on drift")
    ap.add_argument("--dry-run", action="store_true", help="list what would change, write nothing")
    args = ap.parse_args(argv)
    source = args.source.resolve()
    if not (source / "tools" / "ebay_api.py").is_file():
        raise SystemExit(f"{source} doesn't look like the source repo (no tools/ebay_api.py)")

    plan = planned(source)
    changed = []
    for src, dest in plan:
        body = render(src, dest)
        target = PKG / dest
        if not target.is_file() or target.read_bytes() != body:
            changed.append(dest)
            if not (args.check or args.dry_run):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)

    synced = {d for _, d in plan}
    prefixes = {"core/.agent/skills/", "core/.agent/workflows/", "core/tools/", "core/tests/",
                "core/schemas/", "core/templates/", "docs/research-prompts/"}
    stale = sorted(p.relative_to(PKG).as_posix() for prefix in prefixes
                   for p in (PKG / prefix).rglob("*") if p.is_file()
                   and "__pycache__" not in p.parts
                   and p.relative_to(PKG).as_posix() not in synced | AUTHORED)

    commit = source_commit(source)
    dirty = uncommitted(source, plan)
    report = {"source_commit": commit, "uncommitted_in_source": dirty, "files": len(plan),
              "changed": changed, "stale_in_package": stale}
    if not (args.check or args.dry_run):
        record = {"source_commit": commit, "date": date.today().isoformat(), "files": len(plan)}
        if dirty:
            record["uncommitted_in_source"] = dirty
        (PKG / "scripts" / "last-sync.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if stale:
        print("Files above under stale_in_package no longer exist in the source: "
              "remove them by hand (after a backup) or add them to AUTHORED.", file=sys.stderr)
    return 1 if args.check and (changed or stale) else 0


if __name__ == "__main__":
    sys.exit(main())
