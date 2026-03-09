---
title: Configuration
---

# Configuration

MOSAIC stores its configuration in `~/.config/mosaic/config.toml`. The file is created automatically with defaults on first run.

Browser sessions (saved via `mosaic auth login`) are stored separately at `~/.config/mosaic/sessions/` and are not part of the main config file.

## Quick setup

```bash
# Set your Unpaywall email (enables PDF fallback for any DOI)
mosaic config --unpaywall-email you@example.com

# Set an Elsevier API key (enables ScienceDirect API search)
mosaic config --elsevier-key YOUR_KEY

# Set a Semantic Scholar API key (optional — higher rate limit)
mosaic config --ss-key YOUR_KEY

# Change where PDFs are saved
mosaic config --download-dir ~/papers

# Change the PDF filename pattern
mosaic config --filename-pattern "{author}_{year}_{title}"

# Print current config
mosaic config --show
```

## Full config reference

```toml
# Where downloaded PDFs are saved
download_dir = "/home/you/mosaic-papers"

# Path to the local SQLite cache
db_path = "/home/you/.local/share/mosaic/cache.db"

# Minimum seconds between requests to the same source
rate_limit_delay = 1.0

# PDF filename pattern — available placeholders:
#   {year}    publication year (0000 if unknown)
#   {source}  source name (arXiv, DOAJ, …)
#   {author}  first author last name
#   {title}   title slug, truncated to 60 chars
#   {doi}     DOI with special chars replaced by _
#   {journal} journal name slug (no_journal if unknown)
filename_pattern = "{year}_{source}_{author}_{title}"

[unpaywall]
# Required for PDF fallback. Any valid email — Unpaywall uses it
# for usage tracking only, not authentication.
email = "you@example.com"

[sources.arxiv]
enabled = true

[sources.semantic_scholar]
enabled = true
# Optional. Without a key you share 1000 req/s with all unauthenticated users.
# With a key you get a dedicated 1 req/s slot.
api_key = ""

[sources.sciencedirect]
enabled = true
# Optional. Register free at https://dev.elsevier.com
# If omitted, MOSAIC falls back to a saved browser session for search
# (see Authenticated Access). Without an institutional token the API
# returns only open-access content.
api_key = ""

[sources.springer]
enabled = true
# No credentials required. Requires the [browser] optional extra.
# Disable here if you want to exclude Springer from multi-source searches.

[sources.doaj]
enabled = true

[sources.europepmc]
enabled = true

[sources.openalex]
enabled = true

[sources.base]
enabled = true

[sources.core]
enabled = true
# Required. Register free at https://core.ac.uk/services/api
api_key = ""

[sources.nasa_ads]
enabled = true
# Required. Register free at https://ui.adsabs.harvard.edu/user/settings/token
api_key = ""

[sources.zenodo]
enabled = true
# Optional. Create a personal access token at https://zenodo.org/account/settings/applications/
# Anonymous access works without a token (60 req/min limit).
api_key = ""

[sources.crossref]
enabled = true
# No credentials required. Reuses the unpaywall.email for the polite pool (50 req/s).
```

## Source credentials

### ScienceDirect (Elsevier)

MOSAIC supports two access modes for ScienceDirect. The active mode is chosen
automatically based on what credentials you have configured:

| Credentials | Search | PDF download |
|---|---|---|
| **Elsevier API key** (recommended) | ✅ Full API search | ✅ via Unpaywall / direct URL |
| **Browser session** (institutional login) | ✅ Browser-based search | ⚠️ Blocked by Cloudflare on PDF endpoint |
| **Neither** | — source skipped — | — |

::: tip Which mode is right for me?
- Use the **API key** if you primarily want reliable, scriptable access to metadata and open-access PDFs.
- Use the **browser session** if you have institutional credentials but no API key — you still get full search results for subscribed content. PDF download via the session is limited (see note below).
- Both can coexist: if an API key is set it always takes priority; the browser session is the fallback.
:::

#### API key setup

**Step 1 — create an Elsevier developer account:**

