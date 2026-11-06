# Adoption questions

Answer these before copying `core/`. An adopting agent should put each one to the human and record the answers. Each answer sets a named key or rule. The default is the safe choice, so "I don't know" is a fine answer.

## Block A: gates (where the agent must stop and ask)

| # | Question | Sets | Default |
|---|---|---|---|
| A1 | Can the agent ever publish a listing without you approving it? | `AGENTS.md` "Never Do", `05-review-workflow.md` | **No.** Keep it that way: the package was not designed or tested for auto-publishing |
| A2 | Above what price should an item stop for your review before an offer is created? | `pipeline.price_review_threshold` | `200` (USD) |
| A3 | Below what confidence (identification, condition or price) should the agent ask you? | `pipeline.min_confidence` | `0.70` |
| A4 | Will you test items before listing them? If you say yes for an item, the listing may say "tested". | `tested_by_human` per item in `curator-output.json` | `false`: listings say "Not tested" |

## Block B: your seller account

`ebay_api.py setup` reads these from your account. Create the policies in Seller Hub first (EBAY-API-SETUP.md step 10).

| # | Question | Sets | Default |
|---|---|---|---|
| B1 | Which shipping policy should listings use? | `policies.fulfillment` | Pick one free-shipping policy. The pricing docs add the shipping cost into the price (`pipeline.shipping_model: free_baked_in`) |
| B2 | Are there shipping policies the agent must never use (for example a calculated-shipping policy that fails on package errors)? | `policies.disallowed_fulfillment` | none |
| B3 | Which payment policy? | `policies.payment` | your only one |
| B4 | Which return policy? | `policies.return`, `pipeline.return_days_default` | 30-day, buyer pays return shipping |
| B5 | Do you also have a 14-day return policy? Only some categories allow it. | `policies.return_14_day` | none; the 30-day policy is used |
| B6 | Where do items ship from (inventory location)? | `seller.merchantLocationKey`, `postalCode` | your only location, or `setup --create-location` |
| B7 | Your final value fee rate and per-order fee (for net-proceeds estimates) | `pipeline.fvf_rate`, `pipeline.per_order_fee` | `0.136`, `0.40`: check eBay's current fee table for your categories and store level |

## Block C: inputs and privacy

| # | Question | Sets | Default |
|---|---|---|---|
| C1 | Where do your photos come from (Google Photos download, phone, a folder)? | step 1 of `01-import-workflow.md` | Google Photos download into `raw_data/` |
| C2 | Should the agent look for codes, keys and personal data in photos and blur them? | `redact-images` skill, the "Blur sensitive text" step in `01-import-workflow.md` | **Yes** |
| C3 | Will your listing folders go into git? If so, the repository must be private. Phone photos carry GPS until they are processed, and listing folders hold your offer IDs. | `.gitignore` (`raw_data/**`, `listings/**`) | **Not committed.** Both are gitignored |
| C4 | How should files be backed up before the agent deletes them? | `AGENTS.md` "Always Do" | Copy to `backups/YYYY-MM-DD/` (gitignored). See "Backup provider" in ADOPTION-GUIDE.md |
| C5 | Where do sold comps come from? | `price-discovery` skill, `03-evaluator-workflow.md` | Terapeak in Seller Hub, by hand. Apify is optional and paid |

## Block D: environment

| # | Question | Sets | Default |
|---|---|---|---|
| D1 | Which marketplace? | `seller.marketplace`, `EBAY_MARKETPLACE_ID` | `EBAY_US` (the only one tested) |
| D2 | Start against the sandbox? | `EBAY_ENVIRONMENT` | `sandbox` until setup and one test offer work, then `production` |
| D3 | Which agent harness? | where `AGENTS.md` is read from | Any harness that reads `AGENTS.md`. Claude Code reads `CLAUDE.md`, which imports it |
