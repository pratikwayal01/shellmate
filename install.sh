#!/bin/sh
# shellmate installer: entry point + tldr index. Needs uv on PATH.
set -e
REPO="$(dirname "$(readlink -f "$0")")"
ln -sf "$REPO/entry.sh" "$HOME/.local/bin/shellmate"
echo "shellmate -> $HOME/.local/bin/shellmate"
python3 "$REPO/build_tldr_db.py"   # ~/.cache/shellmate/commands.db
echo "done. run: shellmate"
echo "point llama-server at the model (see README) to enable the model tier."