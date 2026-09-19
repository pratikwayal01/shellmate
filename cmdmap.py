#!/usr/bin/env python3
"""cmdmap — match natural-language queries to exact shell commands.

Local, instant, no model wake. llm.py consults match() first and only
falls back to the LLM when nothing hits.

Add an entry: kw = phrases a user might actually type, cmd = the exact
shell line. Generous synonyms beat clever scoring — the matcher is plain
keyword overlap on purpose (ponytail: keep the ladders simple).
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass

# Filler words stripped before scoring. Keep the list small — dropping a
# meaningful word is worse than keeping noise.
_STOP = {
    "how", "to", "do", "i", "want", "the", "a", "an", "for", "on", "of",
    "in", "and", "me", "my", "it", "is", "are", "please", "can", "give",
    "arch", "linux", "cmd", "command", "commands", "need", "me", "out",
    "up", "down", "some",
}
_THRESHOLD = 0.7  # fraction of keyword words that matched, then tie-break

def _load_commands() -> list[dict]:
    """Base entries from commands.json, then user-local overlay wins ties."""
    here = os.path.dirname(os.path.abspath(__file__))
    entries = []
    local = os.path.expanduser("~/.shellmate/commands.local.json")
    if os.path.exists(local):
        with open(local) as f:
            entries.extend(json.load(f))
    with open(os.path.join(here, "commands.json")) as f:
        entries.extend(json.load(f))
    return entries

COMMANDS: list[dict] = _load_commands()


def reload() -> None:
    """Re-read commands.json + local overlay (after /remember)."""
    global COMMANDS
    COMMANDS = _load_commands()


@dataclass
class Match:
    command: str
    desc: str


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP]


def match(query: str) -> Match | None:
    """Best entry for query, or None if nothing clears the threshold."""
    q = _tokens(query)
    if not q:
        return None
    qs = set(q)
    best: tuple[float, int, dict] | None = None
    for entry in COMMANDS:
        for kw in entry["kw"]:
            kwt = _tokens(kw)
            if not kwt:
                continue
            matched = sum(1 for w in kwt if w in qs)
            score = matched / len(kwt)
            # prefer exact-fraction score, then raw word count, then longer phrase
            cand = (score, matched, entry)
            if best is None or cand[:2] > best[:2]:
                best = cand
    if best is None or best[0] < _THRESHOLD:
        return None
    return Match(best[2]["cmd"], best[2]["desc"])


def _self_check() -> None:
    cases = [
        ("flush dns cache on arch", "resolvectl flush-caches"),
        ("clear the dns cache", "resolvectl flush-caches"),
        ("how do i kill process on port 8080", "fuser -k <port>/tcp"),
        ("show disk space", "df -h"),
        ("how much ram is free", "free -m"),
        ("list files bigger than 100MB", "find . -type f -size +100M -exec ls -lh {} \\;"),
        ("restart the docker service", "systemctl restart <service>"),
        ("kubectl cmd to list ingress", "kubectl get ingress -A"),
        ("what time is it", "date"),
        ("my public ip", "curl -s https://ifconfig.me"),
    ]
    for query, expect in cases:
        got = match(query)
        assert got is not None, f"NO MATCH: {query!r}"
        assert got.command == expect, f"WRONG: {query!r} -> {got.command!r}, want {expect!r}"
    for bad in ["tell me a joke", "create a marketing report", "sing a song about cats"]:
        assert match(bad) is None, f"FALSE MATCH: {bad!r} -> {match(bad)!r}"
    print(f"self-check OK: {len(cases)} hits + {3} negative cases")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        m = match(sys.argv[1])
        if m:
            print(m.command)
            sys.exit(0)
        sys.exit(1)
    _self_check()