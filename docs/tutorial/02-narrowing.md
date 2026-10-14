---
pageClass: tutorial-page
aside: false
title: 2. Narrowing the results
---

# 2. Narrowing the results

The first search returned everything that mentions the words anywhere. Each option below removes one kind of
noise.

## One source, a range of years

<<< @/examples/output/02/source.txt{console}

- `--source arxiv` (or `-s arxiv`) queries one source. The shorthands are listed on [Sources](/guide/sources):
  `ss` Semantic Scholar, `oa` OpenAlex, `epmc` Europe PMC, `crossref`, `hal`, `pubmed` and so on.
- `--year 2020-2025` keeps an inclusive range; `--year 2023` one year; `--year 2019,2021,2023` a list. mosaic sends
  the range to the sources that support it, then checks it on every result.

Not every row is about Hall thrusters: one is about the Hall effect in a crystal, two about other thrusters. The
words matched their abstracts.

## Only the title

<<< @/examples/output/02/field.txt{console}

`--field title` turns the query into a title search, in each source's syntax (`ti:` on arXiv, `title.search` on
OpenAlex); `--field abstract` does the same for abstracts. `--sort citations` puts the most-cited papers first and
adds the **Cited** column, from the counts OpenAlex, Semantic Scholar and Scopus report. `--sort year` puts the
newest first; `--sort relevance` is the subject of [chapter 8](./08-local-model).

## An author

<<< @/examples/output/02/author.txt{console}

`--author` matches part of any author's name, ignoring case and accents: `Boeuf` finds Jean-Pierre Bœuf. Repeat it
for several authors (`-a Boeuf -a Garrigues`); a paper passes if any of them signed it. `--journal` matches part of
the journal name the same way.

## Open access, with a PDF

<<< @/examples/output/02/oa.txt{console}

`--oa-only` keeps the papers marked open access or with a known PDF link; `--pdf-only` keeps those with a PDF link.
[Chapter 4](./04-pdfs) downloads these without further effort.

## Who answered what

<<< @/examples/output/02/stats.txt{console}

`--stats` prints how many results each source returned, how many duplicates were merged, and how many unique
papers remain. A source that never returns anything for your field is a candidate for
`mosaic config --disable-source NAME`.

## The raw query

If you know a source's query language, `--raw-query` sends your text as it is and skips the field and author
translation. Year filters still apply to the results:

```bash
mosaic search "" --source arxiv --raw-query 'ti:"hall thruster" AND abs:kinetic'
```

::: tip What you learned
`--source`, `--year`, `--field`, `--author`, `--journal`, `--oa-only`, `--pdf-only`, `--sort`, `--stats` and
`--raw-query`. Filters combine: a paper must pass all of them. Reference: [`search`](/reference/search).
:::

Next: [3. The local cache](./03-cache).
