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

### Interactive download (`--interactive`)

The automatic browser step is headless and unattended, so it fails when:

- your saved login has lapsed (see `auth status` above), or
- the publisher refuses headless browsers or shows a CAPTCHA (e.g. IOP), or
- a single sign-on page needs you to log in again.

`mosaic get --interactive` (`-i`) retries the papers that failed in **one visible browser window**, loaded with all your saved sessions:

```bash
mosaic get --from refs.bib --interactive
mosaic get 10.1088/1361-6595/ab46c5 -i
```

For each paper MOSAIC opens the article page and follows the PDF link itself. A visible browser gets through some walls that block headless ones; in testing, an MDPI paper that failed every scripted method downloaded this way without help. If no PDF arrives within about 20 s, the terminal says **Your turn**: log in, solve the check, or click the PDF/Download link in the window. MOSAIC captures the PDF whether the browser downloads it or shows it in its viewer, checks that it really is a PDF, and moves on. Press **Enter** in the terminal to skip a paper. Each paper waits up to 5 minutes.

If at least one paper downloads, the window's cookies, including a login you just completed, are written back to your saved sessions, so later headless runs can use them.

Requires the `[browser]` extra and a display. On WSL2 this works through WSLg, as `mosaic auth login` does.

### Hand-off to your own browser (`--handoff`)

Some publishers block **every** automated browser, visible or not. **ScienceDirect (Elsevier)** answers any browser driven by Playwright with *HTTP 403, "There was a problem providing the content you requested"*, whether or not you are logged in, because such browsers announce themselves (`navigator.webdriver`). No saved session or `--interactive` run can get past that, and MOSAIC does not try to disguise its automation.

`--handoff` uses **your normal browser** instead, with the logins you already have there:

```bash
mosaic get --from refs.bib --handoff
mosaic get 10.1016/j.actaastro.2018.07.007 --handoff
```

For each paper that failed automatically, MOSAIC opens the article in your default browser (on WSL, your **Windows** browser) and watches your Downloads folder. Click the PDF/Download button as you normally would. As soon as the download finishes, MOSAIC checks that it is a PDF, files it in the download directory under the usual name, and opens the next paper:

```
Hand-off of 3 paper(s) to your browser — watching /mnt/c/Users/me/Downloads for each PDF you download (one paper at a time).

[1/3] Low-temperature plasma simulation of a Hall thruster (2018)
  https://www.sciencedirect.com/science/article/pii/S0094576517312663
  Opened in your browser: download the PDF there. Enter here skips.
  ✓ 1-s2.0-S0094576517312663-main.pdf → 2018_Crossref_Acta_Astronautica_….pdf
```

- **One paper at a time.** Only a PDF that appears *after* a paper is opened is filed for it, so files are never mixed up. Press **Enter** to skip a paper; each one waits up to 5 minutes.
- **Downloads folder.** Detected automatically: on WSL, MOSAIC asks Windows for its Downloads folder (even if it has been moved, e.g. into OneDrive); on Linux it uses `xdg-user-dir`. Override it with `--watch-dir PATH`.
- **The file is moved**, not copied, out of Downloads. Unfinished downloads (`.crdownload`, `.part`) and non-PDF files are ignored. If Windows keeps the original locked (e.g. while antivirus scans it), your filed copy is kept and the original is left in Downloads.
- Nothing is automated in your browser: it is an ordinary download that you make yourself.

Combine both modes with `-i --handoff`: the automated window handles what it can, and your own browser gets the rest.

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
| **Scopus (Elsevier)** | ✅ | — | Search works via browser session (shares `id.elsevier.com` SSO with ScienceDirect). Scopus does not expose PDF links; Unpaywall is used as fallback. See [Scopus notes](#scopus) below. |

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
 Name       Domain               Saved             Login                   Path
 elsevier   www.sciencedirect…   2026-03-23 19:41  ? probably logged out   ~/.config/mosaic/sessions/elsevier.json
 springer   link.springer.com    2026-10-14 16:40  ✓ saved < 1 day ago     ~/.config/mosaic/sessions/springer.json
```

- **Domain** — which URLs the session will be tried for during automatic download.
- **Login** — based on when the session was saved, because that is the only reliable signal in the file. Publisher logins (`sd_session_id` on ScienceDirect, `idp_session` on Springer, Shibboleth `_shibsession_*` for institutional SSO) are *session cookies* that the publisher ends within hours or days. The same file also holds analytics and consent cookies that last a year, so their expiry dates say nothing about being logged in. A session older than a day is shown as **probably logged out**. Only opening the publisher's site proves it.

::: tip Refreshing a login
Run `mosaic auth login <name> --url <url>` again, or download with `mosaic get --interactive`. When an interactive download succeeds, the fresh login from that window is saved back to your sessions.
:::

![Auth status demo](/gifs/06_auth_status.gif)

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

## Scopus (Elsevier) {#scopus}

Scopus and ScienceDirect are both Elsevier products that use the **same
`id.elsevier.com` SSO**. A single browser session can be used for both.

| Credentials | What MOSAIC does |
|---|---|
| API key | Uses the Elsevier Scopus Search API (fast, reliable). |
| Browser session (no API key) | Uses headless Firefox to search via the advanced-search form. |
| Neither | Scopus source is skipped entirely. |

### Saving the Scopus session

```bash
mosaic auth login scopus --url https://www.scopus.com
```

Complete the full institutional SSO flow until the Scopus homepage shows
your name, then press **Enter**.

::: tip Share the session with ScienceDirect
Because both sites use `id.elsevier.com` for authentication, a Scopus login
will also enable the ScienceDirect browser source (and vice versa). You only
need to save one session — MOSAIC matches saved sessions by domain, and the
Elsevier SSO cookies are valid across `scopus.com` and `sciencedirect.com`.
:::

::: warning Same browser for login and search
Use Firefox for both headed login and headless search (same as ScienceDirect).
Install it before logging in: `playwright install firefox`.
:::

### Notes on search and selectors

Scopus uses a heavily JavaScript-rendered interface. The browser source
submits queries via the advanced-search form using full Scopus boolean
syntax (e.g. `TITLE-ABS-KEY("transformer") AND PUBYEAR > 2019`). Because
the Scopus frontend can change independently of MOSAIC releases, the CSS
selectors used to extract result rows may occasionally need updating.

If search returns empty results after a known-working login, open an issue at
[github.com/szaghi/mosaic](https://github.com/szaghi/mosaic).

## Legal and ethical notice

This feature is designed for users who have **legitimate access** to the
content they download — through a personal subscription, an institutional
licence, or any other legal right. It automates what you would do manually
in a browser.

MOSAIC does not circumvent paywalls, DRM, or access controls for content
you do not have the right to access. Using this feature to download
content without authorisation may violate the site's terms of service and
applicable law.
