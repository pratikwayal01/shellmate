# shellmate

Local terminal assistant: human words in, exact shell command out.
Instant for known commands (keyword map), Spark-X2.5-1.7B model for the
rest. No cloud, no API key.

```
$ python3 cmdmap.py "flush dns cache on arch"
resolvectl flush-caches
```

## How it works

Three tiers, first hit wins:

1. **`cmdmap`** — curated keyword map (`commands.json`, loaded by
   `cmdmap.py`). `match()` strips filler words, scores keyword overlap,
   returns the single best command above threshold, or `None`. Instant.
2. **`tldr`** — FTS5 full-text search over ~6700 tldr-pages
   (`~/.cache/shellmate/commands.db`, built by `build_tldr_db.py`).
   Returns the first example of the best-matching page. No model.
3. **Spark-X2.5-1.7B** — local model for everything the map and tldr
   miss (~1-2s, needs llama-server on :11434).

`llm.py` walks the chain and prefixes the answer with its tier:
`[map]` / `[tldr]` / `[model]`. The 1.7B model is great at composing
commands but lacks obscure knowledge (e.g. Arch's
`resolvectl flush-caches`) — the map and tldr cover that gap.

## Install

```sh
git clone git@github.com:pratikwayal01/shellmate.git ~/work/shellmate
ln -sf ~/work/shellmate/llm.py ~/.llm.py   # keep the llm alias happy
./install.sh   # ~/.local/bin/shellmate + builds tldr index
```

Needs `uv`. The model tier additionally needs llama-server on port
11434 serving Spark-X2.5-1.7B:

```sh
llama-server -m ~/models/Spark-X2.5-1.7B-Q4_K_M.gguf -c 2048 --port 11434 \
  --host 127.0.0.1 --reasoning off --repeat-penalty 1.4 --repeat-last-n 128 \
  --load-mode mlock --threads 16
```

Without llama-server the map/tldr tiers still work; `[model]` queries
print the start hint.

## Usage

### The assistant

```
shellmate            # or: uv run --with requests python3 llm.py
```

REPL: type questions in plain words. Map/tldr hits answer instantly;
the rest go to the local Spark-X2.5-1.7B server. Interactive mode
supports arrows/history (readline); piped input works too. Slash
commands: `/quit` `/clear` `/help` `/remember <phrase> :: <cmd>`.

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

Per-user commands live in `~/.shellmate/commands.local.json` (same
format) and win ties over the repo map — add them with `/remember`, or
edit the file directly. Keep upstream `commands.json` clean.

> Note: `install.sh` symlinks `~/.llm.py` — run it carefully if you
> already have a file at that path.

## The rule

Coverage grows by gap: when the model (or you) fumbles a query, that
command earns a map entry. ~100 entries cover the daily surface; the map
stays curated, never a man-page dump.

MIT licensed. Not affiliated with any LLM project.