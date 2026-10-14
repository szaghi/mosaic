#!/usr/bin/env bash
# make_gifs.sh: record the documentation GIFs with VHS (https://github.com/charmbracelet/vhs).
#
# The tapes are in docs/tapes/ and run the real mosaic in a copy of a home directory prepared by
# docs/scripts/docs_examples.py, so the GIFs show the same library as the tutorial:
#
#   MOSAIC_GIF_HOME   a home left by docs_examples.py (config with the Unpaywall e-mail and the LLM, the cache)
#   MOSAIC_GIF_PDF    a PDF of 10.1016/j.paerosci.2006.01.001, "downloaded" by the hand-off tape
#   MOSAIC            the mosaic to run (default: the one on PATH)
#
# No browser opens: BROWSER=true stands in for it, and the Windows tools are dropped from PATH on WSL.
#
# Usage:
#   bash make_gifs.sh                  all tapes
#   bash make_gifs.sh search handoff   some of them
#
# The old tapes in public/gifs/tapes/ made the GIFs of the social posts; run them with `vhs FILE`.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

: "${MOSAIC_GIF_HOME:?set MOSAIC_GIF_HOME to a home prepared by docs/scripts/docs_examples.py}"
mosaic_bin=$(command -v "${MOSAIC:-mosaic}") || { echo "mosaic not found: set MOSAIC" >&2; exit 1; }

home=$(mktemp -d)
bindir=$(mktemp -d)
trap 'rm -rf "$home" "$bindir"' EXIT
cp -a "$MOSAIC_GIF_HOME/." "$home/"
ln -s "$mosaic_bin" "$bindir/mosaic"

# mosaic config saves absolute paths: point the copy's config and download records at the copy
src=$(cd "$MOSAIC_GIF_HOME" && pwd)
sed -i "s|$src|$home|g" "$home/.config/mosaic/config.toml"
python3 - "$home/.local/share/mosaic/cache.db" "$src" "$home" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("UPDATE downloads SET local_path = replace(local_path, ?, ?)", (sys.argv[2], sys.argv[3]))
con.commit()
PY

# the hand-off tape files this paper again: forget the copy the tutorial filed
rm -f "$home"/mosaic-papers/2005_*Boyd_Numerical_modeling*.pdf
mkdir -p "$home/Downloads"
HOME="$home" "$bindir/mosaic" cache clean >/dev/null

# the tapes switch to this home themselves (tapes/_setup.tape): vhs keeps its own, with its browser cache
export MOSAIC_GIF_RUNHOME="$home"
PATH="$bindir:$(printf '%s' "$PATH" | tr ':' '\n' | grep -v '^/mnt/' | paste -sd:)"
export PATH
export BROWSER=true
export MOSAIC_GIF_PDF="${MOSAIC_GIF_PDF:-}"
export TERM=xterm-256color COLORTERM=truecolor FORCE_COLOR=1

mkdir -p public/gifs
tapes=("$@")
[[ ${#tapes[@]} -eq 0 ]] && tapes=(search handoff summarise)
for name in "${tapes[@]}"; do
    echo "recording $name"
    vhs "tapes/$name.tape"
done
