# Getting eBay API access

This guide is for a seller who has never used the eBay developer portal. It covers everything from a new developer account to a working `.env` and `account.json`, so that `tools/ebay_api.py` can manage listings on **your own** seller account.

> **Last verified: 2026-11-06** against developer.ebay.com. eBay renames portal pages from time to time. If a label here doesn't match what you see, the linked eBay page is the authority. Please open an issue so this guide can be fixed.

Commands run from the root of your copy of `core/`. Setup takes about an hour of your time, but allow a day or two in total, because developer account approval can take a business day.

## 1. Prerequisites

- An eBay **seller** account in good standing, with payments set up, that you can sign in to. This is the account the listings go on.
- The US marketplace (`EBAY_US`). Other marketplaces are untested.
- Python 3.10+ and the install from `SETUP.md` section 1.

## 2. Join the eBay Developers Program

1. Go to <https://developer.ebay.com/signin?tab=register>.
2. Fill in the form, re-enter your email, accept the **API License Agreement**, complete the robot check, then select **Join**.
3. eBay asks for a business email address if you have one. Approval takes **about one business day**. You can't create keys until it is approved.

The developer account is separate from your seller account. You can use the same email, but they are different logins.

eBay guide: [Get started with eBay APIs](https://developer.ebay.com/develop/guides-v2/get-started-with-ebay-apis)

## 3. Create your keysets

1. Signed in to developer.ebay.com, open **Your Account → Application Keys** (<https://developer.ebay.com/my/keys>).
2. Under **Sandbox**, select **Create a keyset**. Enter an application title (for example "my-ebay-lister"), confirm the environment, and select **Create keyset**.
3. Do the same under **Production**.

Each keyset shows three values:

| Value | Goes in `.env` as | Notes |
|---|---|---|
| **App ID (Client ID)** | `EBAY_CLIENT_ID` | Can't be changed |
| **Cert ID (Client Secret)** | `EBAY_CLIENT_SECRET` | **Secret.** Can be changed if it leaks (step 12) |
| Dev ID | not used | Identifies your developer profile. The REST APIs don't need it |

The Sandbox and Production keysets have different values. `.env` holds one environment at a time (step 6).

eBay guide: [OAuth credentials](https://developer.ebay.com/api-docs/static/oauth-credentials.html)

## 4. Activate the Production keyset (account deletion notifications)

A new Production keyset is **disabled** ("Your Keyset is currently disabled") until you deal with eBay's **Marketplace Account Deletion** notifications. eBay must be able to tell apps that store eBay user data when a user closes their account. The Sandbox keyset works without this step.

On **Application Keys**, click the **Notifications** link next to your Production App ID. This opens **Alerts and Notifications**. There are two options:

- **Opt out (exemption).** Turn on **Not persisting eBay data**, confirm, choose an **Exemption reason**, add any explanation under "Additional information", and select **Submit**. eBay offers this to apps that are "not persisting any eBay data". It warns that "failure to provide correct information may result in penalties or having their account disabled."
- **Subscribe an endpoint.** Choose **Marketplace Account Deletion** and enter:
  - an alert email
  - an HTTPS **notification endpoint** that you host
  - a **verification token** of 32 to 80 characters (letters, digits, `_` and `-`)

  eBay sends a challenge request to the endpoint, which must answer it correctly. It must also accept the notifications eBay posts later.

**Which one applies to you is your decision.** What this pipeline does:

- It runs only on your own seller account. It never signs in other eBay users and stores no buyer data.
- It does keep files about **your own** listings on your disk: titles, prices, offer IDs and listing IDs.

eBay's wording ("any eBay data") doesn't say whether that counts. Read the guide below, answer the exemption form truthfully, and describe what you store. If eBay doesn't accept the exemption, subscribe an endpoint. Developers on eBay's forum report keysets that stayed "Non Compliant" after applying, so keep using the Sandbox keyset until the Production one shows as enabled.

eBay guide: [Marketplace account deletion](https://developer.ebay.com/develop/guides/sell/marketplace-user-account-deletion)

## 5. Create a RuName (redirect URL name)

The consent step in step 7 needs a **RuName**. This is an eBay-generated name for your redirect settings, not a URL.

1. On **Application Keys**, click **User Tokens** next to the App ID of the keyset (Sandbox first, then Production; each keyset has its own RuName).
2. On **User Tokens (eBay Sign-In)**, open **Get a Token from eBay via Your Application** and click "You have no Redirect URLs. Click here to add one."
3. If asked, fill in the legal address form and select **Continue to create RuName**.
4. Fill in the fields:

| Field | What to enter |
|---|---|
| **Display Title** | Shown to you on the consent page, for example "My eBay Lister" |
| **Privacy Policy URL** | Any page you control describing what the app stores. eBay requires one. [PRIVACY-TEMPLATE.md](PRIVACY-TEMPLATE.md) is a starting point: fill it in and publish it (for example as a GitHub Gist or a page in a public repo) |
| **Auth Accepted URL** | Where eBay sends the browser after you accept. Any HTTPS page works, because you copy the address from the browser bar (step 7). Nothing needs to run there |
| **Auth Declined URL** | Where eBay sends you if you decline. Any HTTPS page |

5. Save it, then copy the **RuName** (it looks like `YourName-YourApp-ab12-cdefgh`) into `EBAY_REDIRECT_URI`.

Third-party guides mention an "OAuth Enabled" option on this form. If you see it, turn it on. eBay's own page doesn't mention it.

The OAuth `redirect_uri` parameter takes the **RuName value**, not the accepted URL. Putting a URL there is the most common cause of `redirect_uri` errors.

eBay guide: [Getting your redirect_uri value](https://developer.ebay.com/api-docs/static/oauth-redirect-uri.html)

## 6. Fill in `.env`

```bash
cp .env.example .env        # gitignored; never commit it
```

Start with the **Sandbox** values:

```ini
EBAY_ENVIRONMENT=sandbox
EBAY_CLIENT_ID=<Sandbox App ID>
EBAY_CLIENT_SECRET=<Sandbox Cert ID>
EBAY_REDIRECT_URI=<Sandbox RuName>
# left empty; step 7 fills it in
EBAY_USER_REFRESH_TOKEN=
```

To switch to Production later, replace all four values with the Production ones, set `EBAY_ENVIRONMENT=production`, and repeat step 7. A refresh token belongs to one environment and one keyset.

Real environment variables override `.env`, which is handy for CI. Never print these values, and never paste them into an AI chat.

## 7. Consent and refresh token

```bash
python tools/ebay_api.py auth-url
```

1. Open the printed URL in a browser. Sign in as the **seller account** the listings belong to, then accept. For Sandbox, sign in as a sandbox test user instead. Create one first if you don't have one (step 9, item 1).
2. eBay redirects to your Auth Accepted URL. Copy the **whole address** from the browser bar. It contains `code=...`.
3. Within **5 minutes** (the code expires after 299 seconds, and works only once):

```bash
python tools/ebay_api.py exchange-code "<the whole redirect URL>"
```

The command decodes the code (eBay URL-encodes it), exchanges it, and writes `EBAY_USER_REFRESH_TOKEN` into `.env`. It reports how many days the token is valid.

| Token | Lifetime | Handling |
|---|---|---|
| Authorization code | 299 seconds, single use | You paste it once |
| Access token | 2 hours | Refreshed automatically, cached in `.ebay-token-cache.json` (gitignored) |
| Refresh token | about 18 months | Repeat this step when it expires (errors 1001/1100 that don't go away) |

eBay guide: [Authorization code grant](https://developer.ebay.com/api-docs/static/oauth-authorization-code-grant.html)

## 8. Scopes

`auth-url` asks for the scopes every command needs. Browse uses an application token (client credentials) that the tool gets on its own. Every other command, Taxonomy included, uses your user token.

| Scope | Used for |
|---|---|
| `https://api.ebay.com/oauth/api_scope` | Taxonomy (categories, aspects), condition metadata; Browse through the application token |
| `https://api.ebay.com/oauth/api_scope/sell.inventory` | Inventory items, offers, publish, inventory locations, **image upload (Media API)** |
| `https://api.ebay.com/oauth/api_scope/sell.account` | Business policies, program opt-in |
| `https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly` | Optional. Sale prices and orders, if you extend `reconcile` |

To add a scope, consent again with it: `python tools/ebay_api.py auth-url --scope <scope URL>`, then `exchange-code`.

## 9. Sandbox

The sandbox lets you try every write call without real listings.

1. Create a test user: **Tools & Samples → Sandbox user registration** on developer.ebay.com, or **Register a new Sandbox user** on the User Tokens page. Usernames get a `TESTUSER_` prefix.
2. Run step 7 with the Sandbox values in `.env`, signing in as that test user.
3. The test user starts with no business policies and no inventory location, and `setup` needs both. Run `python tools/ebay_api.py setup --opt-in --confirm` first (error 20403, "not BP opted in", means this step is missing). Then:
   - **Location:** `setup --create-location ... --confirm` (step 10).
   - **Policies:** `ebay_api.py` has no command that creates policies, and it is unconfirmed whether the sandbox site offers a Business policies page. If you can't find one, create them with the Account API calls `createFulfillmentPolicy`, `createPaymentPolicy` and `createReturnPolicy`, for example from eBay's API Explorer while signed in as the test user. eBay guide: [Business policies](https://developer.ebay.com/api-docs/sell/static/seller-accounts/business-policies.html).
   - **Or skip the sandbox for setup.** Steps 10 onward are safe in Production: the pipeline stops at unpublished offers, which buyers can't see, and nothing publishes without `publish --confirm`. If you choose this, delete test offers with `delete-offer`.

Sandbox limits:

- Browse data is sparse and partly simulated, so don't price anything from it.
- eBay's documentation disagrees on whether the Media API (image upload) works in Sandbox. If `upload-images` fails there, test it in Production on a draft you never publish.
- The sandbox user's policies, location and listings are separate from your real account.

eBay guide: [Sandbox test users](https://developer.ebay.com/api-docs/static/sandbox-test-users.html)

## 10. Seller account setup → `account.json`

The pipeline needs business policies (shipping, payment, returns) and an inventory location.

1. Check: `python tools/ebay_api.py policies`. An error about Business Policies means the account isn't opted in. Run `python tools/ebay_api.py setup --opt-in --confirm`. eBay says it can take **up to 24 hours** to take effect.
2. In **Seller Hub → Account → Business policies**, create the policies you chose in `ADOPTION-QUESTIONS.md` Block B:
   - one shipping policy (free shipping, for the default pricing model)
   - one payment policy
   - a 30-day return policy (buyer pays)
3. Write `account.json`:

```bash
python tools/ebay_api.py setup --dry-run      # what it found, and what it can't decide
python tools/ebay_api.py setup                # writes account.json (gitignored)
```

When you have several policies of a kind, `setup` asks you to choose with `--fulfillment ID`, `--payment ID`, `--return ID` or `--return-14-day ID`. With no inventory location, create one:

```bash
python tools/ebay_api.py setup --create-location --location-key HOME-01 --postal-code <ZIP> --city <city> --state <ST> --confirm
```

eBay guide: [Business policies](https://developer.ebay.com/api-docs/sell/static/seller-accounts/business-policies.html)

## 11. Verify

```bash
python tools/ebay_api.py setup --dry-run              # "problems": [] means ready
python tools/ebay_api.py policies
python tools/ebay_api.py categories "flashlight"
python tools/ebay_api.py browse "flashlight" --limit 1
python tools/ebay_api.py reconcile                    # empty on a fresh copy; that's fine
```

All five should succeed. Back in ADOPTION-GUIDE.md, continue with step 6.

## 12. Limits and hygiene

- **Call limits.** The defaults are far above what one seller uses:

  | API | Calls per day |
  |---|---|
  | Inventory | 2,000,000 |
  | Media | 200,000 |
  | Account | 25,000 |
  | Browse | 5,000 |
  | Taxonomy | 5,000 |

  The Developer Analytics API reports your current limits. eBay's **Application Growth Check** raises them. Separately, eBay blocks listings for 24 hours after 250 revisions in a day.
- **If the Cert ID leaks:**
  - Change it on Application Keys, choosing a grace period of 0 so the old one stops working at once, and put the new value in `.env`.
  - Existing refresh tokens keep working after the change, so if the refresh token leaked too, also get a new one (step 7).
  - eBay guide: [Resetting your Cert ID](https://developer.ebay.com/api-docs/static/gs_resetting-your-cert-id-new.html).
- **On GitHub,** turn on secret scanning and push protection, and keep `.env` out of every commit. See SECURITY.md.

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `invalid_grant` from `exchange-code` | The code was used already, or is more than 5 minutes old | Run `auth-url` again and paste the new redirect URL right away |
| `redirect_uri` error on the consent page or in `exchange-code` | `EBAY_REDIRECT_URI` holds a URL, or the RuName of the other environment | Use the RuName for the keyset in `.env` (step 5) |
| `invalid_client` | Client ID and secret from different keysets, or the wrong environment | Copy both from the same keyset; check `EBAY_ENVIRONMENT` |
| "Keyset is currently disabled" | The Production keyset isn't activated | Step 4 |
| 1001 that persists | Refresh token expired or revoked | Step 7 |
| 1100 | The token lacks a scope | Step 8: consent again with the scope |
| 20403 | Usually not opted in to Business Policies, but it is a generic "invalid field" error | Read `longMessage`. For opt-in: `setup --opt-in --confirm`, then wait |
| 25709 | Bad Content-Language | `EBAY_CONTENT_LANGUAGE=en-US` |
| 25002 "already exists" | An offer exists for that SKU | `offers --sku <slug>`, set `_offerId`, then `update-offer` |
| 25002 "System error" | eBay-side, usually temporary | Wait a minute and retry |
| 429 | Rate limited | Wait for the `Retry-After` time |

The `ebay-api` skill (`.agent/skills/ebay-api/SKILL.md`) has the full error table. The tool prints a `hints` field for the errors it recognizes.
