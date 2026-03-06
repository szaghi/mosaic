---
title: Configuration
---

# Configuration

MOSAIC stores its configuration in `~/.config/mosaic/config.toml`. The file is created automatically with defaults on first run.

## Quick setup

```bash
# Set your Unpaywall email (enables PDF fallback for any DOI)
mosaic config --unpaywall-email you@example.com

# Set an Elsevier API key (enables ScienceDirect source)
mosaic config --elsevier-key YOUR_KEY

# Set a Semantic Scholar API key (optional — higher rate limit)
mosaic config --ss-key YOUR_KEY

# Change where PDFs are saved
mosaic config --download-dir ~/papers

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
# Required to use this source. Register free at https://dev.elsevier.com
# Without an institutional token, only open-access content is returned.
api_key = ""

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
```

## Source credentials

### ScienceDirect (Elsevier) — API key required

ScienceDirect is **disabled** until an Elsevier API key is set. Without it MOSAIC simply skips the source.

1. Register at [dev.elsevier.com](https://dev.elsevier.com) (free for academic/non-commercial use)
2. Create a new API key under **My API Key List**
3. Apply it:

```bash
mosaic config --elsevier-key YOUR_KEY
```

::: tip Institutional access
Without an institutional token, only open-access articles are returned. For full-text access to subscribed content, your institution's library must request an **Institution Token** from Elsevier. Running MOSAIC from campus or via your institution's VPN grants the same access as a browser login through IP-based authentication — no extra config needed.
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

### arXiv, DOAJ, Europe PMC, BASE

These sources require no credentials and are ready to use out of the box.
