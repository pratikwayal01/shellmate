#!/bin/sh
# shellmate installer.
#   curl -fsSL https://raw.githubusercontent.com/pratikwayal01/shellmate/main/install.sh | bash
#   ... | bash -s -- uninstall      remove binary + cache + local data
#   ... | bash -s -- self-update    re-download latest (same as install)
set -e

BIN_DIR="$HOME/.local/bin"
CACHE_DIR="$HOME/.cache/shellmate"
DATA_DIR="$HOME/.shellmate"

if [ "${1:-}" = uninstall ]; then
  rm -f "$BIN_DIR/shellmate"
  rm -rf "$CACHE_DIR" "$DATA_DIR"
  echo "shellmate removed."
  exit 0
fi

VERSION=${SHELLMATE_VERSION:-latest}
BASE=${SHELLMATE_BASE_URL:-https://github.com/pratikwayal01/shellmate/releases/$VERSION/download}

# --- detect platform -> binary name -----------------------------------------
case "$(uname -s)" in
  Linux*)  os=linux ;;
  Darwin*) os=macos ;;
  *) echo "unsupported OS: $(uname -s) (Linux and macOS only)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
  x86_64|amd64)   arch=x86_64 ;;
  arm64|aarch64)  arch=arm64 ;;
  *) echo "unsupported arch: $(uname -m)" >&2; exit 1 ;;
esac
[ "$os" = macos ] && [ "$arch" = x86_64 ] && \
  { echo "no macOS x86_64 build yet (use arm64)" >&2; exit 1; }

bin="shellmate-$os-$arch"

# --- download to tmp dir (kept out of $BIN_DIR until verified) ---------------
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
echo "downloading $bin ($BASE/$bin)..."
curl -fsSL -o "$tmpdir/$bin" "$BASE/$bin"
curl -fsSL -o "$tmpdir/$bin.sha256" "$BASE/$bin.sha256"

if command -v sha256sum >/dev/null 2>&1; then
  SUM="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
  SUM="shasum -a 256"
else
  echo "warning: no checksum tool found, skipping verification" >&2
  SUM=
fi
if [ -n "$SUM" ]; then
  (cd "$tmpdir" && $SUM -c "$bin.sha256") || { echo "checksum mismatch — install aborted" >&2; exit 1; }
fi

# tldr index (tier-2) — release asset, not needed for map/model tiers
if [ ! -f "$CACHE_DIR/commands.db" ]; then
  echo "downloading tldr index (tier-2 search)..."
  mkdir -p "$CACHE_DIR"
  curl -fsSL -o "$CACHE_DIR/commands.db" "$BASE/commands.db" \
    || echo "warning: tldr index unavailable — map + model tiers still work" >&2
fi

# --- install + smoke test ----------------------------------------------------
mkdir -p "$BIN_DIR"
chmod +x "$tmpdir/$bin"
mv -f "$tmpdir/$bin" "$BIN_DIR/shellmate"
rm -f "$BIN_DIR/$bin.sha256"

printf "show disk space\n" | "$BIN_DIR/shellmate" 2>/dev/null | grep -q "df -h" \
  || { echo "installed binary failed smoke test — check $BIN_DIR/shellmate" >&2; exit 1; }

echo
echo "shellmate -> $BIN_DIR/shellmate"
echo "ready. run: shellmate"
echo "self-update: curl -fsSL https://raw.githubusercontent.com/pratikwayal01/shellmate/main/install.sh | bash"
echo "uninstall:   curl -fsSL https://raw.githubusercontent.com/pratikwayal01/shellmate/main/install.sh | bash -s -- uninstall"