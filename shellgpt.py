#!/usr/bin/env python3
"""shellgpt — numpy forward pass over the exported shellGPT checkpoint.

Completion tier for shellmate: turns partial commands ("docker p") into
instantly generated candidates, no llama-server needed. Mirrors the torch
model in shell_gpt.py exactly: byte-token GPT (n_embd=128, 4L/4H), GELU(erf),
LayerNorm(eps=1e-5), tied embeddings, top-k sampling (k=10, temp=0.7).
"""
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_RNG = np.random.default_rng()
_TEMP = 0.7
_TOP_K = 10
_MAX_NEW = 80
_PARCEL = sys._MEIPASS if hasattr(sys, "_MEIPASS") else str(Path(__file__).parent)


@dataclass
class _Model:
    params: dict
    n_embd: int = 128
    n_layer: int = 4
    n_head: int = 4
    block: int = 128


def _model_path():
    return Path(_PARCEL) / "shellmate_model.npz"


def _load():
    if not _model_path().exists():
        return None
    z = np.load(_model_path())
    params = {k: z[k] for k in z.files if not k.startswith("cfg")}
    cfg = {k.replace("cfg_", ""): int(z[k]) for k in z.files if k.startswith("cfg")}
    cfg.setdefault("block", cfg.pop("block_size", 128))  # npz key -> field name
    cfg.pop("vocab_size", None)  # unused — embedding row count comes from weights
    return _Model(params, **cfg)


def _encode(text):
    return list(text.encode("utf-8", errors="replace"))


def _decode(tok):
    return bytes([tok]).decode("utf-8", errors="replace")


def _ln(p, key, x):
    w, b = p.params[f"{key}.weight"], p.params[f"{key}.bias"]
    mu = x.mean(-1, keepdims=True)
    var = ((x - mu) ** 2).mean(-1, keepdims=True)
    return (x - mu) / np.sqrt(var + 1e-5) * w + b


