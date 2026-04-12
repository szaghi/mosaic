---
title: CLI Reference
---

# CLI Reference

```
mosaic [OPTIONS] COMMAND [ARGS]...
```

## Global options

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | `-v` | Print the installed version and exit |
| `--verbose` | | Show per-source warnings (hidden by default) |
| `--help` | | Show help and exit |

`--verbose` must appear **before** the subcommand:

```bash
mosaic --version           # e.g. mosaic 0.0.5
mosaic -v
mosaic --verbose search "protein folding"   # show source warnings
```

## Commands

### `search`

Search for papers across all configured sources.

```
mosaic search [OPTIONS] QUERY
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--max` | `-n` | int | `10` | Max results per source |
| `--download` | `-d` | flag | off | Download available PDFs after search |
| `--oa-only` | | flag | off | Show only open-access papers |
| `--pdf-only` | | flag | off | Show only papers with a known PDF URL |
| `--source` | `-s` | str | all | Limit to one source — tab-completes all shorthands |
| `--year` | `-y` | str | | Year filter (see formats below) |
| `--author` | `-a` | str | | Author filter, repeatable |
| `--journal` | `-j` | str | | Journal name substring filter |
| `--field` | `-f` | str | `all` | Scope query to `title`, `abstract`, or `all` — tab-completes |
| `--raw-query` | | str | | Raw query sent directly to APIs, bypasses all transforms |
| `--output` | `-o` | path | | Save results to file (repeatable); format from extension: `.md`, `.markdown`, `.csv`, `.json`, `.bib`, `.ris` |
| `--download-dir` | | path | config | Override PDF download directory for this run only |
| `--sort` | | str | | Sort results: `citations`, `year`, or `relevance` — tab-completes |
| `--stats` | | flag | off | Print per-source counts and deduplication stats |
| `--cached` | | flag | off | Search only the local cache — no network requests |
| `--prefer-cache` | | flag | off | Substitute rich cached records for freshly fetched ones (see [Cache Management](./cache)) |
| `--zotero` | | flag | off | Export results to Zotero |
| `--zotero-collection` | | str | | Zotero collection name (created if missing) |
| `--zotero-local` | | flag | off | Force local API even when a web API key is configured |

**Source shorthands for `--source`:**

| Shorthand | Source | Requires |
|-----------|--------|----------|
| `arxiv` | arXiv | — |
| `ss` | Semantic Scholar | — (API key optional) |
| `sd` | ScienceDirect | API key or browser session |
| `sp` | Springer Nature (browser) | Playwright (`[browser]` extra) |
| `springer` | Springer Nature (API) | Free API key |
| `doaj` | DOAJ | — |
| `epmc` | Europe PMC | — |
| `oa` | OpenAlex | — (email optional) |
| `base` | BASE | — |
| `core` | CORE | Free API key |
| `ads` | NASA ADS | Free API token |
| `ieee` | IEEE Xplore | Free API key |
| `zenodo` | Zenodo | — (access token optional) |
| `crossref` | Crossref | — (email optional) |
| `dblp` | DBLP | — |
| `hal` | HAL | — |
| `pubmed` | PubMed | — (API key optional) |
| `pmc` | PubMed Central | — (API key optional) |
| `rxiv` | bioRxiv / medRxiv | — |
| `scopus` | Scopus | API key or browser session |

**`--year` / `-y` formats:**

| Format | Example | Meaning |
|--------|---------|---------|
| Single year | `2020` | Exact year |
| Range | `2018-2022` | Inclusive range |
| List | `2019,2021,2023` | Specific years only |

**`--author` / `-a` behaviour:**
- Case-insensitive substring match against any author name in the paper
- Repeat the flag for multiple authors — paper must match **at least one**
- Example: `-a Hinton -a LeCun` returns papers authored by either

**`--journal` / `-j` behaviour:**
- Case-insensitive substring match against the journal name
- Example: `-j "Nature"` matches *Nature*, *Nature Communications*, *Nature Methods*, etc.

