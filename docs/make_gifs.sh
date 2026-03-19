#!/usr/bin/env bash
# make_gifs.sh — generate all MOSAIC demo GIFs using VHS
# Install VHS: https://github.com/charmbracelet/vhs#installation
# Usage: bash make_gifs.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p public/gifs/tapes

# ── force color output in VHS sessions ───────────────────────────────────────
export TERM=xterm-256color
export COLORTERM=truecolor
export CLICOLOR=1
export CLICOLOR_FORCE=1
export FORCE_COLOR=1

# ── slowout: write stdin line-by-line with a configurable delay ───────────────
# Injected into a temp bin dir on PATH so VHS tape sessions can use it as a
# plain command: e.g.  mosaic search ... | slowout .2
_TMPBIN=$(mktemp -d)
cat > "$_TMPBIN/slowout" <<'SLOWOUT'
#!/usr/bin/env bash
delay=${1:-.1}
while IFS= read -r line; do
  printf '%s\n' "$line"
  sleep "$delay"
done
SLOWOUT
chmod +x "$_TMPBIN/slowout"
export PATH="$_TMPBIN:$PATH"

trap 'rm -rf "$_TMPBIN"' EXIT

# ─── Shared VHS header (written into every tape) ─────────────────────────────
# Adjust Width/Height if your terminal font or resolution differs.

# ─── 1. Quick search ─────────────────────────────────────────────────────────
cat > public/gifs/tapes/01_quick_search.tape <<'TAPE'
Output public/gifs/01_quick_search.gif
Set FontSize 12
Set Width 1200
Set Height 900
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s
Type "mosaic search 'scramjet high order simulation' --max 1"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 8s
TAPE

# ─── 2. Search + OA download ─────────────────────────────────────────────────
cat > public/gifs/tapes/02_search_download.tape <<'TAPE'
Output public/gifs/02_search_download.gif
Set FontSize 12
Set Width 1200
Set Height 600
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 120s

Sleep 1s
Type "mosaic search 'mhd amr solver' --oa-only --download -n 1"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 8s
TAPE

# ─── 3. Multi-filter search ───────────────────────────────────────────────────
cat > public/gifs/tapes/03_filter_search.tape <<'TAPE'
Output public/gifs/03_filter_search.gif
Set FontSize 12
Set Width 1100
Set Height 600
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s
Type "mosaic search 'amr hypersonic high order simulation' -y 2022-2024 --source sp -n 5"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 8s
TAPE

# ─── 4. Fetch a single paper by DOI ──────────────────────────────────────────
cat > public/gifs/tapes/04_doi_get.tape <<'TAPE'
Output public/gifs/04_doi_get.gif
Set FontSize 12
Set Width 1100
Set Height 180
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s
Type "mosaic get 10.48550/arXiv.1706.03762"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 8s
TAPE

# ─── 5. Configuration setup ───────────────────────────────────────────────────
cat > public/gifs/tapes/05_config.tape <<'TAPE'
Output public/gifs/05_config.gif
Set FontSize 12
Set Width 800
Set Height 1100
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 10s

Sleep 1s
Type "mosaic config --unpaywall-email username@affiliation.xyz"
Sleep 500ms
Enter
Wait
Sleep 1s
Type "mosaic config --show"
Sleep 500ms
Enter
Wait
Sleep 8s
TAPE

# ─── 6. Auth status ───────────────────────────────────────────────────────────
# Shows saved browser sessions (used for authenticated publisher access).
cat > public/gifs/tapes/06_auth_status.tape <<'TAPE'
Output public/gifs/06_auth_status.gif
Set FontSize 12
Set Width 1100
Set Height 400
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 10s

Sleep 1s
Type "mosaic auth status"
Sleep 500ms
Enter
Wait
Sleep 2s
Type "# Log in to a publisher site (opens headed browser):"
Sleep 1s
Type ""
Enter
Sleep 500ms
Type "# mosaic auth login elsevier https://www.sciencedirect.com"
Sleep 2s
Enter
Sleep 3s
TAPE

# ─── 7. NotebookLM ────────────────────────────────────────────────────────────
# NOTE: this command opens a headed Chromium window for Google auth.
# It cannot run headlessly inside VHS. Options:
#   a) Record it manually with terminalizer or asciinema instead.
#   b) Run `mosaic notebook create` in a real terminal and capture with VHS
#      only if a saved Google session already exists (~/.config/notebooklm/).
#   c) Stub the output for demo purposes.
# The tape below shows the command and its startup output only.
cat > public/gifs/tapes/07_notebook.tape <<'TAPE'
Output public/gifs/07_notebook.gif
Set FontSize 14
Set Width 1100
Set Height 600
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 180s

Sleep 1s
Type "# First-time: authenticate with your Google account"
Enter
Sleep 500ms
Type "notebooklm login"
Sleep 500ms
Enter
Wait
Sleep 2s
Type "# Then create a notebook from a search in one command:"
Enter
Sleep 500ms
Type "mosaic notebook create Transformers --query 'attention is all you need' --oa-only --podcast"
Sleep 500ms
Enter
Wait
Sleep 4s
TAPE

# ─── 8. Output formats ────────────────────────────────────────────────────────
# Demonstrates --output flag: export results to .bib, .csv, .json, .md
cat > public/gifs/tapes/08_output_formats.tape <<'TAPE'
Output public/gifs/08_output_formats.gif
Set FontSize 12
Set Width 1200
Set Height 1000
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s
Type "mosaic search 'maxwell pic conservative high order' -n 1 --output results.bib --output results.csv --output results.json"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 5s
Type "cat results.bib"
Enter
Wait
Sleep 5s
Type "head -5 results.csv"
Enter
Wait
Sleep 5s
TAPE

# ─── 9. Zotero ─────────────────────────────────────────────────────────
cat > public/gifs/tapes/09_zotero.tape <<'TAPE'
Output public/gifs/09_zotero.gif
Set FontSize 12
Set Width 1200
Set Height 900
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s
Type "mosaic search 'adaptive mesh refinement cfd gpu' --oa-only --sort citations --zotero --zotero-collection 'amr-cfd-gpu'"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 8s
TAPE

# ─── Run tapes ────────────────────────────────────────────────────────────────
# Usage:
#   bash make_gifs.sh           — generate all GIFs
#   bash make_gifs.sh 01        — generate only 01_quick_search
#   bash make_gifs.sh 01 05 08  — generate a selection

SKIP_NOTEBOOK=${SKIP_NOTEBOOK:-1}

run_tape() {
    local tape="$1"
    local name
    name=$(basename "$tape" .tape)

    if [[ "$name" == "07_notebook" && "$SKIP_NOTEBOOK" != "0" ]]; then
        echo "  [skipped] $name (set SKIP_NOTEBOOK=0 to include)"
        return
    fi

    echo "  vhs $tape"
    vhs "$tape"
}

echo ""
echo "Generating GIFs..."
echo ""

if [[ $# -eq 0 ]]; then
    for tape in public/gifs/tapes/*.tape; do
        run_tape "$tape"
    done
else
    for id in "$@"; do
        # Accept bare number ("01"), full name ("01_quick_search"), or
        # full filename ("public/gifs/tapes/01_quick_search.tape")
        if [[ -f "$id" ]]; then
            run_tape "$id"
        else
            match=$(compgen -G "public/gifs/tapes/${id}*.tape" 2>/dev/null | head -1 || true)
            if [[ -z "$match" ]]; then
                echo "  [error] no tape found matching '${id}'" >&2
            else
                run_tape "$match"
            fi
        fi
    done
fi

echo ""
echo "Done. GIFs written to public/gifs/"
