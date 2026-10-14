---
pageClass: tutorial-page
aside: false
title: 9. Asking your library
---

# 9. Asking your library

A summary covers one search. To ask questions across everything you have collected, mosaic builds a vector index:
each paper becomes one or more embeddings, lists of numbers that place texts of similar meaning close together. A
question is embedded the same way, the closest papers are retrieved, and the model answers from them, citing them.
This is retrieval-augmented generation (RAG), and here it runs on your machine.

It needs the `rag` extra (sqlite-vec) and an embedding model next to the chat model of
[chapter 8](./08-local-model):

```bash
ollama pull qwen3-embedding:0.6b
mosaic config --embedding-model qwen3-embedding:0.6b \
              --embedding-base-url http://localhost:11434/v1 --embedding-api-key ollama
```

## Building the index

<<< @/examples/output/09/index.txt{console}

`mosaic index` embeds every cached paper not indexed yet; run it again after new searches and it adds only the new
ones (`mosaic config --rag-auto-index` does that after every search). With PyMuPDF installed
([Installation](/guide/installation#extras)), papers whose PDF is in the library are indexed by their full text, in
overlapping chunks; the others by title and abstract, as here. After changing the embedding model, rebuild with
`mosaic index --reindex`: the vectors of two models do not mix.

## Searching by meaning

<<< @/examples/output/09/semantic.txt{console}

`--semantic` ranks the indexed papers by the meaning of the query, so a paper can rank high without sharing its
words. **Sim.** is the similarity of each paper's closest chunk. `--downloaded-only` keeps the papers whose PDF is
in your library.

## Asking a question

<<< @/examples/output/09/ask.txt{console}

`mosaic ask` retrieves the ten papers closest to the question (`-n` changes it), sends their best-matching text to
the model, and prints the answer with `[n]` citations; `--show-sources` lists the papers first. Four modes shape
the answer:

| `--mode` | Answer |
|---|---|
| `synthesis` (default) | the state of the art on the question |
| `gaps` | open problems, contradictions, missing evidence |
| `compare` | methods, data and results side by side |
| `extract` | one structured entry per paper: task, method, dataset, metric, result |

`--query`, `--from refs.bib` and `--year` restrict the papers it may use; `--output answer.md` (or `.json`) saves
the answer with its sources.

## A conversation

```bash
mosaic chat
```

`mosaic chat` keeps asking: each question retrieves its own papers, and the last exchanges go back to the model
as context. Inside, `/mode gaps` switches the mode, `/sources` lists the papers behind the last answer, `/clear`
forgets the conversation and `/quit` ends it.

::: tip What you learned
Embedding settings, `mosaic index`, `search --semantic`, `mosaic ask` and its modes, `mosaic chat`. Guide:
[Local RAG](/guide/rag); reference: [`index`](/reference/index-command), [`ask`](/reference/ask),
[`chat`](/reference/chat).
:::

Next: [10. The citation network](./10-citations).