**Filter application:**

Each filter is applied at the **source API level** where supported, then as a **post-processing step** on all returned results:

| Source | Year | Author | Journal |
|--------|:----:|:------:|:-------:|
| arXiv | ✓ native | ✓ native | ✓ native |
| Semantic Scholar | ✓ native | post-process | post-process |
| ScienceDirect | ✓ native | ✓ native | ✓ native |
| Europe PMC | ✓ native | ✓ native | ✓ native |
| DOAJ | ✓ native | ✓ native | ✓ native |
| OpenAlex | ✓ native | post-process | post-process |
| BASE | ✓ native | ✓ native | ✓ native |
| CORE | ✓ native | ✓ native | ✓ native |
| NASA ADS | ✓ native | post-process | post-process |
| bioRxiv/medRxiv | ✓ native | ✓ native | post-process |

**`--sort` behaviour:**
- `citations`: sort by citation count descending; adds a **Cited** column to the results table
- `year`: sort by publication year descending (newest first)
- `relevance`: re-score every paper against the query and sort by score descending; adds a **Rel.** column (0.00 – 1.00).  Uses BM25 by default; upgrades to LLM scoring when `[llm]` is configured.  See the [Relevance Ranking guide](./relevance-ranking) for setup.

**`--field` / `-f` behaviour:**
- `all` (default): query is sent as a general full-text search to each source
- `title`: scopes the query to the title field using each source's native syntax
- `abstract`: scopes the query to the abstract field using each source's native syntax

**`--raw-query` behaviour:**
- Sent verbatim to every queried source, bypassing all field/author/journal transforms
- Useful for power-users who know each source's query language (e.g. arXiv's `ti:` prefixes, Lucene syntax for BASE/DOAJ/CORE)
- Note: year filter (`-y`) is still applied as post-processing even when `--raw-query` is set

**`--output` / `-o` formats:**

Format is inferred from the file extension:

| Extension | Format | Contents |
|-----------|--------|----------|
| `.md` | Markdown table | Compact summary: title, authors, year, DOI, source, OA, PDF |
| `.markdown` | Markdown sections | One `##` subsection per paper with a full-field key/value table; empty fields omitted |
| `.csv` | CSV | All fields; authors joined with `;`; opens in Excel / Google Sheets |
| `.json` | JSON array | All fields as a JSON list; authors as a native array; suitable for scripting |
| `.bib` | BibTeX | `@article` for journal papers, `@misc` for preprints; includes `eprint`/`eprinttype` for arXiv, `abstract`, `pdf`, OA note |
| `.ris` | RIS | Standard interchange format; `JOUR`/`GEN` type; one `AU` per author; `SP`/`EP` pages; compatible with EndNote, Mendeley, RefWorks, Papers |

**Examples:**

```bash
# Search all sources
mosaic search "protein folding"

# 25 results per source, open-access only
mosaic search "deep learning" -n 25 --oa-only

# Filter by year range
mosaic search "diffusion models" -y 2020-2023

# Relevance-ranked results (BM25 or LLM — see Relevance Ranking guide)
mosaic search "transformer attention" --sort relevance

# Filter by exact year and author
mosaic search "attention" -y 2017 -a Vaswani

# Filter by journal (substring)
mosaic search "CRISPR" -j "Nature" -y 2021-2023

# Multiple authors (OR), single source, download
mosaic search "graph neural" -a Kipf -a Velickovic --source ss --download

# Search arXiv only, download PDFs
mosaic search "diffusion models" --source arxiv --download

# Scope query to title only
mosaic search "attention mechanism" --field title

# Scope query to abstract only (shorter synonym)
mosaic search "CRISPR off-target" -f abstract --source epmc -n 50

# Power-user raw query (arXiv native syntax)
mosaic search "" --raw-query "ti:transformers AND au:Vaswani" --source arxiv

# Save results to Markdown (summary table)
mosaic search "protein folding" -n 20 --output results.md

# Save results to Markdown (one subsection per paper, all fields)
mosaic search "protein folding" -n 20 --output results.markdown

# Save to BibTeX for import into Zotero / JabRef / LaTeX
mosaic search "diffusion models" -y 2023-2025 --oa-only --output refs.bib

# Save to CSV for Excel / Sheets
mosaic search "CRISPR" -j "Nature" --output crispr.csv

# Save full metadata as JSON
mosaic search "attention mechanism" --output attention.json

# Save to multiple formats in one search
mosaic search "diffusion models" -y 2023-2025 --oa-only \
  --output results.md --output refs.bib --output results.json
```

