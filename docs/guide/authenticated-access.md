---
title: Authenticated Access
---

# Authenticated Access

Papers you can read through a subscription, your institution or a personal account, but that have no open copy.
mosaic has three ways to get them, from most to least automated: a saved browser session, an interactive browser
window, and a hand-off to your own browser.

| Method | You do | Works when |
|---|---|---|
| Saved session (`mosaic auth login`) | log in once | the publisher accepts a headless browser with your cookies |
| `mosaic get --interactive` | log in or solve a check in a window mosaic drives | the publisher accepts a visible automated browser |
| `mosaic get --handoff` | click Download in your own browser | always, including Elsevier |

All three need a legitimate right to the content. mosaic automates what you would do by hand in a browser; it
does not get around paywalls, access controls or bot detection.

::: info Prerequisite
Saved sessions and `--interactive` need the `browser` extra and a Playwright browser (Firefox is tried first,
then Chromium, then WebKit); see [Installation](./installation). `--handoff` needs neither.
:::

## Saved sessions

```bash
mosaic auth login springer --url https://link.springer.com
mosaic auth status
mosaic auth logout springer
```

`mosaic auth login NAME --url URL` opens a visible browser at `URL`. Log in as the site requires (SSO,
password, two-factor), wait until the publisher's page shows you as logged in, then press Enter in the terminal.
mosaic writes the browser's cookies and local storage to `~/.config/mosaic/sessions/NAME.json` (readable by you
only) and the domain of `URL` to `NAME.meta.json`. No password is stored.

::: warning Finish logging in before pressing Enter
Pressed during the SSO redirects, Enter saves a half-authenticated session, and later downloads fail.
:::

