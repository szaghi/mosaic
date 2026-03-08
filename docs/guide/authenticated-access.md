---
title: Authenticated Access
---

# Authenticated Access

Some publishers and institutional repositories do not offer a public API but
do grant access to logged-in users — for example via a university single
sign-on, a personal Elsevier or Springer account, or a library proxy.

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
3. When done, switch back to the terminal and press **Enter**.
4. MOSAIC saves the browser session (cookies and local storage) to
   `~/.config/mosaic/sessions/<name>.json` and records the login domain
   alongside it.

### Automatic download fallback

When you run `mosaic search --download` or `mosaic get`, the downloader
tries three strategies in order:

1. **Known PDF URL** — used directly if the search source returned one.
2. **Unpaywall** — resolves a legal open-access copy by DOI.
3. **Browser session** — if steps 1 and 2 fail, MOSAIC checks whether
   any saved session's domain matches the paper's URL. If so, it opens a
   headless browser with that session's cookies, navigates to the paper
   page, and downloads the PDF automatically.

No extra flags are needed — the browser step runs silently whenever a
matching session is found and the other methods come up empty.

### Domain matching

Each session is associated with the domain of the `--url` you passed at
login time (e.g. `sciencedirect.com` for an Elsevier login). When
downloading, MOSAIC compares that domain against the paper's URL domain.
A match is found if either domain is a substring of the other, so both
`sciencedirect.com` and `www.sciencedirect.com` will match an Elsevier
session.

## Session storage

Sessions are stored as standard Playwright `storageState` files:

```
~/.config/mosaic/sessions/
  elsevier.json
  springer.json
  myuni.json
```

Each file contains only browser cookies and local storage — **no passwords
are ever stored**.

Sessions expire when the website's cookies expire (typically days to weeks
depending on the site). Re-run `mosaic auth login` to refresh.

## Commands

### `mosaic auth login`

```
mosaic auth login [OPTIONS] NAME
```

| Argument / Option | Description |
|---|---|
| `NAME` | Arbitrary label for the session (e.g. `elsevier`, `myuni`) |
| `--url` / `-u` | URL to open in the browser (required) |

MOSAIC tries browsers in order: **Chromium → Firefox → WebKit**. The first
one that is installed is used automatically.

**Examples:**

```bash
# Log in to ScienceDirect (Elsevier)
mosaic auth login elsevier --url https://www.sciencedirect.com/user/login

# Log in via your university SSO
mosaic auth login myuni --url https://library.myuni.edu/login

# Log in to Springer
mosaic auth login springer --url https://link.springer.com/login

# Log in to Wiley
mosaic auth login wiley --url https://onlinelibrary.wiley.com/action/showLogin
```

### `mosaic auth status`

List all saved sessions:

```bash
mosaic auth status
```

```
 Name       Domain               Saved             Path
 elsevier   sciencedirect.com    2026-03-08 14:32  ~/.config/mosaic/sessions/elsevier.json
 myuni      library.myuni.edu    2026-03-07 09:15  ~/.config/mosaic/sessions/myuni.json
```

The **Domain** column shows which URLs the session will be used for during automatic download.

### `mosaic auth logout`

Remove a saved session:

```bash
mosaic auth logout elsevier
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
