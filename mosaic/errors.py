"""MOSAIC error hierarchy and logging setup."""

from __future__ import annotations

import logging

# ---------------------------------------------------------------------------
# Central logger — all modules should use ``logging.getLogger(__name__)``
# which inherits from the root "mosaic" logger configured here.
# ---------------------------------------------------------------------------

logger = logging.getLogger("mosaic")

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.ERROR)


def set_verbose_logging(verbose: bool) -> None:
    """Lower log level to WARNING when verbose mode is active."""
    logger.setLevel(logging.WARNING if verbose else logging.ERROR)


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class MosaicError(Exception):
    """Base exception for all MOSAIC-specific errors."""


class SourceError(MosaicError):
    """Raised when a search source fails (network, parsing, auth)."""


class DownloadError(MosaicError):
    """Raised when a PDF download fails."""


class ConfigError(MosaicError):
    """Raised when configuration is invalid or missing."""
