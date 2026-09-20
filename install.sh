#!/bin/sh
# shellmate installer — downloads the release binary. No build tools, no uv.
#   curl -fsSL https://raw.githubusercontent.com/pratikwayal01/shellmate/main/install.sh | bash
set -e

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
  { echo "no macOS x86_64 build yet (use arm64 or the pip path)" >&2; exit 1; }

bin="shellmate-$os-$arch"
url="https://github.com/pratikwayal01/shellmate/releases/$VERSION/download/$bin"

# --- download + verify -------------------------------------------------------
mkdir -p "$HOME/.local/bin" "$HOME/.cache/shellmate"
tmp="$HOME/.local/bin/$bin"
echo "downloading $bin ($url)..."
curl -fsSL -o "$tmp" "$url"
curl -fsSL -o "$tmp.sha256" "$url.sha256"

# tldr index (tier-2) — release asset, not needed for map/model tiers
if [ ! -f "$HOME/.cache/shellmate/commands.db" ]; then
  echo "downloading tldr index (tier-2 search)..."
  curl -fsSL -o "$HOME/.cache/shellmate/commands.db" \
    "https://github.com/pratikwayal01/shellmate/releases/$VERSION/download/commands.db" \
    || echo "warning: tldr index unavailable — map + model tiers still work" >&2
fi

if command -v sha256sum >/dev/null 2>&1; then
  SUM="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
  SUM="shasum -a 256"
else
  echo "warning: no checksum tool found, skipping verification" >&2
  SUM=
fi
if [ -n "$SUM" ]; then
  (cd "$HOME/.local/bin" && $SUM -c "$bin.sha256")
fi

chmod +x "$tmp"
mv -f "$tmp" "$HOME/.local/bin/shellmate"
rm -f "$HOME/.local/bin/$bin.sha256"

echo
echo "shellmate -> $HOME/.local/bin/shellmate"
echo "ready. run: shellmate"
echo "tip: add $HOME/.local/bin to PATH if it isn't already."