def _attn(p, i, x):
    qkv = x @ p.params[f"blocks.{i}.attn.c_attn.weight"].T  # (T,384)
    q, k, v = (qkv[:, j * p.n_embd:(j + 1) * p.n_embd].reshape(-1, p.n_head, p.n_embd // p.n_head)
               for j in range(3))
    att = np.einsum("ihd,jhd->hij", q, k) / np.sqrt(p.n_embd // p.n_head)
    T = x.shape[0]
    causal = np.tril(np.ones((T, T)))
    att = np.where(causal[None] == 0, -np.inf, att)
    att = np.exp(att - att.max(-1, keepdims=True))
    att = att / att.sum(-1, keepdims=True)
    out = np.einsum("hij,jhd->ihd", att, v).reshape(T, p.n_embd)
    return out @ p.params[f"blocks.{i}.attn.c_proj.weight"].T


def _gelu(x):
    """Vectorized erf GELU (torch default): 0.5*x*(1+erf(x/sqrt(2))). A&S 7.1.26."""
    s = x / np.sqrt(2.0)
    t_ = 1.0 / (1.0 + 0.3275911 * np.abs(s))
    erf = 1.0 - (((((1.061405429 * t_ - 1.453152027) * t_) + 1.421413741) * t_
                   - 0.284496736) * t_ + 0.254829592) * t_ * np.exp(-s * s)
    erf = np.sign(s) * erf
    return 0.5 * x * (1.0 + erf)


def _mlp(p, i, x):
    x = x @ p.params[f"blocks.{i}.mlp.fc.weight"].T
    x = _gelu(x)
    return x @ p.params[f"blocks.{i}.mlp.proj.weight"].T


def _forward(p, tokens):
    T = len(tokens)
    x = p.params["tok_emb.weight"][tokens] + p.params["pos_emb.weight"][:T]
    for i in range(p.n_layer):
        x = x + _attn(p, i, _ln(p, f"blocks.{i}.ln1", x))
        x = x + _mlp(p, i, _ln(p, f"blocks.{i}.ln2", x))
    return _ln(p, "ln_f", x) @ p.params["lm_head.weight"].T  # tied head


def _clean(s):
    """Presentation scrub: tldr templates {{x}} -> x, collapse repeated words."""
    s = re.sub(r"\{\{[^}]*\}\}", lambda m: m.group(0)[2:-2], s)
    s = s.split("{")[0]                            # drop unfinished {{... tails
    s = re.sub(r"(?<!\S)(\S+)(?: \1)+", r"\1", s)  # collapse "cmd cmd"
    s = re.sub(r"[\s>|&;=]+$", "", s)              # trailing redirects/ornaments
    return re.sub(r"\s{2,}", " ", s.strip())


def complete(prefix, n=5):
    """Top-n completions of a partial command. Empty list if no model."""
    p = _load()
    if p is None:
        return []
    seen, out = set(), []
    import itertools
    for _ in itertools.repeat(None, n * 3):
        idx = _encode(prefix)[-p.block:]
        res = []
        for _ in range(_MAX_NEW):
            logits = _forward(p, idx)[-1] / _TEMP
            kth = np.partition(logits, -_TOP_K)[-_TOP_K]
            logits[logits < kth] = -np.inf
            probs = np.exp(logits - logits.max())
            probs /= probs.sum()
            tok = int(_RNG.choice(logits.shape[0], p=probs))
            ch = _decode(tok)
            res.append(ch)
            if ch == "\n":
                break
            idx.append(tok)
        key = _clean(prefix + "".join(res))
        if key and key not in seen:
            seen.add(key)
            out.append(key)
        if len(out) >= n:
            break
    return out


def _db_path():
    return Path.home() / ".cache" / "shellmate" / "commands.db"


def _tools():
    """First-word tool set from the tldr index; empty when db absent."""
    db = _db_path()
    if not db.exists():
        return set()
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        names = [r[0] for r in con.execute("SELECT name FROM commands")]
        con.close()
    except sqlite3.Error:
        return set()
    return {n.split()[0].lower() for n in names if n}


_FILLER = {"a", "an", "and", "or", "with", "to", "for", "of", "in", "on",
           "the", "my", "your", "how", "do", "i", "want", "is", "are", "can",
           "show", "list", "get", "using", "use", "tell", "me", "please",
           "we", "it", "this", "that"}


def _looks_like_partial(text):
    toks = re.findall(r"[a-z0-9][a-z0-9._/+-]*", text.lower())
    if len(toks) < 2:
        return False
    tools = _tools()
    if not tools or toks[0] not in tools:
        return False
    return all(t[0] in "-." or t not in _FILLER for t in toks[1:])


def _self_check():
    """Compare numpy forward against the torch reference logits."""
    p = _load()
    assert p, "no model npz"
    exp = np.load(Path(_PARCEL) / "expect_logits.npy")
    got = _forward(p, _encode("docker p"))
    assert got.shape == exp.shape, f"{got.shape} != {exp.shape}"
    diff = np.abs(got - exp).max()
    print(f"logits max diff vs torch: {diff:.2e}")
    assert diff < 1e-3, "numpy forward diverges from torch reference"
    assert _clean("git branch {{name}}") == "git branch name"
    assert _clean("git check check {{file}}") == "git check file"
    assert _clean("ls --all --all {{dir}}") == "ls --all dir"
    assert _clean("git branch {{x}} > {{y") == "git branch x"
    st = _RNG.bit_generator.state
    first = complete("docker p", 1)
    _RNG.bit_generator.state = st
    second = complete("docker p", 1)
    assert first == second, "same RNG state must give same sample"
    assert first and first[0].startswith("docker p"), f"bad completion: {first}"
    print("ok:", first[0] if first else "(no model)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        _self_check()
    else:
        demo = sys.argv[1] if len(sys.argv) > 1 else "docker p"
        got = complete(demo, 3)
        print(f"complete({demo!r}) -> {got if got else '(no model)'}")
        for t in ("docker p", "compress a folder with tar", "show disk space"):
            print(f"partial({t!r}) = {_looks_like_partial(t)}")