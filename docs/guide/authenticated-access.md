---
title: Authenticated Access
---

# Authenticated Access

Papers you can read through a subscription, your institution or a personal account, but that have no open copy.
mosaic has four ways to get them, from most to least automated: the auto pass with your Chrome, a saved browser
session, an interactive browser window, and a hand-off to your own browser.

| Method | You do | Works when |
|---|---|---|
| Auto pass (`mosaic get --auto`) | log in once per browser session | your machine has a Chrome/Edge mosaic can drive (Windows Chrome from WSL included); follows you through fingerprint-guarded publishers like Elsevier |
| Saved session (`mosaic auth login`) | log in once | the publisher accepts a headless browser with your cookies |
| `mosaic get --interactive` | log in or solve a check in a window mosaic drives | the publisher accepts a visible automated browser |
| `mosaic get --handoff` | click Download in your own browser | always, including Elsevier without Chrome |

All of them need a legitimate right to the content. mosaic automates what you would do by hand in a browser; it
does not get around paywalls, access controls or bot detection.

::: info Prerequisite
Saved sessions and `--interactive` need the `browser` extra and a Playwright browser (Firefox is tried first,
then Chromium, then WebKit); see [Installation](./installation). `--auto` needs the `browser` extra too, plus an
installed Chrome or Edge. `--handoff` needs neither.
:::

## Auto pass with your Chrome (`--auto`) {#auto-pass-with-your-chrome-auto}

```bash
mosaic get 10.1016/j.paerosci.2006.01.001 --auto
mosaic get --from refs.bib --auto
```

Some publishers put their PDFs behind fingerprint checks that every Playwright-installed browser fails,
logged in or not, while a genuine Chrome passes. The auto pass therefore drives *your* Chrome, the same binary
you use every day, through exactly the moves you would make: it opens the article page, opens the paper's
"Download PDF" link, lets Chrome save the file as a normal download, and files it into the library under the
usual name. It runs Chrome with a separate mosaic profile and never opens your daily one. On WSL it drives the
Windows Chrome or Edge, with the profile in `mosaic-cdp-profile` under your Windows user folder; the PDFs land
first in `mosaic-auto-downloads` next to it.

The first `--auto` run on a fresh mosaic profile opens a Chrome window and asks for the institutional sign-in;
complete it once, and the pass runs unattended. Publishers' session cookies die with the browser, so one login
per browser session is all the interaction you should expect; after that, papers come one at a time, 8 to 15
seconds apart on the same site, with 3 more seconds between sites.

- **Opt-in by design**: without `--auto` nothing is driven, and the pass never runs as a fallback on its own.
- **Guardrails**: at most 50 papers per run (`--max-auto N` changes it). After 3 papers in a row on one
  publisher site end with no PDF, mosaic skips that site's remaining papers, reported as "stopped after
  repeated walls", and goes on with the other sites. A login page does not count toward the 3. Re-run later:
  the failed papers stay marked in the cache.
- **Rescue chain**: `--auto --interactive --handoff` together run them in this order; each takes what it can
  and passes the rest on.
- **Account risk**: automating browser actions can conflict with a publisher's terms even when the papers are
  yours to read. The pass paces itself to look like a person reading; how you weigh the terms is yours to
  decide.

Works best where the bot checks are the *only* obstacle, Elsevier above all: the probe behind this pass saved
all 5 sampled subscribed PDFs unattended on the first try. A paper whose PDF link needs a CAPTCHA (IOP) still
ends in the interactive window; combine the flags for that.

### Why mosaic drives your Chrome on Elsevier {#linkinghub-auto}