1. Go to [dev.elsevier.com](https://dev.elsevier.com) and click **I want an API key**
2. Sign in with an existing Elsevier / Scopus account, or click **Register** to create one (free)
3. Fill in your name, email, and organisation; accept the API terms of service

**Step 2 — create an API key:**

1. Once logged in, click your name → **Manage API Keys** (or go to [dev.elsevier.com/apikey/manage](https://dev.elsevier.com/apikey/manage))
2. Click **Create API Key**, enter a label (e.g. `MOSAIC`), click **Submit**
3. Copy the 32-character hex key

**Step 3 — add the key to MOSAIC:**

::: warning Wait before using the key
Newly created Elsevier API keys can take up to **15 minutes** to activate. If you get a `401 Unauthorized` error immediately after creation, wait a few minutes and try again.
:::

```bash
mosaic config --elsevier-key YOUR_KEY
```

::: tip Institutional access via API
Without an institutional token, the API returns only open-access articles. For subscribed content, your institution's library must request an **Institution Token** from Elsevier. Running MOSAIC from campus or via your institution's VPN activates IP-based authentication automatically — no extra config needed.
:::

#### Browser session setup

If you have institutional credentials but no API key, save a browser session
instead. See [Authenticated Access](./authenticated-access) for the general
workflow. The ScienceDirect-specific steps are:

```bash
mosaic auth login elsevier --url https://www.sciencedirect.com
```

In the browser window, complete the full institutional SSO flow until
ScienceDirect shows your name or a "Sign out" link, then press **Enter** in
the terminal.

::: warning Use Firefox for ScienceDirect
MOSAIC uses Firefox for both login and headless search by default. The
Cloudflare session cookie (`cf_clearance`) is bound to the browser's TLS
fingerprint — mixing browsers (e.g. logging in with Chromium then searching
with Firefox) causes the session to be rejected. If Firefox is not installed,
run `playwright install firefox`.
:::

::: info PDF download limitation
ScienceDirect's PDF download endpoint (`/pdfft/`) applies stricter Cloudflare
Bot Management rules than article pages. Even with a valid institutional
session the download is blocked by Cloudflare regardless of credentials. The
browser session therefore enables **search only**; PDF retrieval falls back to
Unpaywall (open-access copies). For reliable PDF access to subscribed content,
use the API key with an institutional IP or VPN.
:::

::: tip Session expiry
MOSAIC checks cookie timestamps before activating the browser session. An
expired session is silently excluded at startup (visible as ✗ in
`mosaic auth status`). If the session expires mid-search, MOSAIC prints a
warning and suggests the re-login command. Re-run
`mosaic auth login elsevier --url https://www.sciencedirect.com` to refresh.
:::

### CORE — free API key required

CORE is **disabled** until an API key is set. Registration is free for academic use.

1. Register at [core.ac.uk/services/api](https://core.ac.uk/services/api)
2. Copy the key from your dashboard
3. Add it to the config file directly (no CLI shorthand yet):

```toml
# ~/.config/mosaic/config.toml
[sources.core]
api_key = "YOUR_KEY"
```

### Semantic Scholar — optional API key

Without a key, requests share the public rate-limit pool (1 000 req/s across all anonymous users). With a dedicated key you get a private slot at 1 req/s — enough for interactive use.

1. Go to [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api) and scroll down to **"Get API Key"**
2. Fill in your name, email, and a brief description of your use case
3. The key is issued automatically and sent to your email — usually within a few minutes; no institutional affiliation is required
4. Apply it:

```bash
mosaic config --ss-key YOUR_KEY
```

### Unpaywall — email address required

Unpaywall is not a search source but the PDF fallback resolver used during download. It requires any valid email address for usage tracking — no account or password.

```bash
mosaic config --unpaywall-email you@example.com
```

### OpenAlex — optional email (polite pool)

OpenAlex works without any credentials. Providing your email opts you into the [polite pool](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication), which grants significantly higher rate limits. MOSAIC reuses the Unpaywall email automatically — no separate step needed once `--unpaywall-email` is set.

### Springer Nature — no credentials required

Springer Nature search is publicly accessible. The source activates
automatically when Playwright is installed (`pip install 'mosaic-search[browser]'`).
No API key or browser session is needed for searching. A saved session is
used only for PDF downloads of subscribed articles — see
[Authenticated Access](./authenticated-access).

To disable the source entirely:
```toml
[sources.springer]
enabled = false
```

### Zenodo — optional access token

Zenodo works without any credentials (60 req/min anonymous limit). A free personal access token raises this limit. Create one at [zenodo.org/account/settings/applications](https://zenodo.org/account/settings/applications/tokens/new/) and add it to the config file:

```toml
[sources.zenodo]
api_key = "YOUR_TOKEN"
```

### Crossref — email optional

Crossref works without any credentials. Providing your email opts the client into the [polite pool](https://api.crossref.org/swagger-ui/index.html), granting up to 50 requests per second. MOSAIC reuses the Unpaywall email automatically — no separate step needed once `--unpaywall-email` is set.

To disable the source entirely:
```toml
[sources.crossref]
enabled = false
```

### arXiv, DOAJ, Europe PMC, BASE

These sources require no credentials and are ready to use out of the box.
