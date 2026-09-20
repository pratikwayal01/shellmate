#!/bin/sh
# shellmate — self-resolving entry point (works from any clone location)
exec uv run --with requests --with numpy python3 "$(dirname "$(readlink -f "$0")")/llm.py" "$@"