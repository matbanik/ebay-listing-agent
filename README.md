# eBay Listing Agent

Instructions, skills and tools that let an AI coding agent (Claude Code, Codex, Gemini CLI, Antigravity, Cursor and others that read `AGENTS.md`) turn product photos into eBay listings, with a human approving every publish.

```
photos → process (resize, strip GPS) → identify product + grade condition → price from sold comps
       → upload images, create an UNPUBLISHED offer → human review → publish → reconcile sold items
```

It talks to eBay's REST APIs through one Python script (`core/tools/ebay_api.py`), not an MCP server. Each agent step writes a JSON contract with a JSON Schema in `core/schemas/`, plus a short Markdown report for the human. `validate_payload.py` checks the Evaluator contract against its schema before any offer. It was extracted from a working setup that has listed and sold real items. The seller data was removed before publishing (see [SECURITY.md](SECURITY.md)).

## Start here (in this order)

| # | File | What it's for |
|---|---|---|
| 1 | [ADOPTION-QUESTIONS.md](ADOPTION-QUESTIONS.md) | Decisions to make before copying anything. Each answer sets a named key in `account.json` or a rule in `AGENTS.md` |
| 2 | [EBAY-API-SETUP.md](EBAY-API-SETUP.md) | Getting eBay API access from zero: developer account, keys, RuName, consent, sandbox |
| 2a | [PRIVACY-TEMPLATE.md](PRIVACY-TEMPLATE.md) | Fill-in privacy policy for the RuName eBay requires (EBAY-API-SETUP.md step 5) |
| 3 | [ADOPTION-GUIDE.md](ADOPTION-GUIDE.md) | Copy `core/`, install, configure, validate the example, list your first item |
| 4 | [core/MANIFEST.md](core/MANIFEST.md) | Every file in the package and what it does, plus what was left out on purpose |
| 5 | [examples/](examples/) | One complete synthetic listing folder that passes the validator |
| 6 | [UPDATE-CHECKLIST.md](UPDATE-CHECKLIST.md) | For maintainers: how the package is refreshed from the source repo and checked for private data |

## Safety rules built in

These are in `core/AGENTS.md`, and the tools enforce them where they can:

1. **Nothing publishes without a human.** The Lister stops at an unpublished offer, and `ebay_api.py publish` refuses to run without `--confirm`. Changes to live listings need `--confirm` too, and `delete-offer` refuses any offer that is already published.
2. **No "tested" or "working" claims** unless you tested the item yourself (`tested_by_human`). `validate_payload.py` rejects the wording otherwise.
3. **Every condition note ends with "Condition assessed from photos only."** The validator checks for it.
4. **Price and confidence gates.** Items above `pipeline.price_review_threshold` (default $200), or with any confidence below `pipeline.min_confidence` (default 0.70), stop for a human. The validator rejects a high-priced item that isn't flagged for review and warns on low pricing confidence. The identification and condition confidence gates are agent rules in `AGENTS.md`, not validator checks.
5. **No guessed brands or model numbers.** When the photos don't show the brand or model, the agent asks instead of guessing.
6. **The validator runs before every offer:** the Evaluator schema, condition enum and ID, disclaimer, policy IDs, image URLs. The Curator checks which conditions the category accepts (`ebay_api.py condition-policies`).

## What you need

- An eBay seller account (US marketplace; others are untested) and a free eBay developer account
- Python 3.10+ and ImageMagick 7 (`core/SETUP.md`)
- An AI agent harness that can run shell commands and read images

## Limitations

- **The AI identification gets things wrong.** Brand, model and condition come from photos. Read every listing before you approve it. That is why the human gate exists.
- **eBay's API has no sold prices.** The Finding API was shut down in February 2025, and the Browse API shows only active listings (the price ceiling, not the market price). Sold comps come from Terapeak in Seller Hub (manual, free) or a paid scraper (the `price-discovery` skill shows Apify). Expect to do this step in a browser.
- **Only EBAY_US is tested.** Other marketplaces need different category trees, languages and policies.
- **Fees and policies change.** `pipeline.fvf_rate` and `per_order_fee` are estimates. Check eBay's current fee table.
- **Shipping:** the pricing docs assume free shipping with the cost built into the price (`pipeline.shipping_model: free_baked_in`). Calculated shipping isn't modeled.

## Layout

```
core/           the part you copy into your own repo (AGENTS.md, tools, skills, workflows, schemas, tests)
examples/       a synthetic listing folder showing every pipeline artifact
docs/           research prompts used while designing the pipeline (historical)
scripts/        maintainer tools: sync from the source repo, privacy gate, reference check
```

## License

MIT, see [LICENSE](LICENSE). Not affiliated with or endorsed by eBay. "eBay" is a trademark of eBay Inc. You are responsible for following eBay's API License Agreement and selling policies. See [NOTICE](NOTICE) for credits.
