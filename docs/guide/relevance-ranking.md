---
title: Relevance Ranking and Summaries
---

# Relevance ranking and summaries

Sources return results in their own order, and mosaic lists them source by source. `--sort relevance` re-scores
the merged list against your query and puts the most on-topic papers first; `--summarise` adds a one-paragraph
synthesis of the list. Both work on live results, on the cache (`--cached`) and on `mosaic similar`.

## Usage

```bash
mosaic search "hall thruster anomalous transport" --sort relevance          # live results, ranked
mosaic search "electron transport" --cached --sort relevance                # your cache, ranked, offline
mosaic similar 10.1063/1.4972269 --sort relevance                           # ranked against the seed's title
mosaic search "hall thruster anomalous transport" --max 6 --summarise       # a paragraph under the table
```

With `--sort relevance` the table gains a `Rel.` column: the score divided by the best score of the list, so the
first paper shows 1.00. Scores compare papers within one list only, are computed on every run, and are not stored.

## How scores are computed

Two scorers, chosen by your configuration:

- **BM25** (BM25Plus, from `rank-bm25`) when no language model is configured. It needs nothing else and runs
  offline. Query and documents (title and abstract) are lower-cased and split on whitespace, so it matches words as
  written: `self-attention` is one token, `NLP` does not match "natural language processing".
- **The language model** of `[llm]` when one is configured (see [setting up the models](./rag#setting-up-the-models)).
  mosaic sends the query and batches of 20 papers (title and the first 300 characters of the abstract) and asks for a
  JSON list of scores between 0 and 1. It understands synonyms and paraphrases, at the cost of one request per 20
  papers. If a request fails or the reply is not JSON, mosaic logs a warning (shown with `mosaic --verbose`) and falls
  back to BM25 for the whole list.

Papers without an abstract are scored on their title. Small local models (under about 7B parameters) often answer
with malformed JSON; mosaic then falls back to BM25.

## Ranking what you have already {#ranking-your-local-library}

`--cached` searches the local cache with no network requests: it keeps the papers whose title or abstract contains
every word of the query, then `--sort relevance` orders them.

```bash
mosaic get --from refs.bib                                        # put a bibliography in the cache
mosaic search "hall thruster wall erosion" --cached --sort relevance
mosaic search "hall thruster" --cached --sort relevance -y 2018-2025 --oa-only --output ranked.bib
```

An empty query (`mosaic search "" --cached`) lists the whole cache, but leaves nothing to rank against: give the
words you care about.

## Relevance and semantic search

`--semantic` is a different tool: it searches the vector index built by [`mosaic index`](./rag) for the papers
closest in meaning to the query, and shows a `Sim.` column (1 / (1 + distance)). It finds papers that share none of
your words; `--sort relevance` only re-orders a list you already have.

| | `--sort relevance` | `--semantic` |
|---|---|---|
| Ranks | the live results, or the cached papers matching every word | the whole vector index |
| Needs | nothing (BM25), or `[llm]` | `mosaic index` and an embedding model |
| Column | `Rel.` | `Sim.` |

With `--semantic`, `--sort relevance` is ignored (the list is already ordered by similarity); `--sort citations` and
`--sort year` re-order it. `--downloaded-only` restricts `--semantic` and `--cached` to papers with a PDF in the library.

## Summaries

`--summarise` (or `--summarize`) asks the language model of `[llm]` for one paragraph of at most 150 words on the
results: the main themes and methods and how they evolved, citing papers as `[n]`, where n is the row number in
the table above it.

```bash
mosaic search "hall thruster anomalous electron transport" --source arxiv --max 6 --summarise
mosaic search "hall thruster" --cached --sort year --summarise
mosaic search "hall thruster" --cached --json --summarise | jq -r .summary
```

- The model receives the titles and abstracts of the first 40 results, each abstract cut at 1000 characters, and is
  told to use nothing else. Check any claim that matters against the paper.
- It needs no index, unlike [`mosaic ask`](./rag), which answers a question from the papers of your library.
- With `--json`, the paragraph is in the `summary` field (`null` when there is none), and `[n]` is the n-th entry
  of `papers`.
- With no language model configured, a failed request, or no abstract among the results, the table is shown as
  usual and one line says why there is no summary.

See also: [tutorial chapter 8](/tutorial/08-local-model), [recipes](/cookbook/ai), [`mosaic search`](/reference/search).