ScienceDirect refuses two kinds of client. A plain HTTP request for its PDF URLs gets HTTP 403 even when it
carries your session cookies. A browser that Playwright launches announces itself through `navigator.webdriver`
and gets the same 403 page as the [hand-off](#hand-off-to-your-own-browser-handoff) section describes. A
Chrome you could have started yourself, without the automation switches, passes. So mosaic starts your installed
Chrome or Edge as a normal browser, with only a remote-debugging port added. It then attaches to it over the
Chrome DevTools Protocol (CDP) and makes the moves a reader makes.

For each paper the pass:

1. **Starts at `https://doi.org/<DOI>`.** Journal DOIs resolve to Elsevier's `linkinghub.elsevier.com`, which
   moves on to ScienceDirect through a delayed redirect in the page. A real navigation follows that redirect,
   and mosaic waits up to 30 seconds for the ScienceDirect article page. An article URL opened directly can
   land on a challenge page that never clears, so the pass always starts at doi.org.
2. **Reads the PDF link from the article page.** mosaic polls the page for up to 30 seconds for the
   `citation_pdf_url` meta tag or a `/pdfft` link that carries the article's PII. If the page sends you to
   `id.elsevier.com` or a login page instead, the paper counts as "login needed".
3. **Opens the link in a second tab.** The article tab stays open: closing the page that started a download
   cancels it. The link leads to an interstitial page whose own script sends the browser to a signed copy of
   the file on `pdf.sciencedirectassets.com`. If no file arrives within 8 seconds, mosaic runs the page's own
   `redirectUser()`, or goes to the signed address it finds in the page, and then waits up to 75 seconds more.
4. **Lets Chrome save the file as a normal download.** The mosaic profile is set to download PDFs instead of
   showing them in the viewer, without asking where to save, and with automatic downloads allowed for the two
   ScienceDirect hosts. Chrome blocks repeated downloads from one site otherwise. At the start of each run,
   mosaic also tells the running browser over CDP to save downloads into `mosaic-auto-downloads`. Without that
   instruction, downloads started from pages that mosaic opened over CDP are lost.
5. **Files the PDF.** A new file counts as the paper's only when its name holds the paper's PII
   (`1-s2.0-<PII>-main.pdf`) or its DOI suffix. mosaic checks for the `%PDF-` signature, moves the file into the
   library under the usual name and records it in the cache.

The login lives in the mosaic profile, not in your daily one, so you sign in to ScienceDirect there once.
ScienceDirect's login cookies (`sd_session_id`) are session cookies and end when that Chrome exits. mosaic only
disconnects from the browser at the end of a run, so Chrome stays open. A later `--auto` run attaches to the
same window and reuses the login. Close the window and the next run asks you to sign in again.

When a page asks for a login, mosaic opens that site's article in a window and prints `Login needed`. It then
waits up to 3 minutes for a login cookie, retries the paper once, and does not ask again for that site in the
same run. Press Enter in the terminal to stop waiting.

::: warning Automated access and publisher terms ⚠
Automated access may conflict with a publisher's terms. mosaic does not disguise itself here; it drives a real
browser at a reader's pace. Use your own judgment about your institution's account.
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
that, and mosaic does not disguise its automation. For ScienceDirect the pass that works unattended is
[`--auto`](#auto-pass-with-your-chrome-auto), your own Chrome; `--handoff` is the fallback that needs no Chrome
at all: it uses your normal browser, with the logins you already have there:

```bash
mosaic get 10.1016/j.paerosci.2006.01.001 --handoff
mosaic get --from refs.bib --handoff
```

<<< @/examples/output/05/handoff.txt{console}

For each paper that failed, mosaic opens the article page in your default browser (on WSL, your Windows
browser) and watches your Downloads folder. Click the PDF or Download button as you would anyway. When the file
is complete, mosaic checks it is a PDF, files it under the usual name and opens the next paper.

- **One paper at a time**, by default. Only a PDF that appears after a paper was opened is filed for it, so files
  never get mixed up. Each paper waits up to 5 minutes; once its PDF has arrived you need not press anything.
- **Several at a time with `--batch N`.** mosaic opens N papers in tabs, one second apart, and you download them
  in any order. Each new PDF is filed for the paper of the batch it matches, tried in this order:
  1. an identifier in the file name: the PII of ScienceDirect's `1-s2.0-<PII>-main.pdf`, or the DOI suffix
     (Springer's `s10915-021-01234-5.pdf`);
  2. the paper's DOI inside the PDF: in its metadata, or on its first two pages when pymupdf is installed. A PDF
     that mentions the DOIs of two papers of the batch (one cites the other) matches neither this way;
  3. elimination: when one paper of the batch is left, the next PDF is its own, as in one-at-a-time mode.

  A PDF that still matches nothing stays in Downloads, and mosaic names it at the end of the batch. The batch
  ends when every PDF has arrived, when you press Enter, or after 5 minutes without a new PDF.

  ```bash
  mosaic get --from refs.bib --handoff --batch 10
  ```
- **Enter means "done with this paper"** (or batch). After Enter, mosaic keeps watching for 8 seconds, and up to 2 minutes
  while a partial download (`.crdownload`, `.part`) shows the browser is still writing, so Enter pressed right
  after clicking Download does not lose the file. Enter without downloading skips the paper.
- **A PDF that arrives too late** can be filed afterwards with [`mosaic import`](./downloads#pdfs-you-downloaded-yourself).
- **The Downloads folder** is detected: on WSL, mosaic asks Windows for its Downloads known folder (also when it
  was moved, into OneDrive for example) and maps it with `wslpath`; on Linux it asks `xdg-user-dir DOWNLOAD`,
  then falls back to `~/Downloads`. `--watch-dir PATH` overrides it.
- **The file is moved** out of Downloads: copied to the library, then deleted. Partial downloads and non-PDF
  files are ignored. If Windows keeps the original locked, the library copy stays and the original is left in
  Downloads.
- Nothing is automated in your browser: the download is an ordinary one that you make. Opening the publisher's
  PDF link directly does not save the click: ScienceDirect answers it with "There was a problem providing the
  content you requested" even in a logged-in browser.
- **On WSL** the page opens through PowerShell's `Start-Process` (after `wslview`, if installed):
  `explorer.exe` shows File Explorer instead of the browser for a URL with a query string.

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
| IOP Publishing | nothing headless: use `--auto` and pass the check yourself, or `--interactive` |
| ScienceDirect, Scopus (Elsevier) | search only; PDFs through `--auto` or `--handoff` |

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

PDFs never come from the headless session: ScienceDirect refuses automated browsers there. Open-access copies
come through Unpaywall; for subscribed papers use `--auto` (your own Chrome, one login per session) or
`--handoff`.

### Scopus (Elsevier) {#scopus}

Scopus and ScienceDirect share the `id.elsevier.com` login. With a Scopus API key
(`mosaic config --scopus-key`, plus `--scopus-inst-token` off campus) mosaic uses the Scopus Search API;
without one, a session saved with `mosaic auth login scopus --url https://www.scopus.com` drives the
advanced-search form in a headless browser. Scopus has no PDFs: downloads go through Unpaywall or `--handoff`.
The Scopus web page changes independently of mosaic; if a working login returns no results, open an issue at
[github.com/szaghi/mosaic](https://github.com/szaghi/mosaic).

See also: [tutorial: paywalled papers](/tutorial/05-paywalls), [recipes](/cookbook/paywalls),
[`mosaic auth`](/reference/auth), [`mosaic get`](/reference/get), [Downloads](./downloads).
