"""Citation provider registry — constructs ordered provider chains from config."""

from __future__ import annotations

from mosaic.citations.base import BaseCitationProvider
from mosaic.citations.crossref import CrossRefCitationProvider
from mosaic.citations.openalex import OpenAlexCitationProvider
from mosaic.citations.opencitations import OpenCitationsCitationProvider

# All known providers in default priority order.
_DEFAULT_PROVIDERS = ["openalex", "crossref"]

# Registry: provider name → factory callable
_REGISTRY: dict[str, type[BaseCitationProvider]] = {
    "openalex":       OpenAlexCitationProvider,
    "crossref":       CrossRefCitationProvider,
    "opencitations":  OpenCitationsCitationProvider,
}


def build_citation_providers(cfg: dict) -> list[BaseCitationProvider]:
    """Return an ordered list of citation providers from config.

    Reads ``cfg["rag"]["citations"]["providers"]`` for the priority order.
    Falls back to ``["openalex", "crossref"]`` when not set.  Passes the
    polite-pool email (from ``cfg["unpaywall"]["email"]`` or
    ``cfg["sources"]["openalex"]["email"]``) to providers that accept it.

    Args:
        cfg: The loaded mosaic config dict.

    Returns:
        List of instantiated ``BaseCitationProvider`` objects in priority
        order.  Unknown provider names are logged and skipped.
    """
    import logging
    _log = logging.getLogger(__name__)

    citations_cfg = cfg.get("rag", {}).get("citations", {})
    provider_names: list[str] = citations_cfg.get("providers", _DEFAULT_PROVIDERS)

    # Resolve polite-pool email from multiple config locations
    email: str = (
        cfg.get("unpaywall", {}).get("email", "")
        or cfg.get("sources", {}).get("openalex", {}).get("email", "")
    )

    providers: list[BaseCitationProvider] = []
    for name in provider_names:
        cls = _REGISTRY.get(name)
        if cls is None:
            _log.warning("citations: unknown provider %r — skipped", name)
            continue
        # Only pass email to providers whose __init__ accepts it
        import inspect
        sig = inspect.signature(cls.__init__)
        if "email" in sig.parameters:
            providers.append(cls(email=email))  # type: ignore[call-arg]
        else:
            providers.append(cls())
    return providers
