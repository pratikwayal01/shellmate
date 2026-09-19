#!/usr/bin/env python3
"""tldr fallback — intent → command when cmdmap misses.

Uses the FTS5 db built by build_tldr_db.py (~/.cache/shellmate/commands.db).
Includes the command NAME in the search: a bare name ('df', 'tar') should
hit its own page even when the description is terse.

Contract: returns ONE bare command line (the page's first example) or None —
same shape as cmdmap.match so llm.py treats both identically. No model, no
markdown, no page dump.
"""
from __future__ import annotations

import os
import re
import sqlite3

from cmdmap import _tokens  # same stopword set, same tokenizer

_DB = os.path.expanduser("~/.cache/shellmate/commands.db")

# tokens that FTS5 treats as operators/quotes — force them into quoted terms
_SAFE = re.compile(r"^[a-z0-9]+$")

# generic verbs/adverbs useless for matching example text — strip over _tokens
_NOISE = {"show", "using", "most", "list", "see", "get", "how", "do", "tell", "joke"}


def _match_query(intent: str) -> str | None:
    toks = [t for t in _tokens(intent) if _SAFE.match(t) and t not in _NOISE]
    if not toks:
        return None
    # OR + bm25: docs matching MORE tokens rank higher, single-token hits still surface
    return " OR ".join(f'"{t}"' for t in toks)


def search(intent: str) -> str | None:
    """Best tldr example for intent, or None (also None if db missing)."""
    toks = [t for t in _tokens(intent) if _SAFE.match(t) and t not in _NOISE]
    q = _match_query(intent)
    if q is None or not os.path.exists(_DB):
        return None
    try:
        con = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT c.name, c.examples FROM commands c "
                "JOIN commands_fts f ON f.rowid = c.id "
                "WHERE commands_fts MATCH ? "
                "ORDER BY bm25(commands_fts) LIMIT 10",
                (q,),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if not rows:
        return None
    # prefer a page whose name is literally in the intent ('find large files' -> find)
    name_tokens = set(toks)
    for name, examples in rows:
        if name.split()[0].lower() in name_tokens:
            return examples.split("\n", 1)[0].strip()
    first = rows[0][1].split("\n", 1)[0]
    return first.strip() or None


if __name__ == "__main__":
    import sys

    for query in sys.argv[1:] or ["show processes using most memory", "find large files"]:
        print(f"{query!r} -> {search(query)!r}")