![Output formats demo](/gifs/08_output_formats.gif)

---

### `similar`

Find papers related to a given DOI or arXiv ID.

```
mosaic similar [OPTIONS] IDENTIFIER
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--max` | `-n` | int | `10` | Max similar papers to return |
| `--download` | `-d` | flag | off | Download available PDFs |
| `--oa-only` | | flag | off | Show only open-access papers |
| `--pdf-only` | | flag | off | Show only papers with a known PDF URL |
| `--sort` | | str | | Sort: `citations`, `year`, or `relevance` — tab-completes |
| `--output` | `-o` | path | | Save results to file (repeatable) |
| `--download-dir` | | path | config | Override PDF download directory |
| `--zotero` | | flag | off | Export results to Zotero |
| `--zotero-collection` | | str | | Zotero collection name (created if missing) |
| `--zotero-local` | | flag | off | Force local API even when a web API key is configured |

`IDENTIFIER` accepts the same formats as `mosaic get`: a bare DOI, `doi:10.xxx`, `DOI:10.xxx`, `arxiv:NNNN.NNNNN`, or `ARXIV:NNNN.NNNNN`.

Sources used:
- **OpenAlex** `related_works` — always queried; no key required.
- **Semantic Scholar** recommendations — queried when `ss-key` is set in config.

See the [Find Similar Papers guide](./similar) for a full walkthrough and workflow examples.

**Examples:**

```bash
mosaic similar 10.48550/arXiv.1706.03762
mosaic similar arxiv:1706.03762 -n 20 --sort citations
mosaic similar 10.1038/s41586-021-03819-2 --oa-only --download
```

---

### `get`

Download a paper by DOI, or bulk-download all DOIs from a BibTeX or CSV file.

```
mosaic get [OPTIONS] [DOI]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--from` | path | | BibTeX (`.bib`) or CSV (`.csv`) file containing DOIs to bulk-download |
| `--oa-only` | flag | off | In bulk mode: treat unresolvable papers as skipped rather than failed |
| `--download-dir` | path | config | Override PDF download directory for this run |
| `--zotero` | flag | off | Export downloaded paper(s) to Zotero |
| `--zotero-collection` | str | | Zotero collection name (created if missing) |
| `--zotero-local` | flag | off | Force local API even when a web API key is configured |

Provide either a `DOI` positional argument (single download) or `--from <file>` (bulk download) — not both.

**Cache-first lookup:**
Before hitting Unpaywall or a browser session, MOSAIC checks the local cache for the DOI. If the paper was seen in a previous search and a PDF URL is already known, the download starts immediately without any network resolution step. A dim confirmation line is printed when the cache is used.

**Bulk mode behaviour:**
- For `.bib` files: extracts all `doi = {…}` fields (case-insensitive, no extra dependency)
- For `.csv` files: reads the `doi` column (case-insensitive header)
- Duplicate DOIs within the file are downloaded only once
- Entries without a DOI are silently skipped
- Prints a per-entry result line and a final summary: N downloaded, M failed, K skipped

**Examples:**

```bash
# Single DOI
mosaic get 10.48550/arXiv.1706.03762

# Bulk from BibTeX — download all resolvable PDFs
mosaic get --from refs.bib

# Bulk from CSV, skip non-OA entries instead of counting them as failures
mosaic get --from references.csv --oa-only

# Override download directory for this run
mosaic get --from refs.bib --download-dir ~/papers
```

