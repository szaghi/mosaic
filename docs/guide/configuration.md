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

![Configuration setup demo](/gifs/05_config.gif)

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

[sources.springer_api]
enabled = true
# Optional. Register free at https://dev.springernature.com
# Returns only open-access articles with direct PDF links.
# Disabled automatically when api_key is empty.
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

[sources.ieee]
enabled = true
# Required. Register free at https://developer.ieee.org
# Returns IEEE journals, transactions, and conference proceedings.
# Disabled automatically when api_key is empty. Free tier: 200 req/day.
api_key = ""

[sources.zenodo]
enabled = true
# Optional. Create a personal access token at https://zenodo.org/account/settings/applications/
# Anonymous access works without a token (60 req/min limit).
api_key = ""

[sources.crossref]
enabled = true
# No credentials required. Reuses the unpaywall.email for the polite pool (50 req/s).

[sources.dblp]
enabled = true
# No credentials required. CS bibliography — journals, conferences, workshops.

[sources.hal]
enabled = true
# No credentials required. French open archive — strong for French academic output and grey literature.

[sources.pubmed]
enabled = true
# Optional. NCBI API key raises rate limit from 3 req/s to 10 req/s.
# One key works for both PubMed and PubMed Central.
# Register free at https://www.ncbi.nlm.nih.gov/account/
api_key = ""

[sources.pmc]
enabled = true
# Optional. Same NCBI API key as [sources.pubmed].
api_key = ""

[sources.biorxiv]
enabled = true
# No credentials required. Searches bioRxiv and medRxiv preprint servers.

[sources.pedro]
enabled = true
# Disabled until you explicitly acknowledge PEDro's Fair Use policy.
# Set acknowledge_fair_use = true to enable.
acknowledge_fair_use = false
# Seconds between HTTP requests. 3.0 s is the safe-fair default.
# Lower only if your usage stays within PEDro's acceptable-use terms.
rate_limit_delay = 3.0

[sources.scopus]
enabled = true
# Free API key from https://dev.elsevier.com — same account as ScienceDirect.
# If omitted, MOSAIC falls back to a saved browser session for search
# (see Authenticated Access → Scopus). Disabled when both are absent.
api_key = ""
# Optional institutional token — unlocks full abstracts and complete author
# lists for subscribers. Request from Elsevier support if your institution
# has a Scopus subscription.
inst_token = ""
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

### Springer Nature API — free API key

The Springer Nature API source (`springer`) returns only open-access articles and includes direct PDF links. Register for a free key at [dev.springernature.com](https://dev.springernature.com) and add it to the config:

```toml
[sources.springer_api]
api_key = "YOUR_KEY"
```

The source is disabled automatically when `api_key` is empty.

### Springer Nature browser — no credentials required

The browser-based Springer source (`sp`) is publicly accessible. It activates
automatically when Playwright is installed (`pip install 'mosaic-search[browser]'`).
No API key or browser session is needed for searching. A saved session is
used only for PDF downloads of subscribed articles — see
[Authenticated Access](./authenticated-access).

Both Springer sources can run simultaneously; results are deduplicated by DOI.

To disable the browser source:
```toml
[sources.springer]
enabled = false
```

### IEEE Xplore — free API key required

IEEE Xplore is **disabled** until an API key is set. Registration is free.

1. Sign up at [developer.ieee.org](https://developer.ieee.org)
2. Create an application to receive an API key
3. Add it to the config file:

```toml
# ~/.config/mosaic/config.toml
[sources.ieee]
api_key = "YOUR_KEY"
```

The free tier allows 200 requests per day.

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

### Scopus — API key or browser session

Scopus supports two access modes (same as ScienceDirect):

| Credentials | What MOSAIC does |
|---|---|
| **Elsevier API key** | Uses the Scopus Search API. Free key returns partial metadata; add `inst_token` for full abstracts. |
| **Browser session** (no API key) | Searches via headless Firefox. Shares the `id.elsevier.com` SSO with ScienceDirect. |
| **Neither** | Source is skipped. |

The Elsevier API key is the same one used for ScienceDirect. If you have already run `mosaic config --elsevier-key YOUR_KEY`, add the same key to the Scopus config:

```toml
[sources.scopus]
api_key = "YOUR_KEY"
```

For browser-session setup see [Authenticated Access → Scopus](./authenticated-access#scopus). The full API key registration procedure is documented in [Sources → Scopus](./sources#scopus--shorthand-scopus).

### arXiv, DOAJ, Europe PMC, BASE, DBLP, HAL

These sources require no credentials and are ready to use out of the box. DBLP is particularly useful for computer science conference and journal papers; note that it does not provide abstracts. HAL is the French national open archive, strong for French academic output and grey literature.

### PEDro — explicit fair-use opt-in required

PEDro is the specialised physiotherapy evidence database (~67 700 RCTs, systematic reviews, and clinical practice guidelines).  It is **disabled by default** because its [Fair Use policy](https://pedro.org.au/fair-use/) prohibits automated bulk downloading.

To enable it, edit the config file directly:

```toml
# ~/.config/mosaic/config.toml
[sources.pedro]
enabled = true
acknowledge_fair_use = true   # required — confirms you will use small, targeted queries only

# Optional: adjust the delay between HTTP requests (default: 3.0 s)
# Lower this only if you have verified your usage stays within PEDro's fair-use terms.
rate_limit_delay = 3.0
```

Once enabled, PEDro appears in all multi-source searches and can also be targeted directly:

```bash
mosaic search "chronic low back pain" --source pedro --field title
```
