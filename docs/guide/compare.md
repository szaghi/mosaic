---
title: Compare Papers
---

# Compare papers

`mosaic compare` puts cached papers side by side in a table, one row per paper and one column per dimension you
name: method, dataset, code, key finding. The language model of `[llm]` reads each title and abstract and fills the
cells. Without one, mosaic fills only the columns it has as metadata.

## Usage

```bash
mosaic compare --query "hall thruster" -n 10                          # cached papers matching every word
mosaic compare --query "hall thruster" --sort citations -n 10         # the 10 most cited of them
mosaic compare --from refs.bib --dimensions "method,geometry,code,key finding"
mosaic compare --query "hall thruster" -n 10 --output hall.md         # also write Markdown (.csv, .json)
```

The papers come from the cache: with `--query`, those whose title or abstract contains every word; with `--from`,
those of a `.bib` or `.csv` file that are in the cache (run `mosaic get --from` first for the others); with neither,
the whole cache. `--sort citations` or `--sort year` orders them before `--max` (`-n`, default 20) keeps the first
ones. The default dimensions are `method,dataset,metric,result`.

The terminal always shows the table (number, title, year, authors, then your dimensions); `--output` writes it as
well, as a Markdown table, CSV with a header row, or a JSON list with one object per paper.

## How it works

With a language model configured (see [setting up the models](./rag#setting-up-the-models)), mosaic sends the papers
in batches of 20, each as its title and the first 300 characters of its abstract, and asks for a JSON list of
objects with exactly your dimensions as keys, `-` where the text says nothing. Any dimension name works: the model
reads it as a question about the abstract.

Without a model, mosaic says so in one line and fills the table from metadata. When a request fails or the reply is
not JSON, it falls back to metadata for the whole table and logs a warning (shown with `mosaic --verbose`). These dimension
names are filled from the cache, every other one is `–`:

| Dimension | Filled from |
|---|---|
| `year` | the publication year |
| `source` | the source that returned the paper |
| `journal` | the journal |
| `doi` | the DOI |
| `authors` | the short author list (`Reza et al.`) |
| `citations`, `citation_count`, `cited` | the citation count, when a source reported one |

## Limits

- The model sees 300 characters of each abstract, not the paper. A cell can only be as good as that text, and a
  model can misread it: treat the table as a first pass to check against the papers.
- Each batch of 20 papers is one request; a local model on a large selection takes minutes.
- Wide tables wrap in the terminal. Write `--output table.md` or `.csv` for more than five or six dimensions.

See also: [tutorial chapter 8](/tutorial/08-local-model), [recipes](/cookbook/ai), [`mosaic compare`](/reference/compare).