---

### `index`

Build or update the local vector index for semantic search and RAG.

```
mosaic index [OPTIONS]
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--reindex` | | flag | off | Re-embed all papers, even already-indexed ones (required after changing the embedding model) |
| `--query` | `-q` | str | | Embed only papers matching this cache query |
| `--from` | | path | | Embed only papers listed in a `.bib` or `.csv` file |
| `--batch-size` | | int | `96` | Texts sent per embedding API call |
| `--enrich-citations` | | flag | off | Fetch citation edges from OpenAlex / CrossRef after embedding and store them for graph-boosted retrieval |

Requires `sqlite-vec`: `pipx inject mosaic-search sqlite-vec`.
See the [RAG & Literature Analysis guide](./rag) for full setup instructions.

**Examples:**

```bash
# Index all cached papers
mosaic index

# Re-index after switching embedding model
mosaic index --reindex

# Index only a topic subset
mosaic index --query "protein folding"

# Index papers from a BibTeX file
mosaic index --from refs.bib

# Enrich with citation graph (OpenAlex + CrossRef edges)
mosaic index --enrich-citations
```

---

### `ask`

Ask a question about your indexed papers using RAG.

```
mosaic ask [OPTIONS] QUESTION
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--mode` | | str | `synthesis` | Prompt mode: `synthesis`, `gaps`, `compare`, `extract` |
| `--query` | `-q` | str | | Pre-filter: restrict retrieval to papers matching this query |
| `--from` | | path | | Pre-filter: restrict retrieval to papers from a `.bib`/`.csv` |
| `--year` | `-y` | str | | Year filter (same formats as `search`) |
| `--top` | `-n` | int | config | Override `rag.top_k` for this query |
| `--output` | `-o` | path | | Save answer to `.md` or `.json` |
| `--show-sources` | | flag | off | Print retrieved papers before the answer |

**Prompt modes:**

| Mode | What it produces |
|------|-----------------|
| `synthesis` | Comprehensive state-of-the-art summary with [n] citations |
| `gaps` | Open problems, contradictions, and methodological limitations |
| `compare` | Structured comparison: methods, datasets, metrics, results, trade-offs |
| `extract` | Per-paper structured extraction: Task, Method, Dataset, Metric, Key Result |

**Examples:**

```bash
mosaic ask "What are the main approaches to neural machine translation?"
mosaic ask "Open problems in protein structure prediction" --mode gaps
mosaic ask "transformer vs LSTM" --mode compare
mosaic ask "diffusion model scaling" --year 2023-2025
mosaic ask "RLHF" -n 20 --show-sources
mosaic ask "attention mechanisms" --output analysis.md
mosaic ask "CRISPR" --output crispr.json
```

---

### `chat`

Interactive multi-turn RAG session over your cached papers.

```
mosaic chat [OPTIONS]
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--query` | `-q` | str | | Narrow retrieval to papers matching this query |
| `--from` | | path | | Narrow retrieval to papers from a `.bib`/`.csv` |
| `--mode` | | str | `synthesis` | Default prompt mode for the session |

**In-session commands:**

| Command | Effect |
|---------|--------|
| `/mode <mode>` | Switch prompt mode (`synthesis`, `gaps`, `compare`, `extract`) |
| `/sources` | Show the retrieval pool for the current session |
| `/clear` | Clear conversation history |
| `/quit` | Exit the chat |

**Examples:**

```bash
mosaic chat
mosaic chat -q "protein folding"
mosaic chat --mode gaps
mosaic chat --from refs.bib
```

---

### `ui`

Launch the MOSAIC web interface in your browser.

```
mosaic ui [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--host` | str | `127.0.0.1` | Bind address |
| `--port` | int | `5555` | Port number |
| `--no-browser` | flag | off | Don't auto-open the browser |
| `--debug` | flag | off | Use Flask dev server with hot-reload |

Requires the `ui` extra: `pip install 'mosaic-search[ui]'`.

