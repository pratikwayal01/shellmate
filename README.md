# cmdmap

Match natural-language queries to exact shell commands. Local, instant,
no model wake.

```
$ python3 cmdmap.py "flush dns cache on arch"
resolvectl flush-caches
```

## How it works

A curated keyword map (`COMMANDS` in `cmdmap.py`) — each entry has
natural phrases a user might type, the exact shell line, and a one-line
description. `match()` strips filler words ("how to", "on arch", "cmd
for"), scores keyword overlap, and returns the single best command above
threshold, or `None`.

Built to be the **first hop** of a local terminal assistant: `~/.llm.py`
(the Spark-X2.5-1.7B REPL) calls `match()` before waking the model.
Hit → command in <1ms. Miss → model answers as before. The 1.7B model
is great at composing commands but lacks obscure knowledge (e.g. Arch's
`resolvectl flush-caches`) — the map covers that gap reliably.

## Usage

### Library

```python
from cmdmap import match

m = match("kill process on port 8080")
if m:
    print(m.command)  # fuser -k 8080/tcp
```

### CLI

```
python3 cmdmap.py "show disk space"   # df -h  (exit 0)
python3 cmdmap.py "tell me a joke"    # no output (exit 1)
```

### Self-check

```
python3 cmdmap.py          # runs asserts on the hit + negative cases
```

## Extending

Add an entry: `kw` = phrases a user might actually type, `cmd` = exact
shell line, `desc` = one line. Generous synonyms beat clever scoring —
the matcher is plain keyword overlap on purpose. Commands with
placeholders use `<placeholder>` so they stay copy-paste-ready.

## The rule

Coverage grows by gap: when the model (or you) fumbles a query, that
command earns a map entry. ~80 entries cover the daily surface; the map
stays curated, never a man-page dump.

MIT licensed. Not affiliated with any LLM project.