---
title: Asking Your Library
---

# Asking your library

`mosaic index` turns the papers in your cache into a vector index; `mosaic ask` answers a question from the papers
closest to it, citing them as `[n]`; `mosaic chat` does the same in a conversation; `mosaic search --semantic` lists
the closest papers without an answer. Everything runs against your local cache: the only data that leaves your machine
is what you send to the embedding and language models you configure, and with a local server nothing does.

## Usage

```bash
mosaic index                                        # embed every cached paper not indexed yet
mosaic index --query "hall thruster"                # only the cached papers matching every word
mosaic index --from refs.bib                        # only the papers of a .bib or .csv file
mosaic index --reindex                              # rebuild everything (after changing embedding model)

mosaic search "electrons crossing the magnetic field" --semantic       # closest papers, no answer
mosaic ask "What causes anomalous electron transport?" --show-sources  # an answer with [n] citations
mosaic ask "What is still unexplained?" --mode gaps --year 2018-2025
mosaic ask "Compare the PIC codes used" --mode compare --output pic.md
mosaic chat -q "hall thruster"                      # a conversation over a subset of the library
```

`mosaic ask` takes four modes, which change the instructions given to the model:

| Mode | Asks the model for |
|---|---|
| `synthesis` (default) | the state of the art on the question: approaches, findings, consensus, disagreements |
| `gaps` | open problems, contradictions and methodological limits, each with evidence from the papers |
| `compare` | methods, datasets, metrics, results and trade-offs side by side, with a table where it fits |
| `extract` | one entry per paper: task, method, dataset, metric, key result (`–` when absent) |

The answer is printed as Markdown, followed by the numbered references. `--show-sources` lists the retrieved papers
before the answer, `--top N` (`-n`) retrieves N papers instead of `rag.top_k`, and `--output` saves the answer:
a `.json` file holds the question, mode, answer and papers, any other name gets Markdown.

`--query`, `--from` and `--year` restrict which papers can be retrieved. `--query` keeps the cached papers whose
title or abstract contains every word; `--year` applies to those, or to the whole cache when it is the only filter.

In `mosaic chat`, every question retrieves its own papers, and the last three exchanges go to the model with it. Commands
start with a slash:

| Command | Effect |
|---|---|
| `/mode gaps` | switch mode (`synthesis`, `gaps`, `compare`, `extract`) |
| `/sources` | list the papers retrieved for the last question |
| `/clear` | forget the conversation history |
| `/quit` | leave (Ctrl-D and Ctrl-C too) |

## Setting up the models

Two models are involved, and you configure them separately:

- the **language model** (`[llm]`) writes answers. The same setting serves `mosaic ask`, `mosaic chat`,
  `search --summarise`, `--sort relevance` and `mosaic compare`;
- the **embedding model** (`[rag] embedding_*`) turns text into vectors, for `mosaic index`, `--semantic`, `ask` and
  `chat`. Embeddings go through the OpenAI-compatible `/embeddings` endpoint.

`[llm]` accepts `provider = "openai"` or `"anthropic"` for the cloud services, and any OpenAI-compatible server
(Ollama, LM Studio, llama.cpp, vLLM) through `base_url`. An API key is required even for a local server, which
ignores it: any non-empty string does. Without `model`, mosaic uses `gpt-4o-mini` (OpenAI) or
`claude-haiku-4-5-20251001` (Anthropic).

The embedding settings fall back to `llm.base_url` and `llm.api_key` when unset, so one local server needs one URL.
Anthropic has no embedding endpoint: with an Anthropic language model, set `--embedding-base-url` and
`--embedding-api-key` for another server.

### A local server (Ollama)

```bash
ollama pull qwen3-embedding:0.6b       # an embedding model
ollama pull qwen3:8b                   # a language model; any chat model you have works

mosaic config --llm-provider openai --llm-base-url http://localhost:11434/v1 \
              --llm-api-key ollama --llm-model qwen3:8b
mosaic config --embedding-model qwen3-embedding:0.6b
```

LM Studio (`http://localhost:1234/v1`) and llama.cpp's server (`http://localhost:8080/v1`) work the same way; the
model name must be the one the server lists. The base URL works with or without the trailing `/v1`.

A large model on a desktop GPU can take minutes for one answer, especially a model that reasons before
answering; mosaic waits two to three minutes by default. Raise the limit with `mosaic config --llm-timeout 900`
(seconds).

### Cloud services

```bash
# OpenAI for both
mosaic config --llm-provider openai --llm-api-key sk-... --llm-model gpt-4o-mini
mosaic config --embedding-model text-embedding-3-small

# Anthropic for answers, a local server for embeddings
mosaic config --llm-provider anthropic --llm-api-key sk-ant-...
mosaic config --embedding-model qwen3-embedding:0.6b \
              --embedding-base-url http://localhost:11434/v1 --embedding-api-key ollama
```

## How it works

Indexing. For each paper mosaic builds a text from the title, the first ten authors, the venue and the abstract.
When the paper's PDF is in the library and `pymupdf` is installed, it also extracts the full text and splits it into
overlapping chunks of about `chunk_size` tokens (counted as 4 characters each), every chunk prefixed with the same
header; otherwise the paper is one chunk. The vectors go into a `vec0` table ([sqlite-vec](https://github.com/asg017/sqlite-vec))
in the cache database. mosaic records the embedding model's name and refuses to index with a different one until you
run `mosaic index --reindex`. Papers already indexed are skipped, so `mosaic index` after new searches only embeds the
new ones.

Retrieval. The question is embedded with the same model; mosaic takes the nearest chunks, keeps the best chunk of
each paper, applies your filters, optionally re-ranks with the [citation graph](./citation-graph), and keeps
`top_k` papers.

Answer. The model receives the question, the mode's instructions and the numbered papers, each with its best chunk
(or the first 400 characters of its abstract). It is told to use only these papers and to cite them as `[n]`; check
any claim that matters against the paper.

## Configuration

```toml
[llm]
provider = "openai"                     # openai | anthropic; "openai" for any compatible server
api_key  = "ollama"
model    = "qwen3:8b"
base_url = "http://localhost:11434/v1"  # empty for the cloud services

[rag]
embedding_model    = "qwen3-embedding:0.6b"
embedding_base_url = ""      # empty: llm.base_url, then the OpenAI API
embedding_api_key  = ""      # empty: llm.api_key
top_k              = 10      # papers per question         (mosaic config --rag-top-k)
chunk_size         = 512     # tokens per full-text chunk  (edit the file)
chunk_overlap      = 50      # tokens shared by neighbours (mosaic config --chunk-overlap)
full_text_index    = true    # chunk downloaded PDFs       (mosaic config --no-full-text-index)
auto_index         = false   # index new papers after search and get (mosaic config --rag-auto-index)
```

With `auto_index = true`, `mosaic search` and `mosaic get` embed the papers they return. Failures there are
silent: if the embedding server is down, nothing is indexed and nothing tells you. Run `mosaic index` to catch up.

## Limits and troubleshooting

- `sqlite-vec` comes with the `rag` extra: `pipx install 'mosaic-search[rag]'`, or `[all]`. Full-text chunking
  also needs `pymupdf`, which no extra installs: `pipx inject mosaic-search pymupdf`. Without it `mosaic index`
  prints a warning and indexes metadata only (silence it with `mosaic config --no-full-text-index`).
- Answers can only be as good as what was indexed: for papers without an abstract and without a PDF, the model sees
  little more than a title.
- `ask` and `chat` need the embedding server at question time (the question is embedded), and the language model.
- "Embedding model changed": you configured a model other than the one that built the index. Switch back, or
  `mosaic index --reindex`.

See also: [tutorial chapter 9](/tutorial/09-library), [recipes](/cookbook/ai), [`mosaic index`](/reference/index-command),
[`mosaic ask`](/reference/ask), [`mosaic chat`](/reference/chat).