From then on, the [downloader](./downloads#how-it-works) uses the sessions as its last step, after the source's
PDF link and Unpaywall. It resolves the paper's DOI to the article page, picks the session whose domain matches,
or tries every saved session when none does, opens the page in a headless browser with your cookies, finds the
PDF link and fetches it. No flag is needed.

### `auth status` and the Login column

```
 Name       Domain               Saved             Login                   Path
 elsevier   www.sciencedirect…   2026-03-23 19:41  ? probably logged out   ~/.config/mosaic/sessions/elsevier.json
 springer   link.springer.com    2026-10-14 16:40  ✓ saved < 1 day ago     ~/.config/mosaic/sessions/springer.json
```

The Login column is based on when the session was saved, the one signal the file gives: `✓ saved < 1 day ago`,
or `? probably logged out` once it is older than a day. Publisher logins (`sd_session_id` on ScienceDirect,
`idp_session` on Springer, Shibboleth `_shibsession_*` cookies) are session cookies that the publisher ends
within hours or days, while the same file holds analytics cookies valid for a year, so cookie expiry dates say
nothing about being logged in. Only opening the publisher's site proves it.

Refresh a login with `mosaic auth login` again, or with a successful `mosaic get --interactive`, which writes
the window's cookies back to your sessions.

## Interactive download (`--interactive`) {#interactive-download-interactive}

The saved-session step runs headless and unattended. It fails when the login has lapsed, when the publisher
refuses headless browsers or shows a CAPTCHA (IOP does), or when SSO wants you to log in again.
`--interactive` (`-i`) retries the papers that failed in one visible window, loaded with all your saved
sessions:

```bash
mosaic get 10.1088/1361-6595/ab46c5 --interactive
mosaic get --from refs.bib -i
```

For each paper mosaic opens the article page and follows the PDF link itself. If no PDF arrives within 20
seconds, the terminal says `Your turn`: log in, solve the check, or open the PDF in the window. mosaic captures
the PDF whether the browser downloads it or shows it in its viewer, checks the `%PDF-` signature and moves to
the next paper. Each paper waits up to 5 minutes; Enter in the terminal skips it.

When at least one PDF arrives, the window's cookies, including a login you completed there, are written back to
every saved session. Without a download nothing is written back, so a dead session never looks freshly saved.

`--interactive` needs a display. On WSL2 it works through WSLg, as `mosaic auth login` does.

## Hand-off to your own browser (`--handoff`) {#hand-off-to-your-own-browser-handoff}

Some publishers block every automated browser, visible or not. ScienceDirect (Elsevier) answers any browser
driven by Playwright with HTTP 403, "There was a problem providing the content you requested", logged in or not:
such browsers announce themselves through `navigator.webdriver`. No session or `--interactive` run gets past
that, and mosaic does not disguise its automation.

`--handoff` uses your normal browser, with the logins you already have there:

```bash
mosaic get 10.1016/j.paerosci.2006.01.001 --handoff
mosaic get --from refs.bib --handoff
```

<<< @/examples/output/05/handoff.txt{console}

For each paper that failed, mosaic opens the article page in your default browser (on WSL, your Windows
browser) and watches your Downloads folder. Click the PDF or Download button as you would anyway. When the file
is complete, mosaic checks it is a PDF, files it under the usual name and opens the next paper.

- **One paper at a time.** Only a PDF that appears after a paper was opened is filed for it, so files never get
  mixed up. Each paper waits up to 5 minutes; once its PDF has arrived you need not press anything.
- **Enter means "done with this paper".** After Enter, mosaic keeps watching for 8 seconds, and up to 2 minutes
  while a partial download (`.crdownload`, `.part`) shows the browser is still writing, so Enter pressed right
  after clicking Download does not lose the file. Enter without downloading skips the paper.
- **A PDF that arrives too late** can be filed afterwards with [`mosaic import`](./downloads#pdfs-you-downloaded-yourself).
- **The Downloads folder** is detected: on WSL, mosaic asks Windows for its Downloads known folder (also when it
  was moved, into OneDrive for example) and maps it with `wslpath`; on Linux it asks `xdg-user-dir DOWNLOAD`,
  then falls back to `~/Downloads`. `--watch-dir PATH` overrides it.
- **The file is moved** out of Downloads: copied to the library, then deleted. Partial downloads and non-PDF
  files are ignored. If Windows keeps the original locked, the library copy stays and the original is left in
  Downloads.
- Nothing is automated in your browser: the download is an ordinary one that you make.

Combine the two retries with `-i --handoff`: the automated window takes what it can, your browser the rest.

### DOIs that land on linkinghub

Elsevier DOIs resolve over HTTP only as far as `linkinghub.elsevier.com`, whose page reaches ScienceDirect
through a delayed redirect. mosaic maps `linkinghub.elsevier.com/retrieve/pii/<PII>` straight to
`www.sciencedirect.com/science/article/pii/<PII>`, so the hand-off and interactive windows open the article
itself, and session domain matching sees `www.sciencedirect.com`.

## Publisher notes

| Publisher | What a saved session gives |
|---|---|
| Springer Nature | PDF download of subscribed content |
| Wiley, Taylor & Francis, Cambridge | PDF download (standard cookie sessions) |
| IOP Publishing | nothing headless: use `--interactive` and pass the check yourself |
| ScienceDirect, Scopus (Elsevier) | search only (see below); PDFs through `--handoff` |

`--handoff` works with every publisher, since the download happens in your own browser.

Springer search needs no session: the `sp` source runs a headless browser on the public search pages. Log in
from the home page (`https://link.springer.com`, then Log in via institution) to download subscribed PDFs.

### ScienceDirect (Elsevier) {#sciencedirect-elsevier}

| Credentials | What mosaic does |
|---|---|
| API key (`mosaic config --elsevier-key`) | searches with the Elsevier Article Search API |
| Browser session, no API key | searches `sciencedirect.com` in a headless browser |
| Neither | skips the source |

The API key wins when both are present. Save the session with
`mosaic auth login elsevier --url https://www.sciencedirect.com` and complete the institutional SSO before
pressing Enter. A session counts for search while at least one of its timed cookies has not expired; when a
search lands on the Elsevier login page instead, mosaic prints `ScienceDirect session has expired.` and skips the
source.

PDFs never come from the session: ScienceDirect refuses automated browsers. Open-access copies come through
Unpaywall; for subscribed papers use `--handoff`.

### Scopus (Elsevier) {#scopus}

Scopus and ScienceDirect share the `id.elsevier.com` login. With a Scopus API key
(`mosaic config --scopus-key`, plus `--scopus-inst-token` off campus) mosaic uses the Scopus Search API;
without one, a session saved with `mosaic auth login scopus --url https://www.scopus.com` drives the
advanced-search form in a headless browser. Scopus has no PDFs: downloads go through Unpaywall or `--handoff`.
The Scopus web page changes independently of mosaic; if a working login returns no results, open an issue at
[github.com/szaghi/mosaic](https://github.com/szaghi/mosaic).

See also: [tutorial: paywalled papers](/tutorial/05-paywalls), [recipes](/cookbook/paywalls),
[`mosaic auth`](/reference/auth), [`mosaic get`](/reference/get), [Downloads](./downloads).
