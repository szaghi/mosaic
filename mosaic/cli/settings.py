"""The ``config`` command."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import print as rprint

import mosaic.config as cfg_mod
from mosaic.cli.app import app, console, warn
from mosaic.config import apply_api_keys


@app.command()
def config(
    show: Annotated[bool, typer.Option("--show", help="Print current config")] = False,
    # --- API keys ---
    elsevier_key: Annotated[str, typer.Option(help="Set Elsevier / ScienceDirect API key")] = "",
    ss_key: Annotated[str, typer.Option(help="Set Semantic Scholar API key")] = "",
    ncbi_key: Annotated[str, typer.Option(help="Set NCBI API key (used for PubMed and PMC)")] = "",
    core_key: Annotated[str, typer.Option(help="Set CORE API key")] = "",
    ads_key: Annotated[str, typer.Option(help="Set NASA ADS API key")] = "",
    ieee_key: Annotated[str, typer.Option(help="Set IEEE Xplore API key")] = "",
    springer_key: Annotated[str, typer.Option(help="Set Springer API key")] = "",
    scopus_key: Annotated[str, typer.Option(help="Set Scopus API key")] = "",
    scopus_inst_token: Annotated[str, typer.Option(help="Set Scopus institutional token")] = "",
    zenodo_key: Annotated[str, typer.Option(help="Set Zenodo API key")] = "",
    zotero_key: Annotated[str, typer.Option(help="Set Zotero API key (web API)")] = "",
    unpaywall_email: Annotated[str, typer.Option(help="Set Unpaywall email")] = "",
    # --- download / files ---
    download_dir: Annotated[str, typer.Option(help="Set PDF download directory")] = "",
    db_path: Annotated[str, typer.Option(help="Set SQLite cache path")] = "",
    filename_pattern: Annotated[
        str,
        typer.Option(
            help="Set PDF filename pattern (placeholders: {year}, {source}, {author}, {title}, {doi})"
        ),
    ] = "",
    rate_limit_delay: Annotated[
        float | None,
        typer.Option(help="Set default delay between API calls in seconds"),
    ] = None,
    # --- source enable/disable ---
    enable_source: Annotated[
        list[str] | None,
        typer.Option(
            "--enable-source",
            help="Enable a source by name (repeatable). Known names: arxiv, semantic_scholar, sciencedirect, doaj, europepmc, openalex, base, springer_api, core, nasa_ads, ieee, zenodo, crossref, dblp, hal, pubmed, pmc, biorxiv, pedro, scopus",
        ),
    ] = None,
    disable_source: Annotated[
        list[str] | None,
        typer.Option(
            "--disable-source",
            help="Disable a source by name (repeatable). Same names as --enable-source",
        ),
    ] = None,
    # --- obsidian ---
    obsidian_vault: Annotated[str, typer.Option(help="Set Obsidian vault path")] = "",
    obsidian_subfolder: Annotated[
        str, typer.Option(help="Set subfolder inside vault for paper notes")
    ] = "",
    obsidian_filename_pattern: Annotated[
        str,
        typer.Option(
            help="Set Obsidian note filename pattern (placeholders: {year}, {author}, {title})"
        ),
    ] = "",
    obsidian_tag: Annotated[
        list[str] | None,
        typer.Option(
            "--obsidian-tag",
            help="Set Obsidian tags (repeatable, replaces existing list). E.g. --obsidian-tag paper --obsidian-tag science",
        ),
    ] = None,
    obsidian_wikilinks: Annotated[
        bool | None,
        typer.Option(
            "--obsidian-wikilinks/--no-obsidian-wikilinks",
            help="Use Obsidian [[wikilinks]] in generated notes",
        ),
    ] = None,
    # --- pedro ---
    pedro_fair_use: Annotated[
        bool | None,
        typer.Option(
            "--pedro-fair-use/--no-pedro-fair-use",
            help="Acknowledge PEDro fair-use policy to enable the source",
        ),
    ] = None,
    pedro_fetch_details: Annotated[
        bool | None,
        typer.Option(
            "--pedro-fetch-details/--no-pedro-fetch-details",
            help="Fetch each PEDro record page to get authors, year, DOI and abstract (slower)",
        ),
    ] = None,
    pedro_rate_limit_delay: Annotated[
        float | None,
        typer.Option(help="Set PEDro-specific rate-limit delay in seconds (default: 3.0)"),
    ] = None,
    # --- llm ---
    llm_provider: Annotated[
        str,
        typer.Option(
            "--llm-provider", help='LLM provider for relevance ranking: "openai" or "anthropic"'
        ),
    ] = "",
    llm_api_key: Annotated[
        str,
        typer.Option(
            "--llm-api-key", help="API key for the LLM provider (any string for local servers)"
        ),
    ] = "",
    llm_model: Annotated[
        str, typer.Option("--llm-model", help="Model name (leave empty for provider default)")
    ] = "",
    llm_base_url: Annotated[
        str,
        typer.Option(
            "--llm-base-url",
            help="Base URL for a local OpenAI-compatible server (e.g. http://localhost:11434/v1)",
        ),
    ] = "",
    # --- rag / embeddings ---
    embedding_provider: Annotated[
        str,
        typer.Option(
            "--embedding-provider",
            help='Embedding provider: "openai" or "custom" (empty = inherit from the LLM provider)',
        ),
    ] = "",
    embedding_model: Annotated[
        str,
        typer.Option(
            "--embedding-model",
            help="Embedding model name (e.g. snowflake-arctic-embed2, text-embedding-3-small)",
        ),
    ] = "",
    embedding_base_url: Annotated[
        str,
        typer.Option(
            "--embedding-base-url",
            help="Base URL for the embedding server (e.g. http://localhost:11434/v1)",
        ),
    ] = "",
    embedding_api_key: Annotated[
        str,
        typer.Option(
            "--embedding-api-key",
            help="API key for the embedding server (any string for local servers)",
        ),
    ] = "",
    rag_top_k: Annotated[
        int | None,
        typer.Option("--rag-top-k", help="Number of papers retrieved per RAG query (default: 10)"),
    ] = None,
    rag_auto_index: Annotated[
        bool | None,
        typer.Option(
            "--rag-auto-index/--no-rag-auto-index",
            help="Auto-index new papers after each search/get run",
        ),
    ] = None,
    chunk_size: Annotated[
        int | None,
        typer.Option("--chunk-size", help="Max tokens per text chunk (default: 512)"),
    ] = None,
    chunk_overlap: Annotated[
        int | None,
        typer.Option(
            "--chunk-overlap", help="Token overlap between consecutive chunks (default: 50)"
        ),
    ] = None,
    rag_citations: Annotated[
        bool | None,
        typer.Option(
            "--rag-citations/--no-rag-citations",
            help="Boost retrieval with the citation graph (needs `mosaic index --enrich-citations`)",
        ),
    ] = None,
    full_text_index: Annotated[
        bool | None,
        typer.Option(
            "--full-text-index/--no-full-text-index",
            help="Index full PDF text when available (requires pymupdf)",
        ),
    ] = None,
):
    """View or update MOSAIC configuration."""
    cfg = cfg_mod.load()

    # --- API keys ---
    api_keys_changed = apply_api_keys(
        cfg,
        {
            "elsevier_key": elsevier_key,
            "ss_key": ss_key,
            "ncbi_key": ncbi_key,
            "core_key": core_key,
            "ads_key": ads_key,
            "ieee_key": ieee_key,
            "springer_key": springer_key,
            "scopus_key": scopus_key,
            "scopus_inst_token": scopus_inst_token,
            "zenodo_key": zenodo_key,
        },
    )
    # PMC shares the NCBI key
    if ncbi_key:
        cfg["sources"]["pmc"]["api_key"] = ncbi_key
    if zotero_key:
        from mosaic.workflows import configure_zotero_key

        warning = configure_zotero_key(cfg, zotero_key)
        if warning:
            rprint(f"[dark_orange]{warning} (it will be retried on the first export)[/dark_orange]")
        else:
            rprint(f"[green]Zotero web API configured for user {cfg['zotero']['user_id']}[/green]")
    if unpaywall_email:
        cfg["unpaywall"]["email"] = unpaywall_email

    # --- download / files ---
    if download_dir:
        cfg["download_dir"] = download_dir
    if db_path:
        cfg["db_path"] = db_path
    if filename_pattern:
        cfg["filename_pattern"] = filename_pattern
    if rate_limit_delay is not None:
        cfg["rate_limit_delay"] = rate_limit_delay

    # --- source enable/disable ---
    _sources_changed = False
    for name in enable_source or []:
        if name not in cfg_mod.KNOWN_SOURCES:
            rprint(
                f"[red]Unknown source: {name!r}. Known sources: {', '.join(sorted(cfg_mod.KNOWN_SOURCES))}[/red]"
            )
            raise typer.Exit(1)
        cfg["sources"].setdefault(name, {})["enabled"] = True
        rprint(f"[green]Source '{name}' enabled.[/green]")
        _sources_changed = True
    for name in disable_source or []:
        if name not in cfg_mod.KNOWN_SOURCES:
            rprint(
                f"[red]Unknown source: {name!r}. Known sources: {', '.join(sorted(cfg_mod.KNOWN_SOURCES))}[/red]"
            )
            raise typer.Exit(1)
        cfg["sources"].setdefault(name, {})["enabled"] = False
        rprint(f"[dark_orange]Source '{name}' disabled.[/dark_orange]")
        _sources_changed = True

    # --- obsidian ---
    _obsidian_changed = False
    if obsidian_vault:
        cfg["obsidian"]["vault_path"] = obsidian_vault
        _obsidian_changed = True
    if obsidian_subfolder:
        cfg["obsidian"]["subfolder"] = obsidian_subfolder
        _obsidian_changed = True
    if obsidian_filename_pattern:
        cfg["obsidian"]["filename_pattern"] = obsidian_filename_pattern
        _obsidian_changed = True
    if obsidian_tag is not None:
        cfg["obsidian"]["tags"] = obsidian_tag
        _obsidian_changed = True
    if obsidian_wikilinks is not None:
        cfg["obsidian"]["wikilinks"] = obsidian_wikilinks
        _obsidian_changed = True
    if _obsidian_changed:
        rprint("[green]Obsidian config updated.[/green]")

    # --- pedro ---
    if pedro_fair_use is not None:
        cfg["sources"]["pedro"]["acknowledge_fair_use"] = pedro_fair_use
        if pedro_fair_use:
            rprint("[green]PEDro fair-use policy acknowledged. Source is now enabled.[/green]")
        else:
            rprint(
                "[dark_orange]PEDro fair-use acknowledgement removed. Source is now disabled.[/dark_orange]"
            )
    if pedro_fetch_details is not None:
        cfg["sources"]["pedro"]["fetch_details"] = pedro_fetch_details
        if pedro_fetch_details:
            rprint("[green]PEDro detail fetching enabled (authors, year, DOI, abstract).[/green]")
        else:
            warn("[dark_orange]PEDro detail fetching disabled.[/dark_orange]")
    if pedro_rate_limit_delay is not None:
        cfg["sources"]["pedro"]["rate_limit_delay"] = pedro_rate_limit_delay

    # --- llm ---
    if llm_provider:
        cfg["llm"]["provider"] = llm_provider
    if llm_api_key:
        cfg["llm"]["api_key"] = llm_api_key
    if llm_model:
        cfg["llm"]["model"] = llm_model
    if llm_base_url:
        cfg["llm"]["base_url"] = llm_base_url
    _llm_changed = any([llm_provider, llm_api_key, llm_model, llm_base_url])
    if _llm_changed:
        rprint("[green]LLM config updated.[/green]")

    # --- rag ---
    _rag_changed = False
    if embedding_provider:
        cfg["rag"]["embedding_provider"] = embedding_provider
        _rag_changed = True
    if embedding_model:
        cfg["rag"]["embedding_model"] = embedding_model
        _rag_changed = True
    if embedding_base_url:
        cfg["rag"]["embedding_base_url"] = embedding_base_url
        _rag_changed = True
    if embedding_api_key:
        cfg["rag"]["embedding_api_key"] = embedding_api_key
        _rag_changed = True
    if rag_top_k is not None:
        cfg["rag"]["top_k"] = rag_top_k
        _rag_changed = True
    if rag_auto_index is not None:
        cfg["rag"]["auto_index"] = rag_auto_index
        _rag_changed = True
    if chunk_size is not None:
        if chunk_size <= 0:
            rprint("[red]--chunk-size must be a positive number of tokens[/red]")
            raise typer.Exit(1)
        cfg["rag"]["chunk_size"] = chunk_size
        _rag_changed = True
    if chunk_overlap is not None:
        if not 0 <= chunk_overlap < cfg["rag"].get("chunk_size", 512):
            rprint("[red]--chunk-overlap must be >= 0 and smaller than the chunk size[/red]")
            raise typer.Exit(1)
        cfg["rag"]["chunk_overlap"] = chunk_overlap
        _rag_changed = True
    if rag_citations is not None:
        cfg["rag"].setdefault("citations", {})["enabled"] = rag_citations
        _rag_changed = True
    if full_text_index is not None:
        cfg["rag"]["full_text_index"] = full_text_index
        _rag_changed = True
    if _rag_changed:
        rprint("[green]RAG config updated.[/green]")

    _pedro_changed = (
        pedro_fair_use is not None
        or pedro_fetch_details is not None
        or pedro_rate_limit_delay is not None
    )
    _any_changed = any(
        [
            api_keys_changed,
            zotero_key,
            unpaywall_email,
            download_dir,
            db_path,
            filename_pattern,
            rate_limit_delay is not None,
            _sources_changed,
            _obsidian_changed,
            _pedro_changed,
            _llm_changed,
            _rag_changed,
        ]
    )
    if _any_changed:
        cfg_mod.save(cfg)
        rprint("[green]Config saved to[/green] ~/.config/mosaic/config.toml")

    if show or not _any_changed:
        console.print_json(data=cfg)
