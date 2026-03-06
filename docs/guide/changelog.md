---
title: Changelog
---

## [0.0.14] — 2026-03-06
### Added
- **notebooklm**: Add artifact generation flags for all NotebookLM output types

- **cli**: Add --download-dir flag to search and notebook create


## [0.0.13] — 2026-03-06
### Fixed
- **sources**: Add trailing slash to CORE API URL to avoid 301 redirect


## [0.0.12] — 2026-03-06
### Added
- **cli**: Allow --output to be repeated for concurrent multi-format export


## [0.0.11] — 2026-03-06
### Added
- **cli**: Add --output flag to export results as md, markdown, csv, json, bib


### Fixed
- **cli**: Prevent DOI column from being truncated in results table


## [0.0.10] — 2026-03-06
### Fixed
- **sources**: Synthesize canonical arXiv DOI when journal DOI is absent


## [0.0.9] — 2026-03-06
### Added
- **cli**: Add DOI column to results table and fix arXiv cross-source dedup


## [0.0.8] — 2026-03-06
### Added
- **cli**: Add --pdf-only flag to filter results to papers with a PDF URL


## [0.0.7] — 2026-03-06
### Added
- **search**: Add --field and --raw-query options for fine-grained query scoping


## [0.0.6] — 2026-03-06
### Added
- **cli**: Add --version / -v flag and complete CLI reference docs

- **notebooklm**: Add --year/-y, --author/-a, --journal/-j to notebook create


### Documentation
- Improve README intro and NotebookLM artifact listing

- **configuration**: Expand source credentials into per-source subsections

- **sources**: Add Semantic Scholar API key registration steps


## [0.0.5] — 2026-03-06
### Added
- **sources**: Add CORE open-access aggregator source

- **notebooklm**: Add Google NotebookLM integration via notebooklm-py


### Documentation
- Update all source listings to include OpenAlex and BASE


## [0.0.4] — 2026-03-06
### Added
- **sources**: Add BASE (Bielefeld Academic Search Engine) source


## [0.0.3] — 2026-03-06
### Added
- **sources**: Add OpenAlex as a sixth search source



