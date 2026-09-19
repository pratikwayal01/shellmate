#!/usr/bin/env python3
"""Build ~/.cache/shellmate/commands.db from tldr-pages (stdlib only).

One-time: shallow-clone tldr-pages/tldr, parse pages/linux + pages/common
(~1700 pages), write commands + FTS5 index for intent search. Run again to
refresh. Db is a cache — never committed.

tldr page format:
  # df
  > Display filesystem disk space usage.
  > More information: <https://....>
  -
  - Display all filesystems and their disk usage in human-readable form:
  -
  `df -h`
"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

CACHE = Path(os.path.expanduser("~/.cache/shellmate"))
DB = CACHE / "commands.db"
TLDR_REPO = "https://github.com/tldr-pages/tldr.git"

EX_HEAD = re.compile(r"^`(.+)`$")   # example line: bare "`df -h`"

_ARG = re.compile(r"\{\{[^}]+\}\}")


def clean_example(ex: str) -> str:
    return _ARG.sub("<arg>", ex)


def parse_page(path: Path) -> tuple[str, str, list[str]] | None:
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    name = path.stem
    desc = ""
    for line in lines:
        if line.startswith("> ") and not line.startswith("> More"):
            desc = line[2:].strip()
            break
    ex = []
    for line in lines:
        m = EX_HEAD.match(line.strip())
        if m:
            ex.append(clean_example(m.group(1).strip()))
    if not ex and not desc:
        return None
    return name, desc, ex


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tldr-"))
    try:
        print("cloning tldr-pages/tldr (depth 1)...", flush=True)
        subprocess.run(["git", "clone", "--depth", "1", TLDR_REPO, str(tmp / "tldr")],
                       check=True, capture_output=True)
        pages = (tmp / "tldr" / "pages" / "common", tmp / "tldr" / "pages" / "linux")
        rows = []
        for d in pages:
            for f in sorted(d.glob("*.md")):
                parsed = parse_page(f)
                if parsed:
                    rows.append(parsed)
        print(f"parsed {len(rows)} pages", flush=True)

        CACHE.mkdir(parents=True, exist_ok=True)
        if DB.exists():
            DB.unlink()
        con = sqlite3.connect(DB)
        con.execute("CREATE TABLE commands(id INTEGER PRIMARY KEY, name TEXT, "
                    "description TEXT, examples TEXT)")
        con.execute("CREATE VIRTUAL TABLE commands_fts USING fts5(name, description, "
                    "examples, content='commands', content_rowid='id')")
        con.executemany(
            "INSERT INTO commands(name, description, examples) VALUES (?,?,?)",
            [(n, d, "\n".join(e)) for n, d, e in rows])
        con.execute(
            "INSERT INTO commands_fts(rowid, name, description, examples) "
            "SELECT id, name, description, examples FROM commands")
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
        con.close()
        print(f"wrote {DB} — {n} commands")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()