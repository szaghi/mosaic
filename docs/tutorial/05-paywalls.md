---
pageClass: tutorial-page
aside: false
title: 5. Paywalled papers
---

# 5. Paywalled papers

The 2005 review of electric propulsion modelling by Boyd is an Elsevier paper with no open copy:

<<< @/examples/output/05/get.txt{console}

If your institution subscribes, you can read it in your browser. mosaic has three ways to turn that access into a
file in the library; the one that always works is the simplest.

## Your browser does the download

<<< @/examples/output/05/handoff.txt{console}

`--handoff` opens the article page in your default browser (on WSL, the Windows one), where your institutional
login already lives, and watches your Downloads folder. You click "Download PDF" as usual; when the file is
complete, mosaic checks that it is a PDF, moves it into the library under the paper's name and opens the next
paper. Enter in the terminal means "done with this paper", or skips it.

mosaic finds the Downloads folder by itself, also the Windows one from WSL; `--watch-dir PATH` names another.
With `--from refs.bib --handoff`, only the papers that fail the normal way are handed to you, one at a time.

## PDFs you already have

Downloaded a paper before you had mosaic, or a hand-off ended before the file arrived? `mosaic import` files it:

<<< @/examples/output/05/import.txt{console}

mosaic finds the DOI in the file's metadata, or reads the article ID that ScienceDirect puts in its file names
(`1-s2.0-<PII>-main.pdf`) and asks Crossref, or takes the only DOI printed in the text. When none of these works,
pass `--doi`. The file is moved into the library and recorded as a download:

<<< @/examples/output/05/ls.txt{console}

## Letting mosaic drive a browser

For publishers that accept automated browsers, two more ways need the `browser` extra and a Playwright browser
([Installation](/guide/installation)):

```bash
mosaic auth login springer --url https://link.springer.com   # log in once, cookies saved
mosaic get 10.1007/s41614-019-0033-1                          # later downloads use the session
mosaic get 10.1088/1361-6595/ab46c5 --interactive             # a visible window: you solve the check
```

<<< @/examples/output/05/auth.txt{console}

Sessions expire with the publisher's login cookies, within hours or days; `mosaic auth status` shows how old each
one is. Elsevier refuses every automated browser, logged in or not, so for ScienceDirect use `--handoff`.
[Authenticated access](/guide/authenticated-access) compares the three methods publisher by publisher.

::: tip What you learned
`get --handoff` files what you download in your own browser; `mosaic import` files PDFs you already have;
`auth login` and `--interactive` let mosaic drive a browser where publishers allow it.
Reference: [`get`](/reference/get), [`import`](/reference/import), [`auth`](/reference/auth).
:::

Next: [6. Exporting](./06-exporting).