By default, the server uses [Waitress](https://docs.pylonsproject.org/projects/waitress/) (production-grade, multi-threaded). Pass `--debug` to use Flask's built-in dev server with hot-reload for development.

```bash
mosaic ui                          # default: http://127.0.0.1:5555
mosaic ui --port 8080              # custom port
mosaic ui --host 0.0.0.0           # accessible on LAN
mosaic ui --debug                  # development mode
```

See the [Web UI guide](./web-ui) for a full walkthrough.

---

### `config`

View or update MOSAIC configuration.

```
mosaic config [OPTIONS]
```

| Option | Type | Description |
|--------|------|-------------|
| `--show` | flag | Print current config as JSON |
| **API keys** | | |
| `--elsevier-key TEXT` | str | Set Elsevier/ScienceDirect API key |
| `--ss-key TEXT` | str | Set Semantic Scholar API key |
| `--ncbi-key TEXT` | str | Set NCBI API key (PubMed + PMC) |
| `--core-key TEXT` | str | Set CORE API key |
| `--ads-key TEXT` | str | Set NASA ADS API key |
| `--ieee-key TEXT` | str | Set IEEE Xplore API key |
| `--springer-key TEXT` | str | Set Springer Nature API key |
| `--scopus-key TEXT` | str | Set Scopus API key |
| `--scopus-inst-token TEXT` | str | Set Scopus institutional token |
| `--zenodo-key TEXT` | str | Set Zenodo API key / token |
| `--zotero-key TEXT` | str | Set Zotero API key (web API); auto-discovers and caches user ID |
| `--unpaywall-email TEXT` | str | Set Unpaywall email |
| **Sources** | | |
| `--enable-source TEXT` | str | Enable a source by name (repeatable) |
| `--disable-source TEXT` | str | Disable a source by name (repeatable) |
| **Downloads** | | |
| `--download-dir TEXT` | str | Set PDF download directory |
| `--db-path TEXT` | str | Set SQLite cache path |
| `--filename-pattern TEXT` | str | Set PDF filename pattern (see below) |
| `--rate-limit-delay FLOAT` | float | Set default delay between API calls in seconds |
| **Obsidian** | | |
| `--obsidian-vault TEXT` | str | Set Obsidian vault path |
| `--obsidian-subfolder TEXT` | str | Set subfolder inside vault for paper notes |
| `--obsidian-filename-pattern TEXT` | str | Set Obsidian note filename pattern |
| `--obsidian-tag TEXT` | str | Set Obsidian tags (repeatable, replaces existing list) |
| `--obsidian-wikilinks / --no-obsidian-wikilinks` | bool | Use `[[wikilinks]]` in generated notes |
| **PEDro** | | |
| `--pedro-fair-use / --no-pedro-fair-use` | bool | Acknowledge PEDro fair-use policy (required to enable source) |
| `--pedro-fetch-details / --no-pedro-fetch-details` | bool | Fetch detail pages for richer metadata (slower) |
| `--pedro-rate-limit-delay FLOAT` | float | Delay between PEDro requests in seconds (default: 3.0) |
| **LLM** | | |
| `--llm-provider TEXT` | str | LLM provider for relevance ranking: `openai` or `anthropic` |
| `--llm-api-key TEXT` | str | API key for the LLM provider (any string for local servers) |
| `--llm-model TEXT` | str | Model name; defaults to `gpt-4o-mini` (openai) or `claude-haiku-4-5-20251001` (anthropic) |
| `--llm-base-url TEXT` | str | Base URL for a local OpenAI-compatible server (e.g. `http://localhost:11434/v1`) |
| **RAG / Embeddings** | | |
| `--embedding-model TEXT` | str | Embedding model name (e.g. `snowflake-arctic-embed2`, `text-embedding-3-small`) |
| `--embedding-base-url TEXT` | str | Base URL for the embedding server (e.g. `http://localhost:11434/v1`) |
| `--embedding-api-key TEXT` | str | API key for the embedding server (any string for local servers) |
| `--rag-top-k INT` | int | Number of papers retrieved per RAG query (default: 10) |
| `--rag-auto-index / --no-rag-auto-index` | bool | Auto-index new papers after each search/get run |

**`--filename-pattern` placeholders:**

| Placeholder | Value |
|-------------|-------|
| `{year}` | Publication year (or `0000` if unknown) |
| `{source}` | Source name (e.g. `arXiv`, `DOAJ`) |
| `{author}` | First author's last name |
| `{title}` | Title slug, truncated to 60 characters |
| `{doi}` | DOI with special characters replaced by `_` |
| `{journal}` | Journal name slug (or `no_journal` if unknown) |

The default pattern is `{year}_{source}_{author}_{title}`, which produces filenames like `2017_arXiv_Vaswani_Attention_Is_All_You_Need.pdf`.

**Examples:**

```bash
# Show current config
mosaic config --show

# Set multiple values at once
mosaic config --unpaywall-email me@uni.edu --download-dir ~/papers

# API keys
mosaic config --elsevier-key abc123def456
mosaic config --ncbi-key YOUR_KEY          # sets both PubMed and PMC
mosaic config --core-key YOUR_KEY
mosaic config --ads-key YOUR_KEY
mosaic config --ieee-key YOUR_KEY
mosaic config --springer-key YOUR_KEY
mosaic config --scopus-key YOUR_KEY --scopus-inst-token YOUR_INST_TOKEN
mosaic config --zenodo-key YOUR_TOKEN

# Enable / disable sources
mosaic config --disable-source dblp --disable-source hal
mosaic config --enable-source dblp

# Downloads
mosaic config --filename-pattern "{author}_{year}_{title}"
mosaic config --rate-limit-delay 0.5
mosaic config --db-path ~/mydata/mosaic.db

# Obsidian integration
mosaic config --obsidian-vault ~/Documents/MyVault --obsidian-subfolder literature
mosaic config --obsidian-tag paper --obsidian-tag science
mosaic config --no-obsidian-wikilinks

# Configure LLM relevance scoring — cloud OpenAI
mosaic config --llm-provider openai --llm-api-key sk-... --llm-model gpt-4o-mini

# Configure LLM relevance scoring — local Ollama
mosaic config --llm-provider openai \
              --llm-base-url http://localhost:11434/v1 \
              --llm-api-key ollama \
              --llm-model llama3.2
```

---

### `notebook create`

Create a Google NotebookLM notebook from a search query or a directory of PDFs.

```
mosaic notebook create [OPTIONS] NAME
```

Requires the `[notebooklm]` extra — see [NotebookLM Integration](./notebooklm).

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--query` | `-q` | str | | Search query to populate the notebook |
| `--from-dir` | | path | | Import all PDFs from this directory |
| `--max` | `-n` | int | `10` | Max results per source (with `--query`) |
| `--oa-only` | | flag | off | Only include open-access papers |
| `--pdf-only` | | flag | off | Only include papers with a known PDF URL |
| `--year` | `-y` | str | | Year filter (same formats as `search`) |
| `--author` | `-a` | str | | Author filter, repeatable |
| `--journal` | `-j` | str | | Journal name substring filter |
| `--field` | `-f` | str | `all` | Scope query to `title`, `abstract`, or `all` — tab-completes |
| `--raw-query` | | str | | Raw query sent directly to APIs, bypasses all transforms |
| `--download-dir` | | path | config | Override PDF download directory for this run only |
| `--podcast` | | flag | off | Queue an Audio Overview after import |
| `--video` | | flag | off | Queue a Video Overview after import |
| `--briefing` | | flag | off | Queue a Briefing Doc after import |
| `--study-guide` | | flag | off | Queue a Study Guide after import |
| `--quiz` | | flag | off | Queue a Quiz after import |
| `--flashcards` | | flag | off | Queue Flashcards after import |
| `--infographic` | | flag | off | Queue an Infographic after import |
| `--slide-deck` | | flag | off | Queue a Slide Deck after import |
| `--data-table` | | flag | off | Queue a Data Table after import |
| `--mind-map` | | flag | off | Queue a Mind Map after import |

`--query` and `--from-dir` are mutually exclusive; exactly one must be provided. Filters (`-y`, `-a`, `-j`, `-f`, `--raw-query`) only apply when using `--query`. `--oa-only` and `--pdf-only` apply in both modes.

**Examples:**

```bash
# Search, download, and import into a new notebook
mosaic notebook create "Transformers" --query "attention is all you need" --oa-only

# Queue an Audio Overview (podcast) after import
mosaic notebook create "AMR-GPU" --query "adaptive mesh refinement gpu" -y 2024-2026 --oa-only --podcast

# Queue multiple artifacts at once
mosaic notebook create "CRISPR 2024" --query "CRISPR gene editing" --oa-only \
  --briefing --quiz --mind-map

# Filter by author and journal
mosaic notebook create "Hinton Papers" --query "deep learning" -a Hinton -j "Nature" --oa-only

# Import PDFs you already have locally
mosaic notebook create "My Papers" --from-dir ~/mosaic-papers/

# Import local PDFs and queue a slide deck
mosaic notebook create "My Papers" --from-dir ~/mosaic-papers/ --slide-deck
```

---

### `auth login`

Open a browser, log in to a site, and save the session for future PDF downloads.

```
mosaic auth login [OPTIONS] NAME
```

| Argument / Option | Type | Description |
|---|---|---|
| `NAME` | str | Session label — tab-completes common providers: `elsevier`, `springer`, `scopus` |
| `--url` / `-u` | str | URL to open in the browser *(required)* |

Requires the `[browser]` extra — see [Authenticated Access](./authenticated-access).

MOSAIC tries browsers in order: Chromium → Firefox → WebKit.

**Examples:**

```bash
mosaic auth login elsevier --url https://www.sciencedirect.com/user/login
mosaic auth login myuni    --url https://library.myuni.edu/login
```

---

### `auth status`

List all saved browser sessions.

```bash
mosaic auth status
```

---

### `auth logout`

Remove a saved browser session.

```
mosaic auth logout [OPTIONS] NAME
```

| Argument | Description |
|---|---|
| `NAME` | Session name to remove — tab-completes from your saved sessions |

```bash
mosaic auth logout elsevier
```

---

### `cache stats`

Print a summary of the local cache.

```bash
mosaic cache stats
```

---

### `cache list`

List cached papers, newest-first.

```
mosaic cache list [OPTIONS]
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--limit` | `-n` | int | `20` | Max papers to show |
| `--offset` | | int | `0` | Skip this many rows (pagination) |
| `--query` | `-q` | str | | Substring filter on title and abstract |

---

### `cache show`

Show the full cached record for a paper identified by DOI or arXiv ID.

```
mosaic cache show IDENTIFIER
```

`IDENTIFIER` accepts the same formats as `mosaic get`: bare DOI, `doi:10.xxx`, `arxiv:NNNN.NNNNN`, etc.

---

### `cache verify`

Check whether each tracked PDF file still exists on disk.

```bash
mosaic cache verify
```

Prints a line per tracked download with a ✓ / ✗ indicator and a final count of missing files.

---

### `cache clean`

Remove download records whose PDF files no longer exist on disk.

```bash
mosaic cache clean
```

Only records with `status=ok` are checked. Paper metadata is never deleted.

---

### `cache clear`

Wipe all papers, downloads, searches, and exports from the cache.

```
mosaic cache clear [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--yes` | Skip the confirmation prompt |

PDF files already on disk are not deleted.

---

### `cache export`

Bulk-export all cached papers to a file. Format is inferred from the extension.

```
mosaic cache export [OPTIONS] OUTPUT
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--query` | `-q` | str | | Substring filter before exporting |

Supported extensions: `.csv`, `.json`, `.bib`, `.md`, `.markdown` — same semantics as `--output` on `search`.

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Invalid argument or unknown source |
