# Google API & OAuth Setup — AdVanta AI

This runbook walks through every Google credential AdVanta needs, where each
value comes from, and how to verify it. There are **two separate OAuth clients**
(by design) plus a Google Ads developer token.

| Env var | What it is | Where it comes from |
|---|---|---|
| `GOOGLE_CLIENT_ID` | Integration OAuth client ID | Cloud Console → Credentials |
| `GOOGLE_CLIENT_SECRET` | Integration OAuth client secret | Cloud Console → Credentials |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Google Ads API token | Google **Ads** → API Center |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Manager (MCC) account ID, no dashes | Google Ads (only if using a manager account) |
| `GOOGLE_LOGIN_CLIENT_ID` | "Sign in with Google" client ID | Cloud Console → Credentials |
| `GOOGLE_LOGIN_CLIENT_SECRET` | "Sign in with Google" client secret | Cloud Console → Credentials |
| `GOOGLE_LOGIN_REDIRECT_URI` | Login callback URL | You choose (must match the registered URI) |

**Why two clients?** The *integration* client requests broad ad/analytics data
scopes; the *login* client requests only `openid email profile`. Keeping login
narrow gives a clean consent UX and lets login be verified/published
independently of the sensitive ad scopes.

### Domain reference
- **Backend (API):** `https://api.getadvanta.app` (local: `http://localhost:8000`)
- **Frontend (web):** `https://getadvanta.app` (local: `http://localhost:5173`)
- Redirect URIs always point at the **backend**.

---

## Part A — Cloud project + enable APIs

