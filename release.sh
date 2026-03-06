#!/usr/bin/env bash
# release.sh — create a new MOSAIC release
#
# Usage:
#   ./release.sh major          # bump major (1.2.3 → 2.0.0)
#   ./release.sh minor          # bump minor (1.2.3 → 1.3.0)
#   ./release.sh patch          # bump patch (1.2.3 → 1.2.4)
#   ./release.sh 2.5.0          # set exact version
#
# What it does:
#   1. Validates the working tree is clean
#   2. Computes the new version
#   3. Updates pyproject.toml and mosaic/__init__.py
#   4. Commits the version bump
#   5. Creates an annotated git tag vX.Y.Z
#   6. Pushes commit + tag  →  triggers CI (tests → PyPI publish)

set -euo pipefail

# ── helpers ────────────────────────────────────────────────────────────────────

die() { echo "error: $*" >&2; exit 1; }

current_version() {
    grep -E '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/'
}

bump() {
    local ver="$1" part="$2"
    local major minor patch
    IFS='.' read -r major minor patch <<< "$ver"
    case "$part" in
        major) echo "$((major + 1)).0.0" ;;
        minor) echo "${major}.$((minor + 1)).0" ;;
        patch) echo "${major}.${minor}.$((patch + 1))" ;;
    esac
}

validate_semver() {
    [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "'$1' is not a valid semver (X.Y.Z)"
}

# ── argument parsing ────────────────────────────────────────────────────────────

[[ $# -eq 1 ]] || die "Usage: $0 major|minor|patch|X.Y.Z"

CURRENT=$(current_version)
[[ -n "$CURRENT" ]] || die "could not read current version from pyproject.toml"

case "$1" in
    major|minor|patch)
        NEW=$(bump "$CURRENT" "$1")
        ;;
    *)
        validate_semver "$1"
        NEW="$1"
        ;;
esac

echo "current version : $CURRENT"
echo "new version     : $NEW"
echo ""

# ── pre-flight checks ──────────────────────────────────────────────────────────

# must be on main branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)
[[ "$BRANCH" == "main" ]] || die "releases must be cut from 'main' (currently on '$BRANCH')"

# working tree must be clean
[[ -z "$(git status --porcelain)" ]] || die "working tree is not clean; commit or stash changes first"

# tag must not already exist
git fetch --tags -q
git tag | grep -qx "v${NEW}" && die "tag v${NEW} already exists"

# ── update version in files ────────────────────────────────────────────────────

echo "--- updating pyproject.toml"
sed -i "s/^version = \"${CURRENT}\"/version = \"${NEW}\"/" pyproject.toml

echo "--- updating mosaic/__init__.py"
sed -i "s/__version__ = \"${CURRENT}\"/__version__ = \"${NEW}\"/" mosaic/__init__.py

# sanity-check that the replacements actually happened
grep -q "version = \"${NEW}\"" pyproject.toml       || die "pyproject.toml was not updated"
grep -q "__version__ = \"${NEW}\"" mosaic/__init__.py || die "mosaic/__init__.py was not updated"

# ── commit + tag ───────────────────────────────────────────────────────────────

echo "--- committing version bump"
git add pyproject.toml mosaic/__init__.py
git commit -m "chore(release): bump version to ${NEW}"

echo "--- creating annotated tag v${NEW}"
git tag -a "v${NEW}" -m "Release v${NEW}"

# ── push ───────────────────────────────────────────────────────────────────────

echo "--- pushing commit and tag to origin"
git push origin main
git push origin "v${NEW}"

echo ""
echo "released v${NEW} — CI will run tests and publish to PyPI automatically."
