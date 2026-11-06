# Update checklist (maintainers)

`core/` is the only copy of the pipeline code. The maintainer runs real listings from a clone of this repository, with the private data in a separate folder set by `EBAY_WORKSPACE` (see ADOPTION-GUIDE.md, "Alternative: run from a clone"). Change the code here, never in the data folder.

## Before every push

1. `cd core && python -m pytest tests/ -q`
2. If a payload, schema or validator rule changed: `python scripts/make_example.py`, then validate the example:
   `cd core && EBAY_ACCOUNT_FILE=account.example.json python tools/validate_payload.py ../examples/acme-hl300-headlamp/`
3. If a file was added, removed or renamed in `core/`: update `core/MANIFEST.md`.
4. `python scripts/sanitize.py --selftest`, then `python scripts/sanitize.py --verify`. Both must exit 0.
5. `python -m pytest scripts/tests -q`
6. Read the diff (`git diff --stat`, then the files). The gate catches known shapes, not everything. Watch for examples copied from real runs: real codes, IDs, slugs, prices and paths.
7. Commit with the noreply author. Check 6 of the gate fails on any other address.

## Never commit

| Path | Why |
|---|---|
| `listings/**`, `raw_data/**` | Seller data, GPS in raw photos |
| `backups/**` | File backups |
| `.env`, `account.json`, `tokens.json`, `.ebay-token-cache.json` | Credentials and seller IDs |
| `api-log.jsonl`, `*.log` | Call logs with IDs |
| `scrub.local.txt` | The private deny-list itself |

`.gitignore` and `core/.gitignore` cover all of these. Keep the data folder outside the clone so a mistaken `git add -f` can't reach it.

## The privacy gate

`scripts/sanitize.py --verify` scans every file git would ship. Each check has its own exit code:

| Exit | Check |
|---|---|
| 2 | Deny-list strings, personal emails, user home paths |
| 3 | Secret shapes, plus gitleaks if installed |
| 4 | Account IDs, item and seller URLs, ZIP codes |
| 5 | EXIF in images |
| 6 | Non-noreply commit addresses, private strings in commit messages |
| 7 | Dangling references (`scripts/refcheck.py`) |

The deny-list is `scrub.local.txt` at the repository root. It is gitignored and private to each maintainer, because the list itself is private. It holds one string per line:

- seller name, town, ZIP and location keys
- every business policy ID
- the offer and listing IDs of your real listings
- your email, your home path, and your data folder's absolute path (every spelling: `X:\folder`, `X:/folder`, `/x/folder`, without a trailing slash)
- every code or key you have redacted from photos

Add `@env <data folder>/.env` so every credential value is denied without being copied. Without the file, check 2 fails. `--no-denylist` runs only the built-ins (for CI, where the file doesn't exist).

When your account changes (a new policy, a new location, new listings), add the new values to `scrub.local.txt` before the next push.
