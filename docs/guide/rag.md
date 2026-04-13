---
title: RAG & Literature Analysis
---

# RAG & Literature Analysis

MOSAIC includes a fully local Retrieval-Augmented Generation (RAG) pipeline that turns your cached paper library into an interactive knowledge base. Think of it as a **local NotebookLM alternative** — no data leaves your machine unless you use a cloud LLM or embedding provider.

Three commands power the pipeline:

| Command | Purpose |
|---------|---------|
| `mosaic index` | Embed all cached papers and store vectors in the local SQLite database |
| `mosaic ask` | Ask a single question and get a structured answer with citations |
| `mosaic chat` | Start an interactive multi-turn conversation over your library |

## How it works

1. **Index**: each paper's title and abstract are concatenated and embedded using your chosen model. Vectors are stored in a `vec0` virtual table inside the same SQLite cache file — no extra infrastructure needed.
2. **Retrieve**: at query time, the query is embedded with the same model and the top-*k* most similar papers are returned using cosine distance.
3. **Generate**: the retrieved papers are injected as context into a structured prompt sent to your configured LLM. Four prompt modes are available: `synthesis`, `gaps`, `compare`, and `extract`.

## Installation

The vector storage extension (`sqlite-vec`) must be injected into your environment:

```bash
pipx inject mosaic-search sqlite-vec
```

If you installed with `pip` instead of `pipx`:

```bash
pip install 'mosaic-search[rag]'
```

::: tip Verify the installation
Run `mosaic index` on an empty library — if sqlite-vec is missing you will see a clear error message pointing to the command above.
:::

## Choosing an embedding model

The embedding model converts text into vectors. The right choice depends on your setup:

| Setup | Recommended model | Notes |
|-------|------------------|-------|
| Local (Ollama) | `snowflake-arctic-embed2` | High quality, ~568 M params, runs on CPU |
| Local (Ollama) | `nomic-embed-text` | Lighter alternative (~137 M params) |
| Cloud (OpenAI) | `text-embedding-3-small` | Fast, cheap, good quality |
| Cloud (OpenAI) | `text-embedding-3-large` | Higher quality, higher cost |

::: warning Model consistency
Once you index papers with a specific model, you **must** use the same model for all future queries and indexing. Changing the model without running `mosaic index --reindex` will cause a `ValueError`. MOSAIC stores the model name in the database and validates it on every run.
:::

For the latest benchmarks, see the [MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard). The [Ollama model library](https://ollama.com/library) lists all locally available models.

## Local setup with Ollama (recommended)

Ollama is the easiest way to run embedding and generation models locally.

**1. Install Ollama**: follow instructions at [ollama.com](https://ollama.com).

**2. Pull models:**

```bash
# Embedding model
ollama pull snowflake-arctic-embed2

# Generation model (for mosaic ask / mosaic chat)
ollama pull llama3.2
```

**3. Configure MOSAIC:**

```bash
# Embedding model — use the Ollama OpenAI-compatible API
mosaic config \
  --embedding-model snowflake-arctic-embed2 \
  --embedding-base-url http://localhost:11434/v1 \
  --embedding-api-key ollama

# LLM for generation (if not already set)
mosaic config \
  --llm-provider openai \
  --llm-base-url http://localhost:11434/v1 \
  --llm-api-key ollama \
  --llm-model llama3.2
```

::: tip Single server for both
When the embedding server is the same as the LLM server (e.g. both are Ollama on `localhost:11434`), you can omit `--embedding-base-url` and `--embedding-api-key`. MOSAIC will fall back to `llm.base_url` and `llm.api_key` automatically.
:::

## Cloud setup with OpenAI

```bash
# Embedding model
mosaic config \
  --embedding-model text-embedding-3-small \
  --embedding-api-key sk-...

# LLM (if not already set)
mosaic config \
  --llm-provider openai \
  --llm-api-key sk-... \
  --llm-model gpt-4o-mini
```

## Configuration reference

The `[rag]` section in `~/.config/mosaic/config.toml`:

```toml
[rag]
# Embedding model name — required for mosaic index / ask / chat
embedding_model = "snowflake-arctic-embed2"

# Base URL for the embedding server.
# Leave empty to use the official OpenAI API endpoint.
# When empty, inherits llm.base_url if set.
# Examples:
#   Ollama     → http://localhost:11434/v1
#   LM Studio  → http://localhost:1234/v1
embedding_base_url = "http://localhost:11434/v1"

# API key for the embedding server.
# Any non-empty string works for local servers (e.g. "ollama").
# When empty, inherits llm.api_key if set.
embedding_api_key = "ollama"

# Provider string — leave empty to inherit from [llm].
# Set explicitly only if your embedding and generation servers differ.
embedding_provider = ""

# Number of papers retrieved per RAG query (default: 10)
top_k = 10

# Max characters per text chunk — reserved for future full-PDF mode
chunk_size = 512

# Silently index new papers after each search / get run
auto_index = false
```

## `mosaic index` command

Build or update the vector index.

```
mosaic index [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--reindex` | flag | off | Re-embed all papers, even already-indexed ones. Required after changing the embedding model. |
| `--query` / `-q` | str | | Embed only papers matching this cache query |
| `--from` | path | | Embed only papers listed in a `.bib` or `.csv` file |
| `--batch-size` | int | `96` | Texts sent per embedding API call |

Without `--query` or `--from`, all papers in the cache are indexed. Already-indexed papers are skipped automatically.

**Examples:**

```bash
# Index all cached papers
mosaic index

# Re-embed everything after switching to a new model
mosaic index --reindex

# Index only papers matching a topic
mosaic index --query "transformer attention"

# Index papers from a BibTeX file
mosaic index --from refs.bib
```

![Index demo](/gifs/15_rag_index.gif)

## `mosaic ask` command

Ask a question about your indexed papers.

```
mosaic ask [OPTIONS] QUESTION
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--mode` | | str | `synthesis` | Prompt mode: `synthesis`, `gaps`, `compare`, `extract` |
| `--query` / `-q` | `-q` | str | | Pre-filter: restrict retrieval to papers matching this query |
| `--from` | | path | | Pre-filter: restrict retrieval to papers from a `.bib`/`.csv` |
| `--year` / `-y` | `-y` | str | | Year filter (e.g. `2020-2024`) |
| `--top` / `-n` | `-n` | int | config | Override `rag.top_k` for this query |
| `--output` / `-o` | `-o` | path | | Save answer to `.md` or `.json` file |
| `--show-sources` | | flag | off | Print retrieved papers before the answer |

### Prompt modes

| Mode | What it produces |
|------|-----------------|
| `synthesis` | Comprehensive state-of-the-art summary with citations |
| `gaps` | Open problems, contradictions, and methodological limitations |
| `compare` | Structured comparison of methods, datasets, metrics, and results |
| `extract` | Per-paper structured extraction: Task, Method, Dataset, Metric, Key Result |

**Examples:**

```bash
# Default synthesis
mosaic ask "What are the main approaches to neural machine translation?"

# Gap analysis
mosaic ask "What open problems remain in protein structure prediction?" --mode gaps

# Compare methods
mosaic ask "transformer vs. LSTM for sequence modelling" --mode compare

# Extract structured info
mosaic ask "summarise each paper" --mode extract

# Narrow retrieval to recent papers
mosaic ask "diffusion model scaling" --year 2023-2025

# Restrict to a specific topic already in cache
mosaic ask "RLHF alignment" -q "reinforcement learning human feedback"

# Retrieve more papers for a broad question
mosaic ask "survey of graph neural networks" -n 25

# Save the answer to Markdown
mosaic ask "transformer architectures" --output analysis.md

# Save as JSON (structured, for scripting)
mosaic ask "CRISPR therapeutic applications" --output crispr.json

# Show retrieved papers before the answer
mosaic ask "attention mechanism variants" --show-sources
```

![Ask demo](/gifs/16_rag_ask.gif)

## `mosaic chat` command

Start an interactive multi-turn RAG session.

```
mosaic chat [OPTIONS]
```

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--query` / `-q` | `-q` | str | | Narrow retrieval to papers matching this query |
| `--from` | | path | | Narrow retrieval to papers from a `.bib`/`.csv` |
| `--mode` | | str | `synthesis` | Default prompt mode for the session |

Once inside the session, type your question and press Enter. Special commands:

| Command | Effect |
|---------|--------|
| `/mode synthesis` | Switch prompt mode (also: `gaps`, `compare`, `extract`) |
| `/sources` | Show the papers that would be retrieved for the current pool |
| `/clear` | Clear conversation history (papers are re-retrieved fresh) |
| `/quit` | Exit the chat |

**Examples:**

```bash
# Start a general chat
mosaic chat

# Focus on a subset of papers
mosaic chat -q "protein folding"

# Start in gaps mode
mosaic chat --mode gaps

# Focus on papers from a BibTeX bibliography
mosaic chat --from refs.bib
```

![Chat demo](/gifs/17_rag_chat.gif)

## Typical workflow

```bash
# 1. Build your corpus with normal searches
mosaic search "diffusion model image generation" -n 50
mosaic search "score-based generative models" -n 50 --source arxiv

# 2. Index everything (once)
mosaic index

# 3. Ask questions
mosaic ask "What training objectives do diffusion models use?" --show-sources

# 4. Explore interactively
mosaic chat

# 5. Export a report
mosaic ask "Compare DDPM, DDIM, and score SDE approaches" \
  --mode compare --output diffusion_comparison.md
```

## Semantic search — `mosaic search --semantic`

Once papers are indexed, you can search the vector index directly and get a ranked
list of papers — without generating a natural-language answer. This is useful when you
want to **explore** the library rather than synthesise it.

```bash
# Retrieve by meaning, not keyword overlap
mosaic search "self-supervised contrastive learning" --semantic

# Limit to papers you have on disk
mosaic search "attention mechanism" --semantic --downloaded-only

# More results, sorted by citation count after semantic retrieval
mosaic search "diffusion generative model" --semantic -n 30 --sort citations
```

The results table shows a **Sim.** column (0 – 1) — a normalised cosine similarity score.
The same embedding model used by `mosaic index` is used to embed the query at search time.

::: tip When to use `--semantic` vs `mosaic ask`
- `--semantic` returns a ranked **paper list** — fast, no LLM needed at query time.
- `mosaic ask` retrieves papers and then **synthesises an answer** — requires an LLM.

Use `--semantic` to explore and curate; use `mosaic ask` to analyse and summarise.
:::

---

## Hands-free corpus growth with `auto_index`

Set `auto_index = true` in `[rag]` (or via `mosaic config --rag-auto-index`) to silently embed new papers after every `mosaic search` or `mosaic get` run. Indexing failures are always silent and never block the main operation.

```bash
mosaic config --rag-auto-index
```

After that, every search automatically extends the vector index:

```bash
mosaic search "vision transformers" -n 30   # papers indexed silently
mosaic ask "What makes ViT different from ResNets?"  # ready to use
```

## Offline usage

Once papers are indexed, `mosaic ask` and `mosaic chat` only need the **LLM** at query time — not the embedding model. If you are offline and running a local LLM (e.g. via Ollama), the entire pipeline works without internet access.

The embedding model is only needed when:
- Running `mosaic index` (or `mosaic index --reindex`)
- Using `auto_index = true`

## Citation graph

The vector index can be augmented with a **citation graph** that boosts papers
sharing bibliographic edges with other retrieved results. The graph is built
from OpenAlex (primary) and CrossRef (fallback), requires no LLM, and is
stored as a lightweight edge table in the same SQLite cache.

```bash
# Enrich after indexing
mosaic index --enrich-citations
```

To enable boosting, add the following to `~/.config/mosaic/config.toml`:

```toml
[rag.citations]
enabled = true
```

Citation boosting re-ranks retrieved papers using a combined score:

```
score = (1 / rank) × (1 + α × citation_links_in_result_set)
```

The default `boost_alpha = 0.3` gives a modest nudge; tune it up for tightly
scoped corpora where citation relationships are highly informative.

See [Citation Graph](./citation-graph) for the full reference.

## Notes and limitations (v1)

- **Abstracts only**: indexing uses title + abstract. Full-PDF chunking is reserved for a future release (`chunk_size` is already in the config for forward compatibility).
- **Model consistency**: the embedding model is stored in the database. Changing it requires `mosaic index --reindex` to rebuild all vectors.
- **No incremental updates to changed abstracts**: if a paper's abstract is enriched after initial indexing (e.g. via `mosaic cache enrich`), re-run `mosaic index` to pick up the change.
- **sqlite-vec required**: install with `pipx inject mosaic-search sqlite-vec`. The rest of MOSAIC works without it.
