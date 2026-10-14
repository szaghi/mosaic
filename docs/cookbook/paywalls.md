---
title: Paywalled papers
---

# Paywalled papers

Recipes for papers you can read through a subscription or an account but that have no open copy.

[[toc]]

## An Elsevier paper

```bash
mosaic get 10.1016/j.paerosci.2006.01.001 --handoff
```

mosaic opens the article page in your default browser and watches your Downloads folder. Click "Download PDF" as
usual; mosaic checks the new file is a PDF, moves it into the library under the paper's name and stops. Elsevier
refuses every automated browser, so this is the way for ScienceDirect.
Tutorial: [your browser does the download](/tutorial/05-paywalls#your-browser-does-the-download). Guide:
[hand-off](/guide/authenticated-access#hand-off-to-your-own-browser-handoff).

## Every failed paper of a reference list

```bash
mosaic get --from refs.bib --handoff
mosaic get --from refs.bib -i --handoff     # an automated window first, your browser for the rest
```

The open papers download as usual; the ones that fail open in your browser one at a time. Enter in the terminal
means "done with this paper", or skips it. Each paper waits up to 5 minutes.

## mosaic cannot find your Downloads folder

```bash
mosaic get 10.1016/j.paerosci.2006.01.001 --handoff --watch-dir /mnt/c/Users/me/Downloads
```

On WSL mosaic asks Windows where the Downloads folder is, also when it was moved into OneDrive; on Linux it asks
`xdg-user-dir DOWNLOAD`, then tries `~/Downloads`. `--watch-dir` names the folder when neither works, or when your
browser saves elsewhere.

## PDFs you already downloaded

```bash
mosaic import ~/Downloads/1-s2.0-S0094576517312663-main.pdf
mosaic import ~/Downloads/*.pdf --download-dir ~/papers/hall-thrusters
```

`import` finds each file's DOI (the PDF's metadata, then the article ID in a ScienceDirect file name, then a single
DOI in the text), takes title, authors and year from the cache or Crossref, and moves the file into the library
under the usual name. Files that are not PDFs, or whose DOI it cannot find, are reported and left in place; the
command exits with status 1 if any file failed.
Tutorial: [PDFs you already have](/tutorial/05-paywalls#pdfs-you-already-have). Guide:
[PDFs you downloaded yourself](/guide/downloads#pdfs-you-downloaded-yourself).

## A PDF without DOI metadata

```bash
mosaic import scan.pdf --doi 10.1016/j.paerosci.2006.01.001
```

`--doi` names the paper when detection fails, and works with one file at a time.

## Replace a file already in the library

```bash
mosaic import ~/Downloads/better-copy.pdf --doi 10.1016/j.paerosci.2006.01.001 --force
```

Without `--force`, `import` refuses to overwrite a PDF already filed under the same name.

## Log in to a publisher once

```bash
mosaic auth login springer --url https://link.springer.com
```

A browser window opens at the URL. Log in as the site asks (institution, SSO, two-factor), wait until the
publisher's page shows you logged in, then press Enter in the terminal: mosaic saves the cookies to
`~/.config/mosaic/sessions/springer.json`. Later downloads use the session without any flag. Pressing Enter in
the middle of SSO redirects saves a session that does not work.
Needs the `browser` extra and a Playwright browser ([Installation](/guide/installation)). Guide:
[saved sessions](/guide/authenticated-access#saved-sessions).

## Check your saved sessions

```bash
mosaic auth status
```

The Login column tells how long ago a session was saved: publisher logins live in cookies that end within hours or
days, so a session saved more than a day ago is probably logged out. Log in again, or let a successful
`get --interactive` refresh it.

## A CAPTCHA or an SSO prompt

```bash
mosaic get 10.1088/1361-6595/ab46c5 --interactive
```

`--interactive` (`-i`) retries the failed papers in a visible browser window loaded with your sessions. When the
PDF does not arrive by itself, the terminal says it is your turn: log in, solve the check or open the PDF in the
window. It needs a display; on WSL2, WSLg provides one.
Guide: [interactive download](/guide/authenticated-access#interactive-download-interactive).

## Forget a session

```bash
mosaic auth logout springer
```

Deletes the saved session files for that name.
