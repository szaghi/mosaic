---
pageClass: tutorial-page
aside: false
title: 8. A local model
---

# 8. A local model

The library now holds over a hundred papers, more than you will read. A language model can order them, summarise
them and lay them side by side. This chapter runs one on the same machine with [Ollama](https://ollama.com); a
cloud API works the same way.

## Ranking without a model

<<< @/examples/output/08/bm25.txt{console}

`--sort relevance` scores every result against the query and adds the **Rel.** column, normalised so the best
paper scores 1.00. With no model configured the score is BM25, word statistics over titles and abstracts computed
on your machine in milliseconds. It rewards the query's words, not their meaning.

## Configuring a model

```bash
ollama pull qwen3.8:27b        # any chat model you have; this one has 27 billion parameters
mosaic config --llm-provider openai --llm-base-url http://localhost:11434/v1 \
              --llm-api-key ollama --llm-model qwen3.8:27b --llm-timeout 900
```

- `--llm-provider openai` with a `--llm-base-url` means "an OpenAI-compatible server": Ollama, LM Studio,
  llama.cpp, vLLM. The key can be any word; Ollama ignores it.
- For the cloud, leave out the base URL and give a real key: `--llm-provider openai --llm-api-key sk-...`, or
  `--llm-provider anthropic --llm-api-key sk-ant-...`. Without `--llm-model`, mosaic uses a small model of that
  provider.
- `--llm-timeout` is how many seconds mosaic waits for one answer. A large model on a desktop GPU can need
  minutes when it reasons before answering; without the option, mosaic waits two to three minutes.

With a model configured, `--sort relevance` asks it to score the papers, 20 at a time, and falls back to BM25 if
the model fails.

## A summary of the results

<<< @/examples/output/08/summarise.txt{console}

`--summarise` (or `--summarize`) sends the titles and abstracts of the first 40 results, never the PDFs, and asks
for one paragraph that cites the rows as `[n]`. The model is told to use nothing but the abstracts; check any
claim that matters against the paper. With `--json`, the paragraph is in the `summary` field.

## A comparison table

<<< @/examples/output/08/compare.txt{console}

`mosaic compare` takes papers from the cache (`--query`, `--from refs.bib`, or the whole cache) and asks the model
to fill one column per `--dimensions` entry from each abstract; the default columns are method, dataset, metric
and result. `--output table.md` (or `.csv`, `.json`) writes the table to a file. Without a model, only metadata
columns such as year and journal get values, and mosaic says so.

::: tip What you learned
BM25 ranking with no model; one `mosaic config` for a local or cloud model; `--sort relevance` with the model,
`--summarise`, `mosaic compare`. Guides: [Relevance ranking](/guide/relevance-ranking),
[Comparing papers](/guide/compare), [Local RAG](/guide/rag#setting-up-the-models) for model setups.
:::

Next: [9. Asking your library](./09-library).
