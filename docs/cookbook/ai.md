---
title: Models and analysis
---

# Models and analysis

Recipes that use a language model or an embedding model: ranking, summaries, comparison tables, questions
answered from your papers, and the citation network.

[[toc]]

## A local model with Ollama

```bash
ollama pull qwen3:8b
mosaic config --llm-provider openai --llm-base-url http://localhost:11434/v1 \
              --llm-api-key ollama --llm-model qwen3:8b
```

`openai` here names the protocol: Ollama, LM Studio, llama.cpp and vLLM all speak the OpenAI API. The key can be
any non-empty string for a local server. The base URL works with or without the trailing `/v1`. One `[llm]`
setting serves `--sort relevance`, `--summarise`, `compare`, `ask` and `chat`.
Tutorial: [a local model](/tutorial/08-local-model); guide: [setting up the models](/guide/rag#setting-up-the-models).

## OpenAI or Anthropic in the cloud

```bash
mosaic config --llm-provider openai --llm-api-key sk-...                 # gpt-4o-mini by default
mosaic config --llm-provider anthropic --llm-api-key sk-ant-...          # a Claude Haiku model by default
mosaic config --llm-model gpt-4o                                         # another model
```

Without `--llm-base-url`, mosaic calls the provider's own endpoint. Titles and abstracts leave your machine; the
local setup above keeps them on it.

## A slow local model times out

```bash
mosaic config --llm-timeout 900
```

A large model on a consumer GPU can need minutes for one summary. `--llm-timeout` sets the seconds mosaic waits
for each answer (key `llm.timeout`; `0` keeps the built-in limits of two to three minutes).

## Rank results by relevance

```bash
mosaic search "hall thruster anomalous electron transport" --sort relevance
```

The **Rel.** column scores each paper from 0 to 1 against the query. Without an LLM, mosaic scores with BM25, a
keyword measure that needs no model and no network; with one configured, it asks the model. Guide:
[Relevance ranking](/guide/relevance-ranking).

## Rank your cache offline

```bash
mosaic search "electron transport" --cached --sort relevance
mosaic search "electron transport" --cached --sort relevance --output ranked.bib
```

The query must not be empty: with nothing to compare against, the papers keep their order. See
[ranking what you have already](/guide/relevance-ranking#ranking-your-local-library).

## A one-paragraph summary of the results

```bash
mosaic search "hall thruster anomalous electron transport" --source arxiv --max 6 --summarise
mosaic search "electron transport" --cached --summarise --json | jq -r .summary
```

`--summarise` (or `--summarize`) adds a paragraph below the table that cites papers by row number, `[3]`. Only
titles and abstracts go to the model. With `--json` the paragraph is the `summary` field. Guide:
[Summaries](/guide/relevance-ranking#summaries).

## A comparison table

```bash
mosaic compare --query "hall thruster" -n 10 --dimensions "method,dimensionality,key finding"
mosaic compare --from refs.bib --sort citations --output comparison.md
```

Papers come from the cache: those matching `--query`, those listed in a `.bib`/`.csv` file, or all of them. The
model fills one column per dimension from each abstract (default `method,dataset,metric,result`); without an LLM
only the metadata columns are filled. `--output` writes `.md`, `.csv` or `.json`. Guide:
[Comparing papers](/guide/compare).

## Embeddings for search by meaning

```bash
ollama pull qwen3-embedding:0.6b
mosaic config --embedding-model qwen3-embedding:0.6b \
              --embedding-base-url http://localhost:11434/v1 --embedding-api-key ollama
mosaic index
```

`mosaic index` embeds every cached paper not yet indexed; it needs the `rag` extra (`sqlite-vec`). Unset embedding
URL and key fall back to the `[llm]` ones. `--query` or `--from` index a subset; `--batch-size` sets the texts per
request (96). A server error is reported in one line, with the URL it called. Tutorial:
[asking your library](/tutorial/09-library); guide: [Local RAG](/guide/rag).

## Search by meaning

```bash
mosaic search "electrons crossing the magnetic field" --semantic
mosaic search "wall erosion" --semantic --downloaded-only --sort year
```

`--semantic` searches the vector index instead of the sources: a paper matches by meaning even without your words.
The **Sim.** column shows the similarity. `--downloaded-only` keeps the papers whose PDF is in the library.

## A question answered from your papers

```bash
mosaic ask "What causes anomalous electron transport in Hall thrusters?" --show-sources
mosaic ask "What is still unexplained?" --mode gaps --query "hall thruster" --output gaps.md
mosaic ask "Which codes and dimensionality?" --mode extract --from refs.bib -n 20
```

`ask` retrieves the closest indexed papers (`-n`, default `rag.top_k` = 10) and has the model answer from them
only, citing them. Modes: `synthesis` (default), `gaps`, `compare`, `extract`. `--year`, `--query` and `--from`
narrow the papers it may use; `--output` writes `.md` or `.json`.

## A conversation over your papers

```bash
mosaic chat --query "hall thruster"
```

Each question retrieves papers again; the last three exchanges go to the model as context. `--mode` sets the starting mode and `--from`
narrows the pool, as in `ask`.

## Index the full text of your PDFs

```bash
pipx inject mosaic-search pymupdf
mosaic index --reindex
```

With `pymupdf`, `mosaic index` splits the PDFs in the library into chunks and embeds them, so `ask` can quote the
methods section rather than the abstract. No extra installs `pymupdf`. Without it, `mosaic index` warns and indexes
title and abstract; `mosaic config --no-full-text-index` silences the warning.

## Rebuild the index after changing the embedding model

```bash
mosaic config --embedding-model nomic-embed-text
mosaic index --reindex
```

Vectors from two models cannot be compared; mosaic refuses to index with a new model until you pass `--reindex`,
which drops the index and embeds everything again.

## The citation graph and its hubs

```bash
mosaic index --enrich-citations
mosaic network --top 10
mosaic network --query "hall thruster" --depth 2 --cluster --output graph.json
```

`--enrich-citations` fetches who-cites-whom among your cached papers from OpenAlex and Crossref. It builds the
graph even when the embedding step fails, so `network` needs no embedding model. `network` ranks the most connected
papers; `--query` and `--depth` start from a subset and follow citations; `--cluster` groups them (Louvain with the
`analysis` extra, connected components without); `--output` writes `.json` (D3, Gephi), `.gv` (Graphviz) or `.md`
(Mermaid). Tutorial: [the citation network](/tutorial/10-citations); guides: [Citation graph](/guide/citation-graph),
[Citation network](/guide/network).
