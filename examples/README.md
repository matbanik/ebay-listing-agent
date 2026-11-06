# Examples

`acme-hl300-headlamp/` is one listing folder as it looks after the Lister step, just before human review. It shows every file the pipeline writes for a listing.

Everything in it is invented. "Acme" is a placeholder brand, the sold comps and URLs are made up, the image URLs point nowhere, the policy IDs come from `core/account.example.json`, and the two photos are drawings made by `scripts/make_example.py`, so they carry no EXIF. The category (106984, Headlamps), the item specifics and the condition enum are real eBay US values, so the payloads have the shape the API accepts. The folder has never been sent to eBay.

| File | Written by | What it is |
|---|---|---|
| `acme-hl300-headlamp-01.jpg`, `-02.jpg` | Import (`process_images.py`, `organize_raw.py`) | Processed photos; `-01` is the hero |
| `curator-output.json`, `curator-report.md` | Curator | Identification and condition grade (`schemas/curator-output.json`) |
| `evaluator-output.json`, `evaluator-report.md` | Evaluator | Confirmed identity, comps, price, listing specs (`schemas/evaluator-output.json`) |
| `image-urls.json` | Lister (`ebay_api.py upload-images`) | eBay-hosted image URLs, hero first |
| `inventory-item.json` | Lister | Body for `ebay_api.py put-item` |
| `offer.json` | Lister | Body for `ebay_api.py create-offer`; `_offerId` is added after the call |
| `listing-draft.md` | Lister | Status and review checklist for the human gate |

Some details worth noticing:

- `tested_by_human` is `false`, so the description says "Not tested by the seller" and makes no "working" claim.
- The condition text ends with the required disclaimer, "Condition assessed from photos only."
- The price ($24.99) includes the shipping estimate, because the listing uses free shipping.

Check it with the validator from `core/`:

```bash
cd core
EBAY_ACCOUNT_FILE=account.example.json python tools/validate_payload.py ../examples/acme-hl300-headlamp/
```

The result is `VALIDATION PASSED`, with one warning: publishing needs human approval. To regenerate the folder, run `python scripts/make_example.py` from the package root.
