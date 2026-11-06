# Security and privacy

## What must never be committed

| File | Holds | Protected by |
|---|---|---|
| `.env` | eBay Client ID, Cert ID (client secret), RuName, user refresh token | `.gitignore` |
| `.ebay-token-cache.json`, `tokens.json` | Short-lived access tokens | `.gitignore` |
| `account.json` | Your policy IDs, inventory location key and ZIP code | `.gitignore` (`/account.json`; `schemas/account.json` is the schema and ships) |
| `raw_data/**` | Phone photos straight from the camera, **with GPS coordinates** | `.gitignore` |
| `listings/**` | Your photos, offer IDs, listing IDs, prices | `.gitignore` |
| `api-log.jsonl` | Every write call made, with IDs | `.gitignore` |

The refresh token lets anyone with it manage your listings for about 18 months. Treat `.env` like a password.

## Photos

`tools/process_images.py` strips EXIF and GPS from the images it writes. The originals in `raw_data/` keep them. Only processed images belong in `listings/`. If you ever commit images, check them first:

```bash
python -c "import sys; from PIL import Image; [print(f, dict(Image.open(f).getexif()) or 'clean') for f in sys.argv[1:]]" listings/*/*.jpg
```

Photos can also show serial numbers, license keys, shipping labels or your address. The `redact-images` skill finds and blurs them. Look at every photo before you approve a listing.

## On GitHub

- Turn on **secret scanning** and **push protection** for your repository (Settings → Code security).
- If you commit listing folders, keep the repository private. On GitHub, a fork of a public repository is public, so copy `core/` instead of forking.

## If a secret leaks

1. **Cert ID (client secret):** change it on the Application Keys page of the eBay developer portal and set the grace period to 0, so the old value stops working at once (EBAY-API-SETUP.md step 12). Put the new value in `.env`.
2. **Refresh token:** changing the Cert ID doesn't invalidate refresh tokens already issued, so a leaked refresh token needs its own fix. Run `python tools/ebay_api.py auth-url` and `exchange-code` again to get a new one. eBay's documentation doesn't clearly say how to revoke an old token; check your eBay account's privacy or third-party app settings for an option to remove the application's access, and change the Cert ID too, since a refresh token is useless without it.
3. Remove the value from the repository history (for example with `git filter-repo`), not just from the latest commit. Rotating the secret is what actually protects you. Cleaning the history comes second.

## Reporting a problem in this package

If this package itself ships something private, or a tool here mishandles credentials, open a GitHub security advisory on this repository ("Security" tab → "Report a vulnerability"). Please don't use a public issue. Don't include working secrets in the report.

## How this package is checked

Before each release, `scripts/sanitize.py --verify` checks every shipped file:

- strings from the maintainer's private deny-list
- secret shapes
- account ID shapes
- EXIF in images
- commit author addresses
- dangling references

It also runs gitleaks when installed. `--selftest` proves each check can fail. See [UPDATE-CHECKLIST.md](UPDATE-CHECKLIST.md).
