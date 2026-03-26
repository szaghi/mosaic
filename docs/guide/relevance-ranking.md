---
title: Relevance Ranking
---

# Relevance Ranking

By default, MOSAIC returns results in the order each source API provides them —
roughly its own notion of relevance, often biased toward recency or citation
count.  **Relevance ranking** re-scores every paper against your original query
after all sources have been merged, and re-orders the list so the most
on-topic papers appear first.

```bash
mosaic search "transformer attention mechanism" --sort relevance
```

The results table gains a **Rel.** column (0.00 – 1.00) showing each paper's
normalised relevance score.  The top-scoring paper always shows 1.00:

```
 #   Title                               Authors          Year   …   Rel.
 1   Attention Is All You Need           Vaswani et al.   2017   …   1.00
 2   Self-Attention with Relative…       Shaw et al.      2018   …   0.87
 3   Efficient Transformers: A Survey    Tay et al.       2020   …   0.74
 4   Universal Transformers             Dehghani et al.  2018   …   0.71
 …
```

Relevance ranking also works with `mosaic similar` — scores are computed against
the seed paper's title:

```bash
mosaic similar 10.48550/arXiv.1706.03762 --sort relevance
```

---

## How it works

Relevance scoring is a two-step process applied **after** all search results have
been fetched and deduplicated:

1. For each paper, the scorer receives the paper's **title + abstract** as a
   single text document.
2. It computes a similarity score between that document and the **original query
   string**.
3. Scores are normalised so the highest-scoring paper receives 1.00; all others
   are scaled proportionally.
4. Papers are sorted descending by score before display.

Papers with no abstract use only their title; papers with neither title nor
abstract receive a score of 0.00 and sink to the bottom.

---

## Scoring backends

MOSAIC ships two interchangeable backends.  The active backend is chosen
automatically at runtime based on your configuration.

### BM25 (default — no setup required)

