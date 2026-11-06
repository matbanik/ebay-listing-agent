# Adoption guide

Steps for an AI agent, or a person, setting this pipeline up in a new repository. Do them in order. Each step says how to check that it worked.

## 1. Answer the questions

Go through [ADOPTION-QUESTIONS.md](ADOPTION-QUESTIONS.md) with the human and write the answers down. You'll need them in steps 5 and 6.

## 2. Copy `core/` into a new repository

```bash
git clone https://github.com/<owner>/ebay-listing-agent.git
mkdir my-ebay && cp -r ebay-listing-agent/core/. my-ebay/
cd my-ebay && git init -b main
```

Copy the *contents* of `core/`, dotfiles included (`.gitignore`, `.env.example`, `.agent/`). The repository root of your copy is what `AGENTS.md` calls the repo root.

Make the repository **private** if you will ever commit listing folders (question C3). On GitHub, a fork of a public repository is public, so copy instead of forking.

Check: `ls -a` shows `AGENTS.md`, `.gitignore`, `.agent/`, `tools/`, `listings/`, `raw_data/`.

## 3. Install

Follow `SETUP.md` section 1 (Python packages, ImageMagick 7).

Check: `python -m pytest tests/ -q` passes, and `magick -version` reports 7.x.

## 4. Get eBay API access

Follow [EBAY-API-SETUP.md](EBAY-API-SETUP.md) up to and including step 7 (refresh token in `.env`). Start with `EBAY_ENVIRONMENT=sandbox`, and create the sandbox test user (step 9, item 1) before step 7.

Check: `python tools/ebay_api.py categories "flashlight"` returns category suggestions.

## 5. Configure the seller account

EBAY-API-SETUP.md step 10: create the policies in Seller Hub to match Block B, then:

```bash
python tools/ebay_api.py setup --dry-run     # shows what it found and what it can't decide
python tools/ebay_api.py setup [--fulfillment ID --return ID ...]
```

Then edit the `pipeline` section of `account.json` to match Block A and B7.

Check: `setup --dry-run` shows `"problems": []`.

## 6. Apply the other answers

- **C1 photo source:** if photos don't come from Google Photos, edit step 1 of `.agent/workflows/01-import-workflow.md`.
- **C2 redaction:** if you answered no, remove the "Blur sensitive text" step from `01-import-workflow.md`. Keeping it is cheap.
- **C4 backups:** see "Backup provider" below.
- **C5 comps:** if you use Apify, `pip install apify-client`. Keep the API token in `.env` and never in a skill file.

## 7. Validate the example

Copy the synthetic listing from this package and run the validator against the example account file:

```bash
cp -r ../ebay-listing-agent/examples/acme-hl300-headlamp listings/
EBAY_ACCOUNT_FILE=account.example.json python tools/validate_payload.py listings/acme-hl300-headlamp/
```

Check: `VALIDATION PASSED`, with one warning that publishing needs human approval. Then delete the copy (`rm -r listings/acme-hl300-headlamp`). It is test data, and its image URLs point nowhere.

## 8. First real item

Put the photos for one item in `raw_data/` and ask the agent to run the workflows in order:

| Step | Workflow | You do |
|---|---|---|
| 1 | `01-import-workflow.md` | Drop the photos in; check the grouping |
| 2 | `02-curator-workflow.md` | Correct the identification if it's wrong |
| 3 | `03-evaluator-workflow.md` | Supply sold comps (Terapeak) when asked |
| 4 | `04-lister-workflow.md` | Nothing. It stops at an unpublished offer |
| 5 | `05-review-workflow.md` | Read `listing-draft.md`, then approve or reject |
| later | `07-reconcile-workflow.md` | Archive sold items |

Harnesses that load `.agent/workflows/` (such as Antigravity) offer these as slash commands (`/import-workflow`). In other harnesses, ask the agent to "follow `.agent/workflows/01-import-workflow.md`".

Do the first item in the sandbox if you can. Sandbox listings aren't real, but the policies and location must exist for the sandbox user. Creating sandbox policies takes extra work (EBAY-API-SETUP.md step 9, item 3). If you skip it, do the first item in Production and stop at the unpublished offer.

## Backup provider

`AGENTS.md` says to back up a file before deleting it. The package default is a dated copy under `backups/` (gitignored):

```bash
mkdir -p backups/$(date +%F) && cp -r listings/old-item backups/$(date +%F)/
```

If you use a notes or backup tool through MCP, put its name in that rule in `AGENTS.md` ("Always Do" and "Never Do") and in `01-import-workflow.md`.

**Provider substitution: Pomera MCP.** The maintainer uses the Pomera notes MCP server (`pomera_notes`) for these backups. If you have it, the rule reads: "Save files to pomera notes before deletion". Without an MCP backup tool, keep the `backups/` default. Don't drop the rule.

## Updating later

New versions of this package change files in `core/`. Compare them with your copy (`diff -r`) and merge by hand. Keep your `AGENTS.md` edits from step 6. Your `account.json`, `.env` and `listings/` are never part of the package, so an update can't overwrite them.

## Alternative: run from a clone, data in a separate folder

Instead of copying `core/`, you can keep a clone of this repository for the code and a separate private folder for your data. Set `EBAY_WORKSPACE` to that folder and every tool reads and writes `.env`, `account.json`, the token cache, `listings/` and `raw_data/` there:

```bash
export EBAY_WORKSPACE=~/my-ebay          # in Claude Code: "env" in that folder's .claude/settings.json
cd ~/my-ebay
python ~/ebay-listing-agent/core/tools/ebay_api.py setup --dry-run
```

Updating is then `git pull` in the clone. Your rule changes (step 6) go in a short `AGENTS.md` in the data folder that tells the agent to follow `core/AGENTS.md` with those differences. Never put the data folder inside the clone.
