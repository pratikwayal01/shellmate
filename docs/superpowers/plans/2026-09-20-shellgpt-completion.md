# ShellGPT Completion Tier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a zero-server completion tier to shellmate's answer chain so partial commands (`docker p`) get instant local completions from the trained shellGPT model.

**Architecture:** numpy-only forward pass over the trained checkpoint exported to a small npz; new `[gpt]` tier slotted between `[tldr]` and llama; gate on "first token is a known tool, rest isn't English" so llama still answers prose.

**Tech Stack:** numpy (no torch in shellmate), PyInstaller (binary bundle), tldr FTS5 db (tool-name gate).

**Spec:** Approved design (completion tier) — see conversation.

## Global Constraints
- `numpy` only in shellmate repo — torch stays in `/home/pratik/code/shellGPT`.
- Mirror `shell_gpt.py` sampling exactly: temp 0.7, top_k 10, stop at `\n`, `max_new=80`, byte tokens, block 128, dropout off at eval.
- `install.sh` untouched; model rides in the binary via `.spec` `datas`.
- Existing tier behavior unchanged: `show disk space` still `[map] df -h`.
- No test framework exists in either repo — follow the `cmdmap._self_check()` inline pattern + printf-pipe smoke.

## File structure
| Repo | File | Role |
|---|---|---|
| shellGPT | **create** `export_npz.py` | torch→npz export + `expect_logits.npy` reference |
| shellmate | **create** `shellgpt.py` (~130 ln) | numpy forward, `complete()`, `_looks_like_partial()`, `_self_check()` |
| shellmate | modify `llm.py` | slot `[gpt]` tier into `answer()` + main-loop tag groups |
| shellmate | modify `shellmate.spec` | bundle `shellmate_model.npz` |
| shellmate | modify `entry.sh` | `--with requests,numpy` |
| shellmate | add `shellmate_model.npz`, `expect_logits.npy` | committed assets |

---

### Task 1: Export torch checkpoint → npz (+ logits reference)
**Files:** create `/home/pratik/code/shellGPT/export_npz.py`; run in venv `/tmp/opencode/shellgpt-venv`.

- [ ] **Step 1:** Write `export_npz.py`:
  ```python
  #!/usr/bin/env python
  """One-off: shell_gpt.pt -> shellmate_model.npz + expect_logits.npy."""
  import numpy as np, torch
  from shell_gpt import ShellGPT

  ckpt = torch.load("shell_gpt.pt", map_location="cpu")
  cfg  = ckpt["cfg"]
  sd   = {k: v.numpy().astype(np.float32) for k, v in ckpt["model"].items()}
  cfgm = {f"cfg_{k}": np.array(getattr(cfg, k)) for k in
          ("n_embd", "n_layer", "n_head", "block_size", "vocab_size")}
  np.savez_compressed("shellmate_model.npz", **sd, **cfgm)
  print("params:", sum(v.size for v in sd.values()))

  model = ShellGPT(cfg).eval()
  model.load_state_dict(ckpt["model"])
  prefix = "docker p"
  idx = torch.tensor([list(prefix.encode())][-cfg.block_size:])
  logits, _ = model(idx)
  np.save("expect_logits.npy", logits[-1].detach().numpy().astype(np.float32))
  print("expect_logits.npy:", logits.shape)
  ```
- [ ] **Step 2:** Run it → verify output; copy `shellmate_model.npz` + `expect_logits.npy` into `/home/pratik/work/shellmate/`.
- [ ] **Step 3:** Commit in shellGPT repo (`export_npz.py`).

### Task 2: numpy inference `shellgpt.py`
**Files:** create `/home/pratik/work/shellmate/shellgpt.py`.

- [ ] **Step 1:** Write module — `_model_path()` (via `sys._MEIPASS`/`Path(__file__).parent`), lazy `_load()` caching params dict, `_encode`, `_forward(x: np.ndarray) -> np.ndarray` (byte-embed + 4× Block + LN_f + tied head; `nn.LayerNorm` eps `1e-5`; `nn.GELU()` = `0.5*x*(1+erf(x/sqrt(2)))`), `complete(prefix, n=5)` (dedupe loop, top-k 10, temp 0.7, stop `\n`), `_self_check()` (asserts logits diff vs `expect_logits.npy` < 1e-4; determinism).
- [ ] **Step 2:** Run `_self_check()` → PASS (<1e-4). Commit.
- [ ] **Step 3:** `_looks_like_partial(text)`:
  ```python
  _FILLER = {"a","an","and","or","with","to","for","of","in","on","the","my","your","how","do","i","want","is","are","can","show","list","get","using","use","tell","me","please","we","it","this","that"}
  def _looks_like_partial(text):
      toks = re.findall(r"[a-z0-9][a-z0-9._/+-]*", text.lower())
      if len(toks) < 2 or not _TOOLS.load() or toks[0] not in _TOOLS.get():
          return False
      for t in toks[1:]:
          if t[0] not in "-." and t in _FILLER:
              return False
      return True
  ```
  `_TOOLS` = first-word set of tldr db `name` column (`~/.cache/shellmate/commands.db`), lazily loaded, empty→False.
- [ ] **Step 4:** `__main__` demo: `docker p` → True, `compress a folder with tar` → False, `show disk space` → False. Commit.

### Task 3: Wire tier into `llm.py` + entry.sh
- [ ] **Step 1:** In `answer()` (llm.py:92-104), insert between tldr-miss and model:
  ```python
  if _gpt is None:
      import shellgpt as _gpt
  c = _gpt.complete(text) if _gpt._looks_like_partial(text) else []
  if c:
      return "[gpt]", c[0], 0.0
  ```
  (module-global `_gpt`, same lazy pattern as `_tldr`; missing npz → `complete` returns `[]` → falls through.)
- [ ] **Step 2:** main-loop tag group — change `if tag in ("[map]", "[tldr]"):` (llm.py:312) to include `"[gpt]"`. `maybe_run` already guards non-map tiers.
- [ ] **Step 3:** entry.sh → `--with requests,numpy`. Commit both.

### Task 4: spec bundle + end-to-end smoke
- [ ] **Step 1:** `shellmate.spec` — `datas=[("commands.json","."), ("shellmate_model.npz",".")]`.
- [ ] **Step 2:** Smoke (source mode): `printf 'docker p\nn\n' | ./entry.sh` → `[gpt] docker ps ...`, no run; `printf 'show disk space\n' | ./entry.sh` → `[map] df -h`; `printf 'how do I check disk space\n'` → `[tldr]`/`[model]`. Commit.

---

**skipped:** multi-completion list display (single best line keeps `maybe_run` single-line contract), `|`/`;`-bearing partials (rare; llama covers), PyInstaller binary build (release flow, later). **Gap noted:** single-token partial (`docke`) falls to llama — tldr bare-name path already covers exact names.