[BM25Plus](https://en.wikipedia.org/wiki/Okapi_BM25) is a classical
information-retrieval algorithm.  It is:

- **Fast** — runs locally in milliseconds on any machine
- **Zero cost** — no API calls, no model downloads
- **Always available** — active whenever `--sort relevance` is passed, even with
  no LLM configured

BM25 tokenises query and document by whitespace, then computes a weighted
term-frequency/inverse-document-frequency score.  It rewards documents that
contain many query tokens and penalises very long documents that dilute term
density.  Quality is good for keyword-rich queries; it degrades gracefully on
short or highly technical abstracts with non-standard vocabulary.

### LLM (opt-in — higher quality)

When an LLM is configured (see [LLM configuration](#llm-configuration) below),
MOSAIC sends each batch of up to 20 paper snippets to the model with a prompt
asking for a JSON array of relevance floats.  The model reads the full query
and each title + first 300 characters of the abstract, then rates conceptual
relevance — including synonyms, paraphrases, and domain context that BM25
misses.

LLM scoring:

- Understands semantic equivalences ("neural machine translation" ≈ "seq2seq
  with attention")
- Handles multi-concept queries ("protein structure *and* AlphaFold")
- Ranks by topical fit rather than mere keyword overlap
- Falls back to BM25 automatically if the API call fails

---

## LLM configuration

All LLM settings live under the `[llm]` section of
`~/.config/mosaic/config.toml`.

```toml
[llm]
# LLM provider — "openai", "anthropic", or leave empty to use BM25 only
provider  = ""

# API key for the chosen provider, or any non-empty string for local servers
api_key   = ""

# Model name.  Leave empty to use the built-in default for the provider:
#   openai    → gpt-4o-mini
#   anthropic → claude-haiku-4-5-20251001
model     = ""

# Base URL for a local or custom OpenAI-compatible server.
# Leave empty to use the official provider endpoint.
# Examples:
#   Ollama        → http://localhost:11434/v1
#   LM Studio     → http://localhost:1234/v1
#   llama.cpp     → http://localhost:8080/v1
base_url  = ""
```

Use the dedicated CLI flags to write individual keys without touching the file:

```bash
mosaic config --llm-provider openai --llm-api-key sk-... --llm-model gpt-4o-mini
```

---

## Setup guides

### Cloud OpenAI

```bash
mosaic config --llm-provider openai \
              --llm-api-key sk-YOUR_OPENAI_KEY \
              --llm-model gpt-4o-mini
```

Recommended model: **`gpt-4o-mini`** — fast, cheap, and accurate enough for
relevance scoring.  `gpt-4o` gives marginally better ordering at higher cost.

### Cloud Anthropic (Claude)

```bash
mosaic config --llm-provider anthropic \
              --llm-api-key sk-ant-YOUR_ANTHROPIC_KEY \
              --llm-model claude-haiku-4-5-20251001
```

`claude-haiku-4-5-20251001` is the recommended model: lowest latency,
lowest cost, sufficient reasoning ability for relevance judgements.

### Ollama (local, recommended for local LLMs)

[Ollama](https://ollama.com) runs open-weight models on your machine and
exposes an OpenAI-compatible API at `http://localhost:11434/v1`.

**Step 1 — install Ollama** (visit [ollama.com](https://ollama.com) for
platform-specific instructions, or on Linux/macOS):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Step 2 — pull a model:**

```bash
ollama pull llama3.2        # 2 GB — good quality/speed balance
ollama pull gemma3:4b       # 3 GB — strong instruction following
ollama pull mistral         # 4 GB — excellent for structured output
```

**Step 3 — configure MOSAIC:**

```bash
mosaic config --llm-provider openai \
              --llm-base-url http://localhost:11434/v1 \
              --llm-api-key ollama \
              --llm-model llama3.2
```

::: tip Provider and base-url
Use `--llm-provider openai` for any OpenAI-compatible local server.
The `--llm-api-key` value is sent in the `Authorization: Bearer` header but
ignored by local servers — any non-empty string works.
:::

**Step 4 — verify:**

```bash
mosaic search "attention transformer" --sort relevance --source arxiv -n 5
```

The `Rel.` column should appear with values between 0 and 1.

### LM Studio

[LM Studio](https://lmstudio.ai) provides a GUI for running local models and
includes a built-in OpenAI-compatible server.

1. Download and install LM Studio from [lmstudio.ai](https://lmstudio.ai)
2. Load a model (e.g. `Llama-3.2-3B-Instruct`)
3. Start the local server: click **Local Server** in the left sidebar, then
   **Start Server**
4. Note the port shown (default: `1234`)

```bash
mosaic config --llm-provider openai \
              --llm-base-url http://localhost:1234/v1 \
              --llm-api-key lmstudio \
              --llm-model lmstudio-community/Llama-3.2-3B-Instruct-GGUF
```

The model name must match exactly what LM Studio shows in its API tab.

### llama.cpp server

If you run the [llama.cpp HTTP server](https://github.com/ggerganov/llama.cpp/tree/master/examples/server)
directly:

```bash
# Start the server (example — adjust path and model as needed)
./llama-server -m ~/models/mistral-7b-instruct.Q4_K_M.gguf --port 8080

# Configure MOSAIC
mosaic config --llm-provider openai \
              --llm-base-url http://localhost:8080/v1 \
              --llm-api-key none \
              --llm-model mistral
```

### LocalAI / OpenAI-compatible proxies

Any server that implements the `/v1/chat/completions` OpenAI endpoint works:

```bash
mosaic config --llm-provider openai \
              --llm-base-url http://YOUR_SERVER/v1 \
              --llm-api-key YOUR_KEY_OR_ANY_STRING \
              --llm-model YOUR_MODEL_NAME
```

---

## Choosing a model

| Use case | Recommended choice |
|----------|-------------------|
| Privacy-first, no internet | Ollama + `llama3.2` or `mistral` |
| Best local quality | Ollama + `gemma3:12b` or `mistral-small` |
| Cloud — cheapest | OpenAI `gpt-4o-mini` |
| Cloud — best quality | OpenAI `gpt-4o` or Anthropic `claude-sonnet-4-6` |
| No LLM / offline always | BM25 (default, no config needed) |

::: tip Short queries benefit most from LLM scoring
BM25 works well for long, keyword-rich queries.  For short or conceptual
queries (e.g. `"protein misfolding diseases"`, `"few-shot learning vision"`),
LLM scoring gives noticeably better top-10 precision.
:::

---

## Ranking your local library

`--sort relevance` works on your **local cache** just as well as on live search
results — with no network requests at all.  This is the fastest way to sift a
bibliography you have already collected.

### Basic offline re-ranking

```bash
mosaic search "attention mechanism" --cached --sort relevance
```

MOSAIC queries the local SQLite cache (full-text search on title + abstract),
then re-scores the matching papers against the query and shows the ranked table
with a `Rel.` column.  No source APIs are called, no API keys are needed.

### Ranking a .bib or .csv bibliography file

If your bibliography lives in a file rather than the cache, load it first with
`mosaic get --from`, then run the offline re-rank:

```bash
# Step 1 — pull all DOIs from the file into the local cache
mosaic get --from refs.bib        # BibTeX
mosaic get --from references.csv  # CSV with a 'doi' column

# Step 2 — rank against any query, instantly, no network
mosaic search "transformer attention" --cached --sort relevance
```

Any subsequent query against the same cache is also instant — the papers are
already there.

### Ranking all cached papers against a query

`--cached` pre-filters results using SQLite full-text search, so only papers
whose title or abstract contain at least one query keyword are scored.  If your
bibliography uses different terminology than your query, widen the net by
passing an empty query — every paper in the cache becomes a candidate:

```bash
mosaic search "" --cached --sort relevance
```

::: tip Use LLM scoring for broad queries
An empty or very short query gives BM25 little signal to work with.  With an
LLM configured, the model can still judge conceptual relevance from each
abstract, which makes empty-query ranking much more useful.
:::

### Combining filters with offline re-ranking

All standard filters and output flags compose with `--cached --sort relevance`:

```bash
# Open-access papers from the last 3 years, relevance-ranked
mosaic search "protein folding" --cached --sort relevance -y 2022-2024 --oa-only

# Export the re-ranked bibliography to BibTeX
mosaic search "graph neural networks" --cached --sort relevance --output ranked.bib

# Re-rank and push top results to Zotero
mosaic search "CRISPR off-target" --cached --sort relevance -n 20 --zotero
```

---

## Combining with other options

`--sort relevance` composes with all the usual search flags:

```bash
# Relevance-ranked, open-access only
mosaic search "diffusion models image generation" --sort relevance --oa-only

# Relevance-ranked, year filter, limited to arXiv
mosaic search "CRISPR off-target effects" --sort relevance -y 2021-2024 --source arxiv

# Relevance-ranked and exported to BibTeX
mosaic search "graph neural network drug discovery" --sort relevance --output refs.bib

# Relevance-ranked with Zotero export
mosaic search "protein structure prediction" --sort relevance -n 30 --zotero

# Relevance-ranked similar papers
mosaic similar arxiv:1706.03762 --sort relevance -n 20
```

---

## Fallback behaviour

If LLM scoring is configured but the API call fails (network error, bad key,
model unavailable, JSON parse error), MOSAIC:

1. Logs a warning: `LLM scoring failed (...) — falling back to BM25`
2. Runs BM25 scoring instead
3. Returns results normally — no search is aborted

To see the warning, add `--verbose` before the subcommand:

```bash
mosaic --verbose search "attention mechanism" --sort relevance
```

---

## Notes and limitations

- **Scores are query-relative.** A score of 0.87 means "87% as relevant as the
  most-on-topic paper found for this query" — not an absolute relevance measure.
  Scores from different queries are not comparable.
- **Scores are not cached.** They are computed fresh for every search run and
  are not persisted to the local database.
- **BM25 is case-insensitive and whitespace-tokenised.** Hyphenated terms
  (`self-attention`) and acronyms (`NLP`) are treated as separate tokens.
  For better BM25 coverage, expand acronyms in your query
  (`natural language processing NLP`).
- **LLM token limits.** Each abstract is truncated to 300 characters before
  being sent to the LLM.  Full abstracts are never transmitted.  Batches are
  capped at 20 papers per API call.
- **Local model quality varies.** Very small models (< 1 B parameters) may
  return malformed JSON or nonsensical scores.  If that happens, MOSAIC falls
  back to BM25.  Try a larger model (`7b`+) for reliable structured output.
