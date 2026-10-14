---
title: Zotero
---

# Zotero

`--zotero` adds the papers of a `search`, `similar` or `get` to your Zotero library, optionally in a named
collection. mosaic talks to Zotero desktop on your machine, or to the Zotero web API when you configure a key.

![Papers added by mosaic in Zotero](/zotero-01.png)

## Usage

```bash
mosaic search "hall thruster particle-in-cell" --zotero
mosaic search "hall thruster" --zotero --zotero-collection "Hall thrusters"
mosaic similar 10.1063/1.4972269 --zotero --zotero-collection "Related work"
mosaic get --from refs.bib --zotero --zotero-collection "Imported"
mosaic search "hall thruster" --download --zotero      # also link the PDFs (local API only)
```

- `--zotero-collection NAME` puts the items in that collection, created on first use (top level).
- `--zotero-local` uses Zotero desktop even when a web API key is configured.

## The two APIs

| Configuration | API used |
|---|---|
| no `zotero.api_key` | local: Zotero desktop at `http://localhost:23119`, which must be running |
| `zotero.api_key` set | web: `https://api.zotero.org/users/<user_id>` |
| `zotero.api_key` set and `--zotero-local` | local |

To use the web API, create a key with write access at
[zotero.org/settings/keys](https://www.zotero.org/settings/keys), then:

```bash
mosaic config --zotero-key YOUR_KEY
```

mosaic asks Zotero for the user ID that owns the key and saves it as `zotero.user_id`.

## How it works

Each paper becomes a Zotero item: `preprint` for arXiv, bioRxiv and medRxiv, `journalArticle` otherwise. The item
gets the title, the authors (split into first and last name: "Last, First" at the comma, "First Last" at the last
space), the year, the abstract, the DOI, the journal and a URL (the paper's page, or `https://doi.org/<doi>`).
Items are sent 50 at a time, Zotero's limit per request.

With `--download`, each downloaded PDF is linked to its item as a `linked_file` attachment: Zotero stores the
absolute path, and the file stays in your mosaic library. The web API gets the metadata only; mosaic does not
upload files.

mosaic does not look for duplicates in Zotero: running the same export twice adds the items twice.

## Configuration

```toml
[zotero]
api_key = ""   # web API key; empty means the local API
user_id = 0    # filled in by mosaic config --zotero-key
```

## Troubleshooting

- "Zotero desktop is not running": start Zotero, or configure a web API key.
- "Zotero web API not reachable. Check your API key.": the key was rejected or has no write access;
  `mosaic config --show` prints the key mosaic uses.
- A collection is missing on another device: it exists on the server only after Zotero syncs.

See also: [tutorial chapter 6](/tutorial/06-exporting), [export recipes](/cookbook/exporting),
[`mosaic search`](/reference/search), [`mosaic get`](/reference/get).
