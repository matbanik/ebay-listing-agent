"""
Privacy release gate: nothing private may ship in this package.

    python scripts/sanitize.py --verify       # every check; exit 0 only when all pass
    python scripts/sanitize.py --selftest     # prove each check can fail; run before trusting --verify

`--verify` runs every check even after one fails and exits with the code of the
first failing check:

    2  deny-list strings (scrub.local.txt) plus built-ins: personal email
       addresses, C:\\Users\\<name>, /Users/<name>, /home/<name>
    3  secret shapes: eBay OAuth tokens, Bearer tokens, filled-in credential
       variables, eBay App/Cert IDs; also gitleaks findings when gitleaks is installed
    4  account data shapes: policy/offer/listing IDs, ebay.com/itm/<id>,
       ebay.com/usr/<seller>, real ZIP codes next to postalCode
    5  images with any EXIF (GPS included), and HEIC files (they can't be checked)
    6  git metadata: every author and committer is a noreply address, and no
       commit message carries a deny-list string or a personal email address
    7  references: scripts/refcheck.py

Scope: the files git would ship (tracked plus untracked-but-not-ignored). Without
a git repository it walks the tree instead.

scrub.local.txt (gitignored, never shipped) holds the private strings, one per
line. Blank lines and # comments are ignored. `@env <path>` denies every value in
that .env file, so the secrets never have to be copied. Matching ignores case
and needs a non-alphanumeric character (or the start or end of text) on both sides.
Without scrub.local.txt, check 2 fails unless --no-denylist is given (for example
in CI on a fork, where only the built-ins can run).
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import refcheck  # noqa: E402

PKG = Path(__file__).resolve().parent.parent
DENYLIST = PKG / "scrub.local.txt"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".gif", ".bmp"}
NAMES = {2: "deny-list", 3: "secrets", 4: "account data", 5: "images", 6: "git metadata", 7: "references"}

# --- built-in patterns (no private data here: this file ships) -------------------

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
SAFE_EMAIL = re.compile(r"(?i)^(?:noreply|no-reply)@|@users\.noreply\.github\.com$|@example\.(?:com|org|net)$")
USER_PATH = re.compile(r"(?i)(?:\b[a-z]:[\\/]+users[\\/]+|(?<![\w.])/(?:users|home)/)([^\\/\s<>{}%$'\"`*]+)")
SAFE_USER = {"public", "default", "username", "user", "you", "yourname", "name", "runner", "me"}

TOKEN_SECRETS = [
    ("eBay OAuth token", re.compile(r"v\^1\.1#[A-Za-z0-9^#%+/=_-]{20,}")),
    ("Bearer token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=^#-]{24,}")),
    ("eBay App/Cert ID", re.compile(r"(?:\b|-)(?:PRD|SBX)-[0-9a-f]{8,}(?:-[0-9a-f]{4,})+")),
]
CRED_VAR = re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?(EBAY_(?:CLIENT_ID|CLIENT_SECRET|USER_REFRESH_TOKEN|REDIRECT_URI))"
                      r"[ \t]*=[ \t]*(\S+)")  # [ \t], not \s: an empty value must not read the next line
PLACEHOLDER = re.compile(r"(?i)your|example|placeholder|xxx|changeme|\.\.\.|<|\{|\$|^[\"']{2}$")

ID_KEYWORDS = re.compile(r"(?i)polic|offer|listing|item.?id|fulfil|payment|return|order")
LONG_ID = re.compile(r"(?<!\d)\d{10,13}(?!\d)")
ITEM_URL = re.compile(r"(?i)ebay\.[a-z.]+/itm/(?:[^/\s]+/)?(\d{9,})")
SELLER_URL = re.compile(r"(?i)ebay\.[a-z.]+/(?:usr|str)/([A-Za-z0-9._-]+)")
POSTAL = re.compile(r"(?i)postal_?code[\"'\s:=]*[\"']?(\d{5})(?!\d)")


def is_dummy_number(n):
    """Obvious example values: 100000000001, 111111111111, 123456789012, 00000."""
    # 10{6,}: long IDs only, so a real ZIP such as 60601 is never taken for a dummy
    return bool(re.fullmatch(r"(\d)\1+|10{6,}\d{1,3}|0*123456789\d*|12345", n))


# --- inputs -----------------------------------------------------------------------

def load_denylist(path):
    """(strings, problems). @env lines expand to that file's values."""
    terms, problems = [], []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@env "):
            env = Path(line[5:].strip())
            if not env.is_file():
                problems.append(f"@env file not found: {env}")
                continue
            for env_line in env.read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*(?:export\s+)?[A-Z0-9_]+\s*=\s*(.+)", env_line)
                if m:
                    value = m.group(1).strip().strip("\"'")
                    if len(value) >= 6 and not re.fullmatch(r"(?i)production|sandbox|EBAY_[A-Z]+|[a-z]{2}-[A-Z]{2}", value):
                        terms.append(value)
            continue
        terms.append(line)
    return terms, problems


def deny_pattern(terms):
    if not terms:
        return None
    alts = "|".join(re.escape(t) for t in sorted(set(terms), key=len, reverse=True))
    return re.compile(r"(?i)(?<![A-Za-z0-9])(?:" + alts + r")(?![A-Za-z0-9])")


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


# --- checks: each returns [failure strings] ---------------------------------------

def check_denylist(root, files, deny):
    hits = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        if deny and deny.search(rel):
            hits.append(f"{rel}: file name matches a deny-list string")
        text = read_text(path)
        if text is None:
            continue
        if deny:
            hits += [f"{rel}:{line_of(text, m.start())}: deny-list string" for m in deny.finditer(text)]
        hits += [f"{rel}:{line_of(text, m.start())}: email address {m.group(0)}"
                 for m in EMAIL.finditer(text) if not SAFE_EMAIL.search(m.group(0))]
        hits += [f"{rel}:{line_of(text, m.start())}: user home path ({m.group(1)})"
                 for m in USER_PATH.finditer(text) if m.group(1).lower() not in SAFE_USER]
    return hits


def check_secrets(root, files):
    hits = []
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        rel = path.relative_to(root).as_posix()
        for label, pattern in TOKEN_SECRETS:
            hits += [f"{rel}:{line_of(text, m.start())}: {label}" for m in pattern.finditer(text)]
        hits += [f"{rel}:{line_of(text, m.start())}: {m.group(1)} has a value"
                 for m in CRED_VAR.finditer(text) if not PLACEHOLDER.search(m.group(2))]
    return hits


def check_account_data(root, files):
    hits = []
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        rel = path.relative_to(root).as_posix()
        for no, line in enumerate(text.splitlines(), 1):
            if ID_KEYWORDS.search(line):
                hits += [f"{rel}:{no}: ID-like number {n}" for n in LONG_ID.findall(line) if not is_dummy_number(n)]
            hits += [f"{rel}:{no}: eBay item URL ({n})" for n in ITEM_URL.findall(line) if not is_dummy_number(n)]
            hits += [f"{rel}:{no}: eBay seller URL ({s})" for s in SELLER_URL.findall(line)
                     if not re.search(r"(?i)your|example|seller.?name|username", s)]
            hits += [f"{rel}:{no}: postal code {z}" for z in POSTAL.findall(line) if not is_dummy_number(z)]
    return hits


def check_images(root, files):
    from PIL import Image

    hits = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        if suffix in {".heic", ".heif"}:
            hits.append(f"{rel}: HEIC can't be checked for EXIF; ship JPEG")
        elif suffix in IMAGE_SUFFIXES:
            try:
                with Image.open(path) as im:
                    exif = im.getexif()
                    if exif:
                        gps = " including GPS" if exif.get_ifd(0x8825) else ""
                        hits.append(f"{rel}: has EXIF ({len(exif)} tags{gps}); re-save without it")
                    elif "exif" in im.info or "xmp" in im.info or "XML:com.adobe.xmp" in im.info:
                        hits.append(f"{rel}: has embedded metadata")
            except OSError as exc:
                hits.append(f"{rel}: can't be opened ({exc})")
    return hits


