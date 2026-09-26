"""Flask route handlers for the MOSAIC web UI.

All routes are registered on the single ``ui`` blueprint (so templates keep
using ``url_for("ui.<view>")``); each module groups the pages of one area.
Importing a module registers its routes.
"""

from mosaic.ui.routes.common import bp

# isort: off
from mosaic.ui.routes import (  # noqa: F401
    search,
    papers,
    exports,
    settings,
    notebook,
    bulk,
    library,
    analysis,
    rag,
    sessions,
)

# isort: on

__all__ = ["bp"]
