# shellmate

Local terminal assistant: human words in, exact shell command out.
Instant for known commands (keyword map), Spark-X2.5-1.7B model for the
rest. No cloud, no API key.

```
$ python3 cmdmap.py "flush dns cache on arch"
resolvectl flush-caches
```

## How it works

A curated keyword map (`cmdmap` module: entries in `commands.json`,
loaded by `cmdmap.py`) — each entry has natural phrases a user might
type, the exact shell line, and a one-line description. `match()`
strips filler words ("how to", "on arch", "cmd for"), scores keyword
overlap, and returns the single best command above threshold, or
`None`.

Built to be the **first hop** of a local terminal assistant: `llm.py`
(the Spark-X2.5-1.7B REPL) calls `match()` before waking the model.
Hit → command in <1ms. Miss → model answers as before. The 1.7B model
is great at composing commands but lacks obscure knowledge (e.g. Arch's
`resolvectl flush-caches`) — the map covers that gap reliably.

## Usage

### The assistant (`llm.py`)

```
uv run --with requests python3 llm.py
```

REPL: type questions in plain words. Map hits answer instantly; the
rest go to the local Spark-X2.5-1.7B server (`http://127.0.0.1:11434`).
Interactive mode supports arrows/history (readline); piped input works
too. Slash commands: `/quit` `/clear` `/help`.

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

Edit `commands.json`: `kw` = phrases a user might actually type, `cmd` =
exact shell line, `desc` = one line. Generous synonyms beat clever
scoring — the matcher is plain keyword overlap on purpose. Commands with
placeholders use `<placeholder>` so they stay copy-paste-ready.

## The rule

Coverage grows by gap: when the model (or you) fumbles a query, that
command earns a map entry. ~100 entries cover the daily surface; the map
stays curated, never a man-page dump.

MIT licensed. Not affiliated with any LLM project.