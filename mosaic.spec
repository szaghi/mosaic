# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building the standalone MOSAIC application."""

import platform
import re

# Read version from pyproject.toml so it stays in sync automatically.
_version = "0.0.0"
with open("pyproject.toml", encoding="utf-8") as _f:
    _m = re.search(r'^version\s*=\s*"([^"]+)"', _f.read(), re.MULTILINE)
    if _m:
        _version = _m.group(1)

a = Analysis(
    ["mosaic/gui_launcher.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("mosaic/ui/templates", "mosaic/ui/templates"),
        ("mosaic/ui/static", "mosaic/ui/static"),
    ],
    hiddenimports=[
        # All source modules (explicit imports, but PyInstaller may miss them
        # because they are imported via mosaic.sources.__init__)
        "mosaic.sources",
        "mosaic.sources.arxiv",
        "mosaic.sources.semantic_scholar",
        "mosaic.sources.sciencedirect",
        "mosaic.sources.sciencedirect_browser",
        "mosaic.sources.springer_browser",
        "mosaic.sources.springer_api",
        "mosaic.sources.doaj",
        "mosaic.sources.europepmc",
        "mosaic.sources.openalex",
        "mosaic.sources.base_search",
        "mosaic.sources.core",
        "mosaic.sources.nasa_ads",
        "mosaic.sources.ieee",
        "mosaic.sources.zenodo",
        "mosaic.sources.crossref",
        "mosaic.sources.dblp",
        "mosaic.sources.hal",
        "mosaic.sources.pubmed",
        "mosaic.sources.pmc",
        "mosaic.sources.biorxiv",
        "mosaic.sources.pedro",
        "mosaic.sources.scopus_api",
        "mosaic.sources.scopus_browser",
        "mosaic.sources.unpaywall",
        "mosaic.sources.custom",
        # Modules imported lazily at runtime
        "mosaic.source_registry",
        "mosaic.services",
        "mosaic.parsing",
        "mosaic.errors",
        "mosaic.workflows",
        "mosaic.similar",
        "mosaic.exporter",
        "mosaic.downloader",
        "mosaic.db",
        "mosaic.config",
        "mosaic.models",
        "mosaic.search",
        "mosaic.zotero",
        "mosaic.bulk",
        "mosaic.ui",
        "mosaic.ui.routes",
        "mosaic.ui.jobs",
        # Waitress and its internal modules
        "waitress",
        "waitress.runner",
        "waitress.server",
        "waitress.task",
        "waitress.channel",
        # NotebookLM integration (API calls only — Playwright excluded)
        "mosaic.notebooklm_bridge",
        "notebooklm",
        "notebooklm.client",
        "notebooklm.auth",
        "notebooklm.paths",
        "notebooklm.types",
        "notebooklm.exceptions",
        "notebooklm._core",
        "notebooklm._notebooks",
        "notebooklm._sources",
        "notebooklm._artifacts",
        "notebooklm._chat",
        "notebooklm._notes",
        "notebooklm._research",
        "notebooklm._settings",
        "notebooklm._sharing",
        "notebooklm._url_utils",
        "notebooklm._logging",
        "notebooklm.rpc",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "playwright",
        "notebooklm.cli",
        "notebooklm.notebooklm_cli",
        "notebooklm.__main__",
        "pytest",
        "pytest_cov",
        "tkinter",
        "_tkinter",
        "pywebview",
        "webview",
        "clr",
        "pythonnet",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MOSAIC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MOSAIC",
)

# macOS .app bundle (BUNDLE is macOS-only; Linux/Windows use the COLLECT directory)
if platform.system() == "Darwin":
    app = BUNDLE(
        coll,
        name="MOSAIC.app",
        icon=None,
        bundle_identifier="com.mosaic.search",
        info_plist={
            "LSUIElement": False,
            "CFBundleShortVersionString": _version,
            "CFBundleDisplayName": "MOSAIC",
            "NSHighResolutionCapable": True,
        },
    )
