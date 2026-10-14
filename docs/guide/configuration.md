---
title: Configuration
---

# Configuration

mosaic reads its settings from `~/.config/mosaic/config.toml`. Every key has a default, so the file only holds what
you change. You edit it with `mosaic config` flags or by hand; this page lists every key and the flag that sets it.

## Where things live

| What | Default location | Key |
|---|---|---|
| Configuration | `~/.config/mosaic/config.toml` | |
| Browser sessions (`mosaic auth login`) | `~/.config/mosaic/sessions/` | |
| Cache: papers, downloads, searches, watches, vector index | `~/.local/share/mosaic/cache.db` | `db_path` |
| Downloaded PDFs | `~/mosaic-papers/` | `download_dir` |

mosaic writes the configuration file the first time a `mosaic config` flag changes something, readable by you only
(mode 0600: it holds API keys). Until then the defaults apply.

## Reading and changing it

```bash
mosaic config --show                                # print the merged configuration as JSON
mosaic config --unpaywall-email you@example.org     # change one setting, then save
mosaic config --download-dir ~/papers --rate-limit-delay 2
```

`mosaic config` with no flag prints the configuration too. Several flags combine in one call. Keys that have no
flag (marked "edit the file" below) go into the TOML file directly; mosaic merges the file over its defaults when it
starts, and logs a warning for a value of the wrong type or an unknown source name.

A first setup usually needs one line, the e-mail that Unpaywall requires to find open PDFs:

```bash
mosaic config --unpaywall-email you@example.org
```

## Top-level keys

| Key | Default | Flag | Meaning |
|---|---|---|---|
| `download_dir` | `~/mosaic-papers` | `--download-dir` | Where PDFs are saved; `--download-dir` on `search`, `get`, `import` overrides it per run |
| `db_path` | `~/.local/share/mosaic/cache.db` | `--db-path` | The SQLite cache |
| `filename_pattern` | `{year}_{source}_{author}_{title}` | `--filename-pattern` | Name of a downloaded PDF, see [File names](#file-names) |
| `rate_limit_delay` | `1.0` | `--rate-limit-delay` | Seconds between two arXiv requests |
| `custom_sources` | `[]` | edit the file | Extra JSON APIs searched like built-in sources: [Custom sources](./custom-sources) |

## File names

`filename_pattern` builds the name of every PDF that `search --download`, `get`, `get --handoff` and `import`
save. The same placeholders work in `obsidian.filename_pattern` for note names.

| Placeholder | Value | When missing |
|---|---|---|
| `{year}` | publication year | `0000` |
| `{source}` | source that returned the paper (`arXiv`, `DOAJ`, `Crossref`, ...) | |
| `{author}` | first word of the first author's name, as the source lists it | `Unknown` |
| `{title}` | title, punctuation removed, cut to 60 characters, spaces as `_` | |
| `{doi}` | DOI with characters other than letters, digits, `.` and `-` replaced by `_` | `no_doi` |
| `{journal}` | journal name, cleaned like the title | `no_journal` |

`{author}` is a family name for sources that list "Family, Given" (Crossref: `2005_Crossref_Boyd_...`) and a given
name for those that list "Given Family" (arXiv, DOAJ: `2004_arXiv_Jose_...`). Already downloaded papers are
recognised by the cache, so changing the pattern renames nothing and downloads nothing twice; new downloads use
the new pattern.

```bash
mosaic config --filename-pattern "{year}_{journal}_{author}_{title}"
```

## Sources

Each source has a table `[sources.<name>]` with `enabled = true` and, for some, more keys. `--enable-source NAME`
and `--disable-source NAME` (repeatable) switch sources on and off by config name:

| Config name | `--source` | Extra keys |
|---|---|---|
| `arxiv` | `arxiv` | |
| `semantic_scholar` | `ss` | `api_key` |
| `sciencedirect` | `sd` | `api_key` |
| `springer` | `sp` | |
| `springer_api` | `springer` | `api_key` |
| `doaj` | `doaj` | |
| `europepmc` | `epmc` | |
| `cochrane` | `cochrane` | |
| `openalex` | `oa` | |
| `base` | `base` | |
| `core` | `core` | `api_key` |
| `nasa_ads` | `ads` | `api_key` |
| `ieee` | `ieee` | `api_key` |
| `zenodo` | `zenodo` | `api_key` |
| `crossref` | `crossref` | |
| `dblp` | `dblp` | |
| `hal` | `hal` | |
| `pubmed` | `pubmed` | `api_key` |
| `pmc` | `pmc` | `api_key` |
| `biorxiv` | `rxiv` | |
| `pedro` | `pedro` | `acknowledge_fair_use`, `fetch_details`, `rate_limit_delay` |
| `scopus` | `scopus` | `api_key`, `inst_token` |

```bash
mosaic config --disable-source base --disable-source zenodo
```

What each source covers and needs: [Sources](./sources).

### API keys

| Key | Flag | Get it at |
|---|---|---|
| `sources.semantic_scholar.api_key` | `--ss-key` | [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api) |
| `sources.sciencedirect.api_key` | `--elsevier-key` | [dev.elsevier.com](https://dev.elsevier.com) |
| `sources.scopus.api_key` | `--scopus-key` | [dev.elsevier.com](https://dev.elsevier.com) (same Elsevier key) |
| `sources.scopus.inst_token` | `--scopus-inst-token` | Elsevier support, through your library |
| `sources.springer_api.api_key` | `--springer-key` | [dev.springernature.com](https://dev.springernature.com) |
| `sources.core.api_key` | `--core-key` | [core.ac.uk/services/api](https://core.ac.uk/services/api) |
| `sources.nasa_ads.api_key` | `--ads-key` | [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu/user/settings/token) |
| `sources.ieee.api_key` | `--ieee-key` | [developer.ieee.org](https://developer.ieee.org) |
| `sources.zenodo.api_key` | `--zenodo-key` | [zenodo.org](https://zenodo.org/account/settings/applications/tokens/new/) |
| `sources.pubmed.api_key`, `sources.pmc.api_key` | `--ncbi-key` (sets both) | [ncbi.nlm.nih.gov](https://www.ncbi.nlm.nih.gov/account/) |

CORE, NASA ADS, IEEE Xplore and the Springer Nature API are skipped until their key is set; the others work
without one.

### ScienceDirect (Elsevier)

ScienceDirect searches with the Elsevier API when `sources.sciencedirect.api_key` is set, and otherwise through a
saved browser session (`mosaic auth login`), if one is valid. Create the key at
[dev.elsevier.com](https://dev.elsevier.com), under "Manage API Keys"; a new key can take up to 15 minutes to
activate, and answers HTTP 401 until then. In API mode mosaic asks for open-access articles only. The browser
session sees what your institution subscribes to. Scopus works the same way with its own key and
`inst_token`. Sessions: [Authenticated access](./authenticated-access).

```bash
mosaic config --elsevier-key KEY --scopus-key KEY
```

### PEDro

| Key | Default | Flag |
|---|---|---|
| `acknowledge_fair_use` | `false` | `--pedro-fair-use` / `--no-pedro-fair-use` |
| `fetch_details` | `false` | `--pedro-fetch-details` / `--no-pedro-fetch-details` |
| `rate_limit_delay` | `3.0` | `--pedro-rate-limit-delay` |

PEDro stays off until `acknowledge_fair_use` is true: [Sources, PEDro](./sources#pedro).

## Unpaywall

| Key | Flag |
|---|---|
| `unpaywall.email` | `--unpaywall-email` |

Unpaywall wants an e-mail address with each request and has no account. Without it, `get` and `--download` use only
the PDF links the sources return. mosaic also sends this address to OpenAlex, Crossref and the citation providers,
which serve identified clients faster.

## Zotero

| Key | Default | Flag |
|---|---|---|
| `zotero.api_key` | `""` | `--zotero-key` |
| `zotero.user_id` | `0` | set by `--zotero-key` |

With no key, `--zotero` talks to the Zotero desktop app on this computer. `--zotero-key` stores a web API key and
looks up your user ID at once. Details: [Zotero](./zotero).

## Obsidian

| Key | Default | Flag |
|---|---|---|
| `obsidian.vault_path` | `""` | `--obsidian-vault` |
| `obsidian.subfolder` | `papers` | `--obsidian-subfolder` |
| `obsidian.filename_pattern` | `{year}_{author}_{title}` | `--obsidian-filename-pattern` |
| `obsidian.tags` | `["paper"]` | `--obsidian-tag` (repeatable; replaces the list) |
| `obsidian.wikilinks` | `true` | `--obsidian-wikilinks` / `--no-obsidian-wikilinks` |

Details: [Obsidian](./obsidian).

## LLM

One model serves `--sort relevance`, `--summarise`, `compare`, `ask` and `chat`.

| Key | Default | Flag | Meaning |
|---|---|---|---|
| `llm.provider` | `""` | `--llm-provider` | `openai` (also any OpenAI-compatible server) or `anthropic` |
| `llm.api_key` | `""` | `--llm-api-key` | Key; any non-empty string for a local server |
| `llm.model` | `""` | `--llm-model` | Empty: `gpt-4o-mini` (openai) or `claude-haiku-4-5-20251001` (anthropic) |
| `llm.base_url` | `""` | `--llm-base-url` | OpenAI-compatible server, e.g. `http://localhost:11434/v1` for Ollama (`/v1` is added when missing) |
| `llm.timeout` | `0` | `--llm-timeout` | Seconds to wait for one answer; `0` keeps the built-in 2–3 minutes. Raise it for large local models |

mosaic uses the LLM only when both `provider` and `api_key` are set. A local Ollama server:

```bash
mosaic config --llm-provider openai --llm-base-url http://localhost:11434/v1 --llm-api-key ollama --llm-model qwen3:8b
```

## RAG

Settings for `mosaic index`, `ask`, `chat` and `search --semantic` ([Asking your library](./rag)).

| Key | Default | Flag | Meaning |
|---|---|---|---|
| `rag.embedding_model` | `""` | `--embedding-model` | Embedding model; required to index |
| `rag.embedding_base_url` | `""` | `--embedding-base-url` | Embedding server; empty: `llm.base_url`, or OpenAI |
| `rag.embedding_api_key` | `""` | `--embedding-api-key` | Empty: `llm.api_key` |
| `rag.embedding_provider` | `""` | edit the file | Not used: embeddings always go through the OpenAI embeddings API (cloud OpenAI, or the server at `embedding_base_url`) |
| `rag.top_k` | `10` | `--rag-top-k` | Papers retrieved per question |
| `rag.chunk_size` | `512` | edit the file | Tokens per text chunk (counted as 4 characters each) |
| `rag.chunk_overlap` | `50` | `--chunk-overlap` | Tokens shared by consecutive chunks |
| `rag.full_text_index` | `true` | `--full-text-index` / `--no-full-text-index` | Index the text of downloaded PDFs; needs `pymupdf` installed |
| `rag.auto_index` | `false` | `--rag-auto-index` / `--no-rag-auto-index` | Index new papers after every `search` and `get` |

Change the embedding model and the stored vectors no longer match: run `mosaic index --reindex`.

### Citation graph

| Key | Default | Meaning |
|---|---|---|
| `rag.citations.enabled` | `false` | Boost retrieval with citation links, and fetch them on every `mosaic index` |
| `rag.citations.boost_alpha` | `0.3` | Weight of the boost; 0 turns it off |
| `rag.citations.providers` | `["openalex", "crossref"]` | Where citation links come from, in order; `opencitations` also works |
| `rag.citations.expand_neighbors` | `false` | Add papers one citation away to the retrieved set |

These keys have no flags: edit the file.

```toml
[rag.citations]
enabled = true
boost_alpha = 0.3
```

Details: [Citation graph](./citation-graph).

See also: [tutorial: getting the PDFs](/tutorial/04-pdfs), [maintenance recipes](/cookbook/maintenance),
[`mosaic config`](/reference/config).
