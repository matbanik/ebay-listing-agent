# Update checklist (maintainers)

The pipeline is developed in a private source repo that runs real listings. This package is refreshed from it. `scripts/sync.py` is the executable version of this file. If they disagree, the script wins, and this file needs fixing.

## Refresh

1. In the source repo: commit everything, then run its tests (`python -m pytest tests/ -q`).
2. `python scripts/sync.py --source <source repo> --dry-run`: lists what would change.
3. `python scripts/sync.py --source <source repo>`: copies, applies the scrub ledger and writes `scripts/last-sync.json` (source commit and date).
   - Exit 2 means a ledger entry no longer matches its source file, because the wording changed. Update `REWRITES` in `sync.py` and this file, then run it again.
   - Exit 3 means a `NEVER` path matched a `SYNC` glob. Fix the glob. Never weaken `NEVER`.
   - `stale_in_package` lists files that no longer exist in the source. Back them up, then delete them, or add them to `AUTHORED`.
4. If the source gained a file type or folder, add it to `SYNC` and to `core/MANIFEST.md`.
5. `cd core && python -m pytest tests/ -q`
6. `python scripts/make_example.py`, then validate the example:
   `cd core && EBAY_ACCOUNT_FILE=account.example.json python tools/validate_payload.py ../examples/acme-hl300-headlamp/`
7. `python scripts/sanitize.py --selftest`, then `python scripts/sanitize.py --verify`. Both must exit 0.
8. `python -m pytest scripts/tests -q`
9. Read the diff (`git diff --stat`, then the files). The gate catches known shapes, not everything.
10. Commit with the noreply author. Check 6 of the gate fails on any other address.

## Sync map

| Source | Package |
|---|---|
| `AGENTS.md`, `SETUP.md`, `requirements.txt`, `.env.example`, `account.example.json` | `core/` (same names) |
| `.agent/skills/**` | `core/.agent/skills/**` |
| `.agent/workflows/*.md` | `core/.agent/workflows/` |
| `.agent/docs/condition-grading.md`, `ebay-image-guide.md`, `pricing-strategy.md` | `core/.agent/docs/` |
| `schemas/*.json`, `templates/*`, `tools/*.py`, `tests/*.py` | `core/` (same paths) |
| `.agent/docs/research-prompt-*.md` | `docs/research-prompts/` (flattened) |

**Package-authored files** (`AUTHORED` in `sync.py`; never overwritten):

- `core/CLAUDE.md`
- `core/MANIFEST.md`
- `core/.gitignore`
- `core/.agent/context/current-focus.md`
- `core/.agent/context/known-issues.md`
- `docs/research-prompts/README.md`

Everything at the package root, plus `examples/` and `scripts/`, is also authored here.

## Scrub ledger (intended differences from the source)

| File | Source text | Package text | Why |
|---|---|---|---|
| `core/AGENTS.md` | "Save files to pomera notes before deletion" | "Back up a file before deleting it: copy it to `backups/YYYY-MM-DD/` (gitignored), or use the backup tool you chose during adoption" | Pomera MCP is the maintainer's own tool. See ADOPTION-GUIDE.md "Backup provider" |
| `core/AGENTS.md` | "Delete files without user request + pomera backup" | "Delete files without the user's request and a backup" | same |
| `core/AGENTS.md` | `archive/` line in Project Structure | removed | `archive/` isn't shipped |
| `core/AGENTS.md` | `research/` line in Project Structure | `tests/` and `backups/` lines | `research/` isn't shipped; those two folders are |
| `core/.agent/workflows/01-import-workflow.md` | "(back up to pomera notes first; see AGENTS.md)" | "(back up first; see AGENTS.md)" | Pomera |
| `core/.agent/workflows/06-batch-workflow.md` | "`.agent/context/current-focus.md` or pomera notes" | "`.agent/context/current-focus.md`" | Pomera |

Anything else that differs between the source and `core/` is drift. Change the source, or add a ledger entry here and in `REWRITES`.

## Never copy

`NEVER` in `sync.py` refuses these even if a `SYNC` glob matches:

| Path | Why |
|---|---|
| `listings/**`, `raw_data/**` | Seller data, GPS in raw photos |
| `archive/**`, `research/**`, `backups/**` | Retired scripts, deep-research output, file backups |
| `.agent/context/**` | Plans, focus and session logs for the source repo |
| `.env`, `account.json`, `tokens.json`, token caches | Credentials and seller IDs |
| `api-log.jsonl`, `*.log` | Call logs with IDs |
| `__pycache__`, `*.pyc` | Build output |

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

The deny-list is `scrub.local.txt` at the package root. It is gitignored and private to each maintainer, because the list itself is private. It holds one string per line: seller name, town, ZIP, location keys, every business policy ID, and the offer and listing IDs from the source repo, plus your email, your home path and the source repo's absolute path (every spelling: `X:\repo`, `X:/repo`, `/x/repo`, without a trailing slash). Add every code or key you have redacted from photos too. Examples in the docs tend to get copied from real runs. Add `@env <source repo>/.env` so every credential value is denied without being copied. Without the file, check 2 fails. `--no-denylist` runs only the built-ins (for CI, where the file doesn't exist).

When the source account changes (a new policy, a new location), add the new values to `scrub.local.txt` before the next sync.

## Last sync

`scripts/last-sync.json` records the source commit and date of the last refresh.