1. [Google Cloud Console](https://console.cloud.google.com) → project dropdown → **New Project** (`advanta-ai`). Keep it selected for everything below.
2. **APIs & Services → Library** → enable the APIs for the integrations you'll use:
   | Integration | API to enable |
   |---|---|
   | Google Ads | **Google Ads API** |
   | GA4 (reporting) | **Google Analytics Data API** |
   | GA4 (list properties) | **Google Analytics Admin API** |
   | Search Console | **Google Search Console API** |

   "Sign in with Google" needs **no** API enabled (it reads `oauth2/v3/userinfo`).

---

## Part B — OAuth consent screen (shared by BOTH clients)

The consent screen is configured **once per project** and used by every OAuth
client in it.

1. **APIs & Services → OAuth consent screen** (newer UI: **Google Auth Platform → Branding**).
2. **User type: External** → Create.
3. App name (`AdVanta AI`), user support email, developer contact email. Add
   `getadvanta.app` under **Authorized domains** when you have it (blank is fine for local dev).
4. **Scopes → Add**:
   ```
   openid
   https://www.googleapis.com/auth/userinfo.email
   https://www.googleapis.com/auth/userinfo.profile
   https://www.googleapis.com/auth/adwords
   ```
   Add these too if connecting GA4 / Search Console:
   ```
   https://www.googleapis.com/auth/analytics.readonly
   https://www.googleapis.com/auth/webmasters.readonly
   ```
   `adwords`, `analytics.readonly`, `webmasters.readonly` are **sensitive** scopes;
   the userinfo/openid ones are non-sensitive. None are "restricted."

   > A scope only appears in the picker once its API (Part A) is enabled. Use the
   > Filter box, or the "Manually add scopes" box to paste them directly.

5. **Test users → + Add users** → add **your own Google account** (and any teammate
   who tests). ⚠️ While in "Testing" mode, only listed test users can complete OAuth.
6. **Publishing status:** leave **Testing** for now (see Part G for going live).

---

## Part C — Integration client → `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`

1. **APIs & Services → Credentials → + Create credentials → OAuth client ID**.
2. **Application type: Web application**.
3. **Name:** `AdVanta — Integrations`.
4. **Authorized JavaScript origins:** leave **empty** (server-side redirect flow).
5. **Authorized redirect URIs** — one per box, exact, **no trailing slash**:
   ```
   http://localhost:8000/api/v1/integrations/google_ads/callback
   http://localhost:8000/api/v1/integrations/google_analytics/callback
   http://localhost:8000/api/v1/integrations/google_search_console/callback
   https://api.getadvanta.app/api/v1/integrations/google_ads/callback
   https://api.getadvanta.app/api/v1/integrations/google_analytics/callback
   https://api.getadvanta.app/api/v1/integrations/google_search_console/callback
   ```
   (The `google_ads` rows are the minimum; add the others if connecting them.)
6. **Create** → copy **Client ID** → `GOOGLE_CLIENT_ID`, **Client secret** → `GOOGLE_CLIENT_SECRET`.

The backend builds the redirect as `BACKEND_URL + /api/v1/integrations/<provider>/callback`
(`apps/api/app/integrations/base.py`), so the registered URIs must match `BACKEND_URL` exactly.

---

## Part D — Login client → `GOOGLE_LOGIN_CLIENT_ID` + `GOOGLE_LOGIN_CLIENT_SECRET`

1. **Credentials → + Create credentials → OAuth client ID** (a **second** client).
2. **Application type: Web application**.
3. **Name:** `AdVanta — Login`.
4. **Authorized JavaScript origins:** leave **empty**.
5. **Authorized redirect URIs**:
   ```
   http://localhost:8000/api/v1/auth/google/callback
   https://api.getadvanta.app/api/v1/auth/google/callback
   ```
6. **Create** → **Client ID** → `GOOGLE_LOGIN_CLIENT_ID`, **Client secret** → `GOOGLE_LOGIN_CLIENT_SECRET`.
7. `GOOGLE_LOGIN_REDIRECT_URI` is **not** from Google — it's the redirect URI you
   registered. Local: `http://localhost:8000/api/v1/auth/google/callback`;
   production: the `https://api.getadvanta.app/...` form. **Must match exactly.**

You'll now have **two** clients in the Credentials list — correct.

---

## Part E — `GOOGLE_ADS_DEVELOPER_TOKEN` (from Google **Ads**, not Cloud Console)

1. The dev token lives on a **Manager (MCC) account**. Create one if needed at
   [ads.google.com/home/tools/manager-accounts](https://ads.google.com/home/tools/manager-accounts).
2. Sign in to [ads.google.com](https://ads.google.com) with that manager account.
3. **Tools (🔧) → Setup → API Center** (only shown on manager accounts).
4. Accept the **Google Ads API Terms**.
5. The **Developer token** shown → `GOOGLE_ADS_DEVELOPER_TOKEN`.

⚠️ **Access level:** a new token defaults to **"Test account" access** — it can call
only *test* Ads accounts (real accounts return `DEVELOPER_TOKEN_NOT_APPROVED`).
- **Now:** test against a [test account](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts).
- **Before real customers:** API Center → **Apply for Basic access** (Google review — start early).

---

## Part F — `GOOGLE_ADS_LOGIN_CUSTOMER_ID` (optional, MCC only)

- Needed only when operating through a **Manager (MCC)** account (the usual setup,
  since the dev token lives on the manager).
- It's the **manager's 10-digit Customer ID** (top-right in Google Ads, shown as
  `123-456-7890`). Enter it **without dashes**: `1234567890`.
- Leave blank if you only ever call a single standalone Ads account directly.

---

## `.env` summary

```env
# Integration client (Ads / GA4 / Search Console)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_LOGIN_CUSTOMER_ID=        # blank if no manager account

# Sign in with Google (separate login client)
GOOGLE_LOGIN_CLIENT_ID=
GOOGLE_LOGIN_CLIENT_SECRET=
GOOGLE_LOGIN_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

In production set `GOOGLE_LOGIN_REDIRECT_URI=https://api.getadvanta.app/api/v1/auth/google/callback`.

---

## Verify it works

1. Restart the backend so it reads the new env.
2. Confirm you're a **Test user** on the consent screen (Part B5).
3. **Sign in with Google** → the login button → consent → you land authenticated.
4. **Connect Google Ads** → Integrations page → Connect → consent → status flips to
   Connected (test Ads account until Basic access clears).

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `redirect_uri_mismatch` | Registered URI ≠ what the backend sent | Match scheme/host/port/path exactly, no trailing slash; check `BACKEND_URL` |
| "Access blocked: app not verified" | You're not a test user (Testing mode) | Add your account under consent screen → Test users |
| `DEVELOPER_TOKEN_NOT_APPROVED` | Dev token at test-access; real account called | Use a test Ads account, or apply for Basic access |
| Scope missing from picker | That API isn't enabled | Enable it (Part A), or paste via "Manually add scopes" |
| `invalid_client` | Wrong client ID/secret, or env points at the other client | Confirm integration vs login client values |

---

## Going to production (Part G)

1. **OAuth verification:** the sensitive `adwords` (and `analytics`/`webmasters`)
   scopes require Google **app verification** before the project can be used by
   users outside your org. Needs a privacy-policy URL, an explainer/demo video,
   and domain verification. **Start early — review takes days to weeks.**
   - To launch "Sign in with Google" publicly *before* ad verification, you can
     run the **login client in its own Cloud project** (login-only, no sensitive
     scopes → no verification needed).
2. **Google Ads Basic access** (Part E) before touching real ad accounts.
3. **Production redirect URIs** registered on both clients (the `https://api.getadvanta.app/...` rows).
4. **Production env** set: the integration + login client IDs/secrets, the dev
   token, and `GOOGLE_LOGIN_REDIRECT_URI` pointing at the production callback.