def check_git(root, deny):
    """[failures], or None when root isn't a git repository."""
    if not (root / ".git").exists():
        return None
    run = subprocess.run(["git", "-C", str(root), "log", "--all", "--format=%H%x00%ae%x00%ce%x00%B%x1e"],
                         capture_output=True, text=True, encoding="utf-8")
    if run.returncode != 0:  # no commits yet
        return [] if "does not have any commits" in run.stderr or not run.stderr.strip() else [run.stderr.strip()]
    hits = []
    for record in filter(str.strip, run.stdout.split("\x1e")):
        sha, author, committer, body = record.strip("\n").split("\x00", 3)
        short = sha[:8]
        for role, addr in (("author", author), ("committer", committer)):
            if not re.search(r"@users\.noreply\.github\.com$|^noreply@github\.com$", addr):
                hits.append(f"commit {short}: {role} address is not a noreply address")
        if deny and deny.search(body):
            hits.append(f"commit {short}: message contains a deny-list string")
        hits += [f"commit {short}: message has email {e}" for e in EMAIL.findall(body) if not SAFE_EMAIL.search(e)]
    return hits


def run_gitleaks(root, files):
    """('skipped' | 'passed' | 'failed', [findings]). Scans a copy of the shipped files
    only, because gitleaks would otherwise read gitignored local files."""
    import json

    exe = shutil.which("gitleaks")
    if not exe:
        return "skipped", ["gitleaks not installed"]
    with tempfile.TemporaryDirectory(prefix="gitleaks-") as tmp:
        stage, report = Path(tmp) / "tree", Path(tmp) / "report.json"
        for path in files:
            dest = stage / path.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        common = ["--redact", "--no-banner", "--exit-code", "9", "--report-format", "json",
                  "--report-path", str(report), "--log-level", "error"]
        for args in (["dir", str(stage)], ["detect", "--no-git", "--source", str(stage)]):
            run = subprocess.run([exe, *args, *common], capture_output=True, text=True)
            if run.returncode == 0:
                return "passed", []
            if run.returncode == 9:
                rows = json.loads(report.read_text(encoding="utf-8") or "[]")
                return "failed", [f"{Path(r['File']).relative_to(stage).as_posix()}:{r['StartLine']}: "
                                  f"gitleaks {r['RuleID']}" for r in rows]
    return "skipped", [f"gitleaks couldn't run: {(run.stderr or run.stdout).strip()[:200]}"]


# --- driver ---------------------------------------------------------------------

def verify(root=PKG, denylist=DENYLIST, use_denylist=True, gitleaks=True, quiet=False):
    """Run every check. Returns (exit code, {code: [failures]})."""
    say = (lambda *a: None) if quiet else print
    files = refcheck.shipped_files(root)
    results, deny = {}, None

    setup = []
    if use_denylist:
        if denylist.is_file():
            terms, setup = load_denylist(denylist)
            deny = deny_pattern(terms)
            if not terms:
                setup.append(f"{denylist.name} has no entries")
        else:
            setup.append(f"{denylist.name} not found: create it (see UPDATE-CHECKLIST.md) or pass --no-denylist")
    results[2] = setup + check_denylist(root, files, deny)
    results[3] = check_secrets(root, files)
    results[4] = check_account_data(root, files)
    results[5] = check_images(root, files)
    git = check_git(root, deny)
    results[6] = git or []
    results[7] = refcheck.check(root, files)

    leaks = ("skipped", ["--no-gitleaks"])
    if gitleaks:
        leaks = run_gitleaks(root, files)
        if leaks[0] == "failed":
            results[3] += leaks[1]

    say(f"scanned {len(files)} files in {root}")
    for code, hits in results.items():
        note = ""
        if code == 2 and not use_denylist:
            note = " (built-ins only: --no-denylist)"
        if code == 6 and git is None:
            note = " (not a git repository)"
        say(f"  [{code}] {NAMES[code]:<13} {'FAIL' if hits else 'ok'}{note}")
        for hit in hits[:50]:
            say(f"        {hit}")
        if len(hits) > 50:
            say(f"        ... {len(hits) - 50} more")
    # "skipped" is never reported as passed: it means no second scanner ran
    say(f"  gitleaks: {leaks[0]}{' (' + leaks[1][0] + ')' if leaks[0] == 'skipped' else ''}")
    failed = [c for c, hits in results.items() if hits]
    say("VERIFY PASSED" if not failed else f"VERIFY FAILED: {', '.join(NAMES[c] for c in failed)}")
    return (failed[0] if failed else 0), results


