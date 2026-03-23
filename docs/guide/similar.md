---
title: Find Similar Papers
---

# Find Similar Papers

`mosaic similar` discovers papers related to a known work — given only its DOI or arXiv ID.
No query to write, no keyword to think of: point MOSAIC at a paper you already know and let it
map the surrounding literature for you.

```bash
mosaic similar 10.48550/arXiv.1706.03762
```

```
Similar to: Attention Is All You Need

 #   Title                                       Authors              Year   Source     OA    PDF
 1   BERT: Pre-training of Deep Bidirectional…   Devlin et al.        2019   OpenAlex   yes   ✓
 2   Language Models are Few-Shot Learners       Brown et al.         2020   OpenAlex   no    –
 3   Improving Language Understanding by…        Radford et al.       2018   OpenAlex   yes   ✓
...
10 result(s)
```

![Find similar papers demo](/gifs/10_similar.gif)

---

## How it works

`mosaic similar` fans out to two independent sources and merges the results:

| Source | Method | Requires |
|--------|--------|----------|
| **OpenAlex** | `related_works` graph — curated semantic neighbours stored per paper | Nothing — always queried |
| **Semantic Scholar** | Recommendations API — ML-based similarity model over 214 M papers | `ss-key` in config |

When both sources return the same paper (matched by DOI), the records are merged:
the higher citation count wins, and any field missing from one source is filled from the other.

---

## Accepted identifier formats

| Format | Example |
|--------|---------|
| Bare DOI | `10.48550/arXiv.1706.03762` |
| `doi:` prefix | `doi:10.1038/s41586-021-03819-2` |
| `DOI:` prefix | `DOI:10.1038/s41586-021-03819-2` |
| `arxiv:` prefix | `arxiv:1706.03762` |
| `ARXIV:` prefix | `ARXIV:2303.08774` |

---

## Options

```
mosaic similar [OPTIONS] IDENTIFIER
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--max` | `-n` | `10` | Max similar papers to return |
| `--sort` | | — | `citations` (most-cited first) or `year` (newest first) |
| `--oa-only` | | off | Show only open-access papers |
| `--pdf-only` | | off | Show only papers with a known PDF URL |
| `--download` | `-d` | off | Download available PDFs |
| `--download-dir` | | config | Override PDF download directory for this run |
| `--output` | `-o` | — | Save results to file (repeatable); format from extension: `.md`, `.markdown`, `.csv`, `.json`, `.bib` |

---

## Examples

```bash
# Basic: 10 similar papers to the Transformer paper
mosaic similar 10.48550/arXiv.1706.03762

# Use arXiv prefix
mosaic similar arxiv:1706.03762

# 20 results sorted by citation count
mosaic similar 10.48550/arXiv.1706.03762 -n 20 --sort citations

# Open-access only, download PDFs
mosaic similar 10.1038/s41586-021-03819-2 --oa-only --download

# Save to BibTeX for Zotero / LaTeX
mosaic similar 10.48550/arXiv.1706.03762 --output related.bib

# Save to multiple formats
mosaic similar arxiv:2303.08774 -n 30 \
  --output related.md --output related.bib --output related.json
```

---

## Enable Semantic Scholar for better coverage

OpenAlex `related_works` is curated and high-precision but limited in size (typically 20–50 works
per paper). Semantic Scholar's recommendation model covers 214 M papers and returns up to 500
candidates, dramatically increasing recall.

Register a free API key at [semanticscholar.org](https://www.semanticscholar.org/product/api)
and configure it once:

```bash
mosaic config --ss-key YOUR_KEY
```

From that point on, `mosaic similar` automatically queries both sources and merges the results.

---

## Combine with other commands

Use `mosaic similar` as the first step in a literature-discovery workflow:

```bash
# 1. Find related papers, sort by citation count, save to BibTeX
mosaic similar arxiv:1706.03762 -n 30 --sort citations --output seed.bib

# 2. Download open-access PDFs
mosaic similar arxiv:1706.03762 --oa-only --download

# 3. Import everything into a NotebookLM notebook for AI summaries
mosaic notebook create "Transformer neighbours" \
  --from-dir ~/mosaic-papers/
```
