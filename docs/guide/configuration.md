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
```

## Obtaining API keys

### Elsevier / ScienceDirect

1. Register at [dev.elsevier.com](https://dev.elsevier.com)
2. Create a new API key (free for academic/non-commercial use)
3. Run `mosaic config --elsevier-key YOUR_KEY`

::: tip Institutional access
For full-text access to subscribed content, your institution's library must request an **Institution Token** from Elsevier. Running MOSAIC from campus or over your institution's VPN automatically grants the same access as a browser login via IP-based authentication.
:::

### Semantic Scholar

An API key is optional but gives you a dedicated rate limit slot instead of sharing the public pool. Request one at [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api).

### Unpaywall

No key required — just provide any valid email address. Unpaywall uses it only for usage tracking.
