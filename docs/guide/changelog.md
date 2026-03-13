---
title: Changelog
---

## [1.3.9] — 2026-03-13
### Added
- **sources**: Enhance PEDro source with full metadata and CLI controls


### Fixed
- **desktop**: Use Chrome/Edge app mode for native window instead of browser tab

- **release**: Prevent dangling tag when push fails


## [1.3.8] — 2026-03-13
### Fixed
- **desktop**: Replace pywebview with browser launch to fix Windows bundling


## [1.3.7] — 2026-03-13
### Fixed
- **build**: Fix pythonnet coreclr runtime for Windows PyInstaller bundle


## [1.3.6] — 2026-03-13
### Documentation
- Add --output export section to usage guide and update web UI demo


### Fixed
- **build**: Use edgechromium backend to avoid pythonnet DLL failure on Windows


## [1.3.5] — 2026-03-13
### Fixed
- **docs**: Escape mustache syntax in obsidian plugin compat table


## [1.3.4] — 2026-03-12
### Added
- Add Obsidian vault integration and complete web UI parity


### Fixed
- **test**: Mock _require_playwright in scopus browser exception test


## [1.3.3] — 2026-03-12
### Added
- **sources**: Add Scopus API and browser search sources


### Fixed
- **cli**: Add scopus to --source help text and enable tab completion


## [1.3.2] — 2026-03-12
### Added
- **sources**: Add PEDro physiotherapy evidence database source


## [1.3.1] — 2026-03-11
### Fixed
- **ui**: Include templates/static in wheel and add web UI demo


## [1.3.0] — 2026-03-11
### Added
- **ui**: Add web interface with Waitress server, parallel search, and HTMX dashboard

- **build**: Add PyInstaller packaging for standalone macOS/Linux/Windows executables

- **build**: Add PyInstaller packaging for standalone macOS/Linux/Windows executables

- **desktop**: Replace browser launch with native pywebview window

- **ui**: Add missing CLI features to web interface


### Documentation
- Add authors section to README and docs index


### Fixed
- **ci**: Install UI deps in test job so test_ui.py can import Flask

- **ci**: Install UI extra so test_ui.py can import Flask


## [1.2.18] — 2026-03-10
### Added
- **sources**: Add bioRxiv/medRxiv preprint source


## [1.2.17] — 2026-03-10
### Added
- **zotero**: Add Zotero integration with local and web API support


## [1.2.16] — 2026-03-10
### Added
- **get**: Add bulk download from BibTeX and CSV files


## [1.2.15] — 2026-03-10
### Added
- **sources**: Add PubMed Central search source via NCBI E-utilities


## [1.2.14] — 2026-03-10
### Added
- **sources**: Add PubMed search source via NCBI E-utilities


## [1.2.13] — 2026-03-10
### Added
- **search**: Add --verbose flag with per-source deduplication stats


## [1.2.12] — 2026-03-10
### Added
- **cli**: Add mosaic similar command for related-paper discovery


## [1.2.11] — 2026-03-10
### Added
- **search**: Add --sort flag to rank results by citations or year


### Documentation
- Add terminal demo GIFs and VHS recording script


## [1.2.10] — 2026-03-10
### Fixed
- **security**: Restrict config and session file permissions to owner


## [1.2.9] — 2026-03-10
### Added
- **sources**: Add HAL open archive source


## [1.2.8] — 2026-03-09
### Added
- **sources**: Add DBLP computer science bibliography source


## [1.2.7] — 2026-03-09
### Added
- **sources**: Add IEEE Xplore search source


## [1.2.6] — 2026-03-09
### Added
- **sources**: Add Springer Nature Open Access API source


## [1.2.5] — 2026-03-09
### Added
- **sources**: Add Crossref metadata source


## [1.2.4] — 2026-03-09
### Added
- **sources**: Add Zenodo research repository source


### Documentation
- Sync source lists in README, docs/index.md, and CLAUDE.md


## [1.2.3] — 2026-03-09
### Added
- **sources**: Add NASA ADS search source


## [1.2.2] — 2026-03-09
### Documentation
- **sources**: Add Google-style docstrings to all source modules


## [1.2.1] — 2026-03-09
### Added
- **auth**: Add session validity check and browser source warnings


## [1.2.0] — 2026-03-09
### Added
- **sources**: Add Springer Nature browser-based search source


## [1.1.0] — 2026-03-09
### Added
- **sources**: Add ScienceDirect browser-based search via saved session


## [1.0.0] — 2026-03-08
### Added
- **auth**: Add browser session management and authenticated PDF download


### Changed
- Rename acronym expansion from Index to Indexer everywhere


### Documentation
- Add project subtitle and expand header across README and docs

- Add GitHub release version badge to README

- Add MOSAIC logo with dark/light theme switching to README and docs


## [0.1.1] — 2026-03-07
### Documentation
- **custom-sources**: Clarify multi-source support and add HAL/Zenodo example


## [0.1.0] — 2026-03-07
### Added
- **sources**: Add generic custom source configurable via TOML


## [0.0.17] — 2026-03-07
### Fixed
- **exporter**: Create parent directories when output path does not exist


## [0.0.16] — 2026-03-07
### Added
- **cli**: Add configurable PDF filename pattern with placeholder support


### Documentation
- Update source count wording in about page

- Expand README and about page with why/design sections


## [0.0.15] — 2026-03-06
### Fixed
- **tests**: Update notebooklm bridge tests to use artifacts set parameter


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



