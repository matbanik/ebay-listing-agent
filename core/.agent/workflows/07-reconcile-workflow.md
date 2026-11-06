---
description: Check live eBay status of every listing and archive the sold ones
---

# 07 — Reconcile Workflow

Find out which listings are still live and which have sold, then archive sold items so `listings/` holds only active and in-progress work. Uses the `reconcile-listings` skill.

Run it:
- before starting a new batch
- after eBay sends "You made the sale" emails
- whenever someone asks "what is still listed?"

## Steps

### 1. Report (read-only)

```bash
python tools/ebay_api.py reconcile
```

Show the human the `summary`: ACTIVE, SOLD, ENDED, NEVER_LISTED and NO_OFFER, with listing URLs. Nothing changes yet.

### 2. Archive sold items

```bash
python tools/ebay_api.py reconcile --archive
```

- **SOLD folders** move from `listings/` to `listings/archive/`, and each `listing-draft.md` gets a dated `Reconciled ...: SOLD` stamp.
- **Archived folders** get their stamp refreshed.
- **Re-run check:** the output's `next` should read "Nothing to archive".

### 3. Handle the flags (ask the human)

| `action` | What to do |
|----------|------------|
| `review: not live and not sold` (ENDED / NEVER_LISTED / NO_OFFER in `listings/`) | Ask: relist (`/review-workflow` → `publish`), fix the SKU, or archive with `git mv listings/{slug} listings/archive/{slug}` |
| `still live but archived` | `git mv listings/archive/{slug} listings/{slug}` |
| `NOT moved: ... already exists` | Two folders share a slug. Compare them and ask the human before merging or renaming |

Never delete a folder or end a live listing as part of reconcile.

### 4. Update context

- `.agent/context/current-focus.md`: the list of live listings.
- `.agent/context/known-issues.md`: close issues that only applied to now-sold listings.

### 5. Commit (only if the user asks)

```bash
git add -A listings/ .agent/context/
git commit -m "chore: reconcile listings, archive sold items"
```

Check that the author is the noreply address before committing.

## Output

- `listings/` contains only ACTIVE or in-progress items.
- Every sold item is in `listings/archive/{slug}/` with a dated stamp.
- A short report to the human lists live items (title, price, URL) and newly archived items.
