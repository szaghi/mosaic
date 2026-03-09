---
title: Authenticated Access
---

# Authenticated Access

Some publishers and institutional repositories do not offer a public API but
do grant access to logged-in users — for example via a university single
sign-on (Shibboleth/SAML), a personal account, or a library proxy.

MOSAIC can open a real browser window, let you log in interactively, save
the session (cookies and local storage), and reuse it in future runs to
download PDFs you are legally entitled to access — without asking you to log
in again every time.

::: info Prerequisite
This feature requires the `[browser]` optional extra and at least one
Playwright browser. See [Installation](./installation#optional-browser-sessions)
for setup instructions.
:::

## How it works

### Saving a session

```
mosaic auth login <name> --url <login-url>
```

1. A headed (visible) browser window opens at `<login-url>`.
2. You log in manually — SSO, username/password, 2FA — whatever the site
   requires.
3. **Wait until you are fully logged in** — the publisher page should show
   your name or a "Log out" link. Do not press Enter during the login
   redirect chain.
4. Switch back to the terminal and press **Enter**.
5. MOSAIC saves the browser session (cookies and local storage) to
   `~/.config/mosaic/sessions/<name>.json` and records the login domain
   alongside it.

::: warning Complete the login before pressing Enter
If you press Enter while the browser is still going through SSO redirects,
the session will be saved in a partially authenticated state and downloads
will fail silently. Always verify the publisher page shows you as logged in
before returning to the terminal.
:::

### Automatic download fallback

When you run `mosaic search --download` or `mosaic get`, the downloader
tries three strategies in order:

1. **Known PDF URL** — used directly if the search source returned one.
2. **Unpaywall** — resolves a legal open-access copy by DOI.
3. **Browser session** — if steps 1 and 2 fail, MOSAIC iterates over all
   saved sessions, opens a headless browser with the session cookies,
   navigates to the paper page, and downloads the PDF automatically.

No extra flags are needed — the browser step runs silently whenever saved
sessions are found and the other methods come up empty.

### Domain matching

Each session is associated with the domain of the `--url` you passed at
login time (e.g. `link.springer.com` for a Springer login). When
downloading, MOSAIC first tries to match the paper's URL domain against
saved session domains. If no direct match is found (e.g. the DOI resolves
via an intermediate hub like `linkinghub.elsevier.com`), MOSAIC falls back
to trying all saved sessions in order — the browser follows the full
redirect chain including JavaScript redirects.

## Publisher compatibility

Not all publishers are equally automatable. The feature works best with
publishers that use standard cookie-based session management.

| Publisher | Search | PDF download | Notes |
|---|---|---|---|
| **Springer Nature** | ✅ | ✅ | Search is public (no login needed); session used for PDF download of subscribed content |
| **Wiley** | — | ✅ | Standard cookie session |
| **Taylor & Francis** | — | ✅ | Standard cookie session |
| **Cambridge University Press** | — | ✅ | Standard cookie session |
| **ScienceDirect (Elsevier)** | ✅ | ⚠️ | Search works via browser session. PDF download blocked by Cloudflare on the `/pdfft/` endpoint — falls back to Unpaywall. See [ScienceDirect notes](#sciencedirect-elsevier) below. |

::: info Wiley, Taylor & Francis, Cambridge
These publishers do not yet have a dedicated browser-based search source.
The saved session is used only for PDF downloading of papers found via other
sources (arXiv, Semantic Scholar, OpenAlex, Springer, etc.).
:::

::: tip Springer Nature
Springer search works **without** a saved session — the search interface is
publicly accessible and MOSAIC uses headless Firefox automatically. A session
is only needed to download PDFs of subscribed articles.

Login URL: `https://link.springer.com` (homepage). Click
**Log in → Log in via Institution** from there.
:::

## Session storage

Sessions are stored as standard Playwright `storageState` files:

```
~/.config/mosaic/sessions/
  springer.json
  wiley.json
  myuni.json
```

Each file contains only browser cookies and local storage — **no passwords
are ever stored**.

Sessions expire when the website's cookies expire (typically days to weeks
for most publishers, up to a year for Cloudflare-protected sites like
ScienceDirect). Re-run `mosaic auth login` to refresh.

MOSAIC checks cookie expiry timestamps when deciding whether to activate a
browser-based search source. If all timed cookies in a session file have
passed their expiry, the source is excluded from active sources at startup —
you will not see it in results and no browser is launched. Run
`mosaic auth status` to see which sessions are still valid.

## Commands

### `mosaic auth login`

```
mosaic auth login [OPTIONS] NAME
```

| Argument / Option | Description |
|---|---|
| `NAME` | Arbitrary label for the session (e.g. `springer`, `myuni`) |
| `--url` / `-u` | URL to open in the browser (required) |

MOSAIC tries browsers in order: **Firefox → Chromium → WebKit**. The first
one that is installed is used automatically.

::: tip Why Firefox first?
Firefox's TLS fingerprint passes Cloudflare Bot Management on sites like
ScienceDirect where headless Chromium is blocked. Using the same browser
for both login and headless reuse also ensures that Cloudflare session
cookies (`cf_clearance`) remain valid — they are bound to the browser's
TLS fingerprint.
:::

**Examples:**

```bash
# Log in to Springer Nature
mosaic auth login springer --url https://link.springer.com

# Log in to Wiley
mosaic auth login wiley --url https://onlinelibrary.wiley.com

# Log in via your university SSO
mosaic auth login myuni --url https://library.myuni.edu/login

# Log in to ScienceDirect (Elsevier) — see compatibility note above
mosaic auth login elsevier --url https://www.sciencedirect.com
```

### `mosaic auth status`

List all saved sessions:

```bash
mosaic auth status
```

```
 Name       Domain               Saved             Valid  Path
 elsevier   www.sciencedirect…   2026-03-09 11:21  ✓      ~/.config/mosaic/sessions/elsevier.json
 springer   link.springer.com    2026-03-09 10:14  ✓      ~/.config/mosaic/sessions/springer.json
 myuni      library.myuni.edu    2026-02-01 09:15  ✗ exp  ~/.config/mosaic/sessions/myuni.json
```

- **Domain** — which URLs the session will be tried for during automatic download.
- **Valid** — MOSAIC inspects cookie expiry timestamps in the saved file. ✓ means at least one timed cookie is still active; ✗ expired means all timed cookies have passed their expiry date and the session will be excluded from active sources until refreshed.

### `mosaic auth logout`

Remove a saved session:

```bash
mosaic auth logout springer
```

## ScienceDirect (Elsevier) {#sciencedirect-elsevier}

ScienceDirect is the only publisher for which a browser session enables both
**search** and (partial) **download** support. The behaviour depends on which
credentials are configured:

| Credentials | What MOSAIC does |
|---|---|
| API key | Uses the Elsevier Article Search API (fast, reliable). PDF via Unpaywall. |
| Browser session (no API key) | Uses headless Firefox to run searches on `sciencedirect.com`. PDF via Unpaywall only. |
| Neither | ScienceDirect source is skipped entirely. |

The API key always takes precedence when both are present.

### Saving the ScienceDirect session

```bash
mosaic auth login elsevier --url https://www.sciencedirect.com
```

Complete the full institutional SSO flow until your name appears on
ScienceDirect, then press **Enter**. Do not press Enter during intermediate
redirects.

::: warning Same browser for login and search
MOSAIC uses Firefox for both headed login and headless search. The Cloudflare
`cf_clearance` cookie is bound to the browser's TLS fingerprint — if you log
in with Chromium and search with Firefox (or vice versa) the session is
rejected and you will be redirected to the SSO page. Ensure Firefox is
installed (`playwright install firefox`) before logging in.
:::

### PDF download limitation

The ScienceDirect PDF endpoint (`/pdfft/`) enforces Cloudflare Bot Management
rules that are stricter than article pages. Even with a valid institutional
session, automated PDF downloads from this endpoint are blocked. The browser
session therefore enables **search only**; PDF retrieval always falls back to
Unpaywall for open-access copies.

For reliable PDF access to subscribed content, use the API key combined with
campus IP or institutional VPN — see
[ScienceDirect configuration](./configuration#sciencedirect-elsevier).

### Session expiry and warnings

Elsevier's Cloudflare session cookies (`cf_clearance`) typically expire after
a year, while the shorter-lived `__cf_bm` cookie (30 minutes) is refreshed
automatically during each browser session.

MOSAIC detects expiry at two points:

- **At startup** — cookie timestamps in the session file are checked. An
  expired session is excluded from active sources before any browser is
  launched. `mosaic auth status` shows a ✗ in the **Valid** column.
- **During search** — if the headless browser is redirected to the Elsevier
  SSO page mid-search, MOSAIC prints a clear warning and skips the source:

  ```
  ScienceDirect session has expired.
  Run: mosaic auth login elsevier --url https://www.sciencedirect.com
  ```

To refresh the session:

```bash
mosaic auth login elsevier --url https://www.sciencedirect.com
```

## Legal and ethical notice

This feature is designed for users who have **legitimate access** to the
content they download — through a personal subscription, an institutional
licence, or any other legal right. It automates what you would do manually
in a browser.

MOSAIC does not circumvent paywalls, DRM, or access controls for content
you do not have the right to access. Using this feature to download
content without authorisation may violate the site's terms of service and
applicable law.