def selftest():
    """Seed one violation per check in a throwaway tree; each must fail with its own code."""
    from PIL import Image

    j = "".join  # fixtures are assembled at run time so this file never contains them
    clean_doc = "# Doc\n\nRun `tools/a.py`. Ask seller@example.com. IDs like 100000000001 in offer.json are dummies.\n"
    arms = [
        ("clean tree passes", None, None, 0),
        ("deny-list string", "core/notes.md", j(["Ships from ", "Springfield", "ville"]), 2),
        ("personal email", "core/notes.md", j(["mail ", "someone", "@", "mailbox.test"]), 2),
        ("user home path", "core/notes.md", j(["C:", "\\Users\\", "alice", "\\repo"]), 2),
        ("eBay OAuth token", "core/notes.md", j(["v^1.1#", "i^1#p^3#r^1#", "A" * 30]), 3),
        ("credential value", "core/.env.example", j(["EBAY_CLIENT", "_SECRET=", "PRD-", "a1b2c3"]), 3),
        ("App ID", "core/notes.md", j(["Acme-Lister-", "PRD-", "1a2b3c4d5", "-6e7f8a9b"]), 3),
        ("policy ID", "core/offer.json", j(['{"fulfillmentPolicyId": "', "2648", "4662", "0012", '"}']), 4),
        ("item URL", "core/notes.md", j(["https://www.ebay.com/itm/", "3", "8765432101"]), 4),
        ("postal code", "core/account.json.md", j(['"postalCode": "', "606", "01", '"']), 4),
        ("image with EXIF", "examples/x.jpg", "exif", 5),
        ("personal git author", None, j(["dev", "@", "mailbox.test"]), 6),
        ("dangling reference", "core/notes.md", "See `tools/missing.py`.", 7),
    ]
    failures = 0
    for label, rel, content, expected in arms:
        with tempfile.TemporaryDirectory(prefix="sanitize-selftest-") as tmp:
            root = Path(tmp)
            (root / "core" / "tools").mkdir(parents=True)
            (root / "core" / "AGENTS.md").write_text(clean_doc, encoding="utf-8")
            (root / "core" / "tools" / "a.py").write_text("print('ok')\n", encoding="utf-8")
            Image.new("RGB", (8, 8), "white").save(root / "clean.jpg")
            deny = root / "scrub.local.txt"
            deny.write_text("# test deny-list\n" + j(["Springfield", "ville"]) + "\n", encoding="utf-8")
            (root / ".gitignore").write_text("scrub.local.txt\n", encoding="utf-8")
            if rel:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
            if rel and content == "exif":
                exif = Image.Exif()
                exif[0x0110] = "Phone"
                Image.new("RGB", (8, 8), "white").save(root / rel, exif=exif)
            elif rel:
                (root / rel).write_text(content + "\n", encoding="utf-8")
            email = content if expected == 6 else "dev@users.noreply.github.com"
            git = ["git", "-C", tmp, "-c", "user.name=selftest", "-c", f"user.email={email}",
                   "-c", "commit.gpgsign=false"]
            subprocess.run(git[:3] + ["init", "-q"], check=True)
            subprocess.run(git + ["add", "-A"], check=True)
            subprocess.run(git + ["commit", "-q", "-m", "selftest"], check=True)
            code, results = verify(root, deny, gitleaks=False, quiet=True)
            others = [c for c, hits in results.items() if hits and c != expected]
            if code == expected and not others:
                print(f"PASS {label:<22} exit {code}")
            else:
                failures += 1
                detail = {c: h[:2] for c, h in results.items() if h}
                print(f"FAIL {label:<22} expected exit {expected}, got {code}: {detail}")
    print(f"\nselftest: {len(arms)} arms, {failures} failed")
    return 1 if failures else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true", help="run every check (exit 0 or 2-7)")
    mode.add_argument("--selftest", action="store_true", help="prove each check can fail")
    ap.add_argument("--no-denylist", action="store_true", help="run check 2 with built-ins only")
    ap.add_argument("--no-gitleaks", action="store_true", help="don't run gitleaks even if installed")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    code, _ = verify(use_denylist=not args.no_denylist, gitleaks=not args.no_gitleaks)
    return code


if __name__ == "__main__":
    sys.exit(main())
