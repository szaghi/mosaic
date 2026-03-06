---
title: Changelog
---

# Changelog

## 0.1.0 — 2026-03-06

Initial release.

### Sources
- arXiv (no auth, full OA, direct PDF links)
- Semantic Scholar (214M papers, `openAccessPdf` field)
- ScienceDirect (Elsevier, OA filter, API key required)
- DOAJ (100% open-access journals)
- Europe PMC (biomedical, PMC PDF links)
- Unpaywall (PDF resolver for any DOI)

### Commands
- `mosaic search` — fan-out search with deduplication, OA filter, optional download
- `mosaic get` — download by DOI with Unpaywall fallback
- `mosaic config` — view and update configuration

### Infrastructure
- SQLite cache for metadata and download history
- TOML config at `~/.config/mosaic/config.toml`
- Rich terminal table output with OA and PDF indicators
- Per-source error reporting (warnings, not fatal)
