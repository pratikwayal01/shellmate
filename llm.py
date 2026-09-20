#!/usr/bin/env python
"""Terminal LLM Assistant — local, provider-free (Spark-X2.5-1.7B via llama.cpp).

'linux commands in human words' — human words in, command out.
Local server: http://127.0.0.1:11434 (llama-server --reasoning off),
OpenAI-compatible /v1/chat/completions.
"""
import select
import sys
import time

try:
    import readline  # arrow keys / line editing in interactive mode
except ImportError:
    pass

import cmdmap  # instant local answer before the model wakes (same dir)

import json
import os
import re
import subprocess
import requests

MODEL = "x"
URL = "http://127.0.0.1:11434/v1/chat/completions"

VERSION = "0.1.0"  # bump on each release (installer downloads the v<VERSION> tag)
UPDATE_URL = "https://api.github.com/repos/pratikwayal01/shellmate/releases/latest"
INSTALLER_URL = "https://raw.githubusercontent.com/pratikwayal01/shellmate/main/install.sh"

TERMINAL_SYSTEM_PROMPT = ("You are an expert Linux systems engineer. When the user asks for a shell "
                          "command, output ONLY the command on a single line. No markdown, no "
                          "explanation, no preamble.")

HISTORY = []
_tldr = None
_gpt = None


def read_multiline_input(prompt=">>> "):
    """Line input that supports pasting whole blocks (multi-line paste)."""
    # paste-drain only for piped/non-tty input; a TTY uses readline (arrows, editing)
    if not sys.stdin.isatty():
        lines = []
        while True:
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
            except (OSError, ValueError):  # select is socket-only on Windows
                r = []
            if not r:
                break
            try:
                line = input()
            except EOFError:
                break
            lines.append(line)
        if lines:
            return "\n".join(lines)
    try:
        return input(prompt)
    except EOFError:
        return "\x04"  # Ctrl-D
    except KeyboardInterrupt:
        return "\x03"  # Ctrl-C


def chat(user_text, system=TERMINAL_SYSTEM_PROMPT, temp=0.7):
    messages = [{"role": "system", "content": system}]
    for role, content in HISTORY[-6:]:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})
    try:
        r = requests.post(URL, json={
            "model": MODEL,
            "messages": messages,
            "max_tokens": 128,
            "temperature": temp,
            "top_p": 0.95,
        }, timeout=300)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content:
            HISTORY.append(("user", user_text))
            HISTORY.append(("assistant", content))
        return content
    except requests.ConnectionError:
        return "ERROR: llama-server not running. Start it:\n  llama-server -m ~/models/Spark-X2.5-1.7B-Q4_K_M.gguf -c 8192 --port 11434 --host 127.0.0.1 --reasoning off"
    except requests.RequestException as e:
        return f"ERROR: {e}"


def answer(text):
    """4-tier chain: map → tldr → gpt → model. Returns (tag, reply, elapsed_s)."""
    global _tldr, _gpt  # lazy import caches assigned below
    m = cmdmap.match(text)
    if m:
        return "[map]", m.command, 0.0
    if _tldr is None:
        import tldr as _tldr  # lazy — keeps startup instant
    hit = _tldr.search(text)
    if hit:
        return "[tldr]", hit, 0.0
    if _gpt is None:
        import shellgpt as _gpt
    c = _gpt.complete(text) if _gpt._looks_like_partial(text) else []
    if c:
        return "[gpt]", c[0], 0.0
    t0 = time.time()
    return "[model]", chat(text), time.time() - t0


def web(host="127.0.0.1", port=8765):
    """Minimal local web UI — stdlib only, same 3-tier chain."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    html = """<!doctype html><html><head><meta charset=utf-8>
<title>shellmate</title><style>
body{font-family:ui-monospace,monospace;max-width:640px;margin:40px auto;padding:0 16px;background:#111;color:#ddd}
#log{white-space:pre-wrap;min-height:200px;border-bottom:1px solid #333;padding-bottom:12px;margin-bottom:12px}
.tag{color:#888}.t{color:#888;font-size:12px}
input{width:100%;box-sizing:border-box;background:#1a1a1a;color:#eee;border:1px solid #333;border-radius:4px;padding:10px;font:16px ui-monospace,monospace}
</style></head><body><h2>shellmate</h2><div id=log></div>
<input id=in placeholder="'linux commands in human words' — Ctrl-D exits when server stops" autofocus>
<script>
const log=document.getElementById('log'),inp=document.getElementById('in');
function add(t,cls){const d=document.createElement('div');d.textContent=t;if(cls)d.className=cls;log.appendChild(d)}
add('shellmate — /quit to exit REPL central terminal (this is the web UI)','tag');
inp.addEventListener('keydown',async e=>{if(e.key!=='Enter'||!inp.value.trim())return;
const q=inp.value;add('> '+q);inp.value='';
const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:q})});
const j=await r.json();add(j.tag+' '+j.reply,'tag');add('( '+j.ms+'ms )','t')});
</script></body></html>"""

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
            tag, reply, ms = answer(data.get("message", ""))
            body = json.dumps({"tag": tag, "reply": reply, "ms": round(ms * 1000)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # silence request spam
            pass

    print(f"shellmate web UI: http://{host}:{port}")
    ThreadingHTTPServer((host, port), H).serve_forever()


def check_update(force=False):
    """Daily GitHub check: notice if a newer release exists. Never blocks startup."""
    stamp = os.path.expanduser("~/.cache/shellmate/.update-check")
    if not force and os.path.exists(stamp):
        try:
            if time.time() - os.path.getmtime(stamp) < 86400:
                return
        except OSError:
            pass
    try:
        os.makedirs(os.path.dirname(stamp), exist_ok=True)
        with open(stamp, "w") as f:  # written before the request: offline = retry tomorrow, not every run
            f.write("1")
        r = requests.get(UPDATE_URL, timeout=5)
        r.raise_for_status()
        latest = r.json()["tag_name"].lstrip("v")
        newer = tuple(int(x) for x in latest.split("."))
        if newer > tuple(int(x) for x in VERSION.split(".")):
            print(f"update available: shellmate {latest} (you have {VERSION})")
            print(f"  /update   or   curl -fsSL {INSTALLER_URL} | bash")
    except (requests.RequestException, ValueError, KeyError, OSError):
        pass  # offline / no release yet — silent


# tripwire patterns — never offer execution for these (short list, not a policy)
RUN_BLOCKED = re.compile(
    r"rm -rf|rm -fr|mkfs\.|fdisk|dd if=|:\(\{|shutdown|poweroff|reboot|init 0|"
    r"> /dev/sd|curl.*\| *bash|wget.*\| *sh|git push --force|sudo rm|chmod 777 /|chown -R",
    re.I)

def maybe_run(cmd, tier="[map]"):
    """Offer to run a suggested command. TTY only, explicit y/n, guarded.
    [map] answers are trusted/curated; [tldr] and [model] answers are
    stripped of markdown and refused if they carry shell metacharacters."""
    if not sys.stdin.isatty():
        return
    if RUN_BLOCKED.search(cmd):
        print("  ! blocked: destructive command pattern — not running")
        return
    cmd = cmd.strip()
    if tier != "[map]":
        cmd = re.sub(r"```[a-zA-Z]*\n?", "", cmd)   # strip code fences
        cmd = cmd.replace("`", "")                  # strip inline backticks
    if re.search(r"<[^>]+>", cmd):
        print(f"  ! has placeholders — fill in and run yourself: {cmd}")
        return
    if re.search(r"/path/to/|your[_ -]?(file|name|dir)|example\.(?:com|org)", cmd):
        print("  ! looks like a template — not running")
        return
    if "\n" in cmd:
        print("  ! multi-line — not running")
        return
    if tier != "[map]":
        # chaining/expansion on untrusted tiers: pipes alone are fine
        if re.search(r"[;&$]|\|\||&&", cmd.replace("\\;", "")):
            print("  ! shell metacharacters — not running")
            return
    try:
        ans = input("  run? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if ans not in ("y", "yes"):
        return
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        out = (p.stdout + p.stderr).strip()
        if out:
            print(out)
        if p.returncode != 0:
            print(f"  ! exit code {p.returncode}")
    except subprocess.TimeoutExpired:
        print("  ! timed out after 30s (long-running? run it yourself)")


def remember(query: str, command: str) -> str:
    """Save to local overlay so the user's correction wins over the map."""
    path = os.path.expanduser("~/.shellmate/commands.local.json")
    entries = []
    if os.path.exists(path):
        with open(path) as f:
            entries = json.load(f)
    entries.append({"kw": [query.strip().lower()], "cmd": command.strip(),
                    "desc": "user-remembered"})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(entries, f, indent=2)
    cmdmap.reload()
    return f"remembered: {command}"


def main():
    global _tldr  # lazy import cache assigned in the loop
    global LAST_SUGGESTED
    LAST_SUGGESTED = [None, None]  # (cmd, tier) for the 'run it' alias
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        web()
        return
    print("llm (Spark-X2.5-1.7B local) — /help for commands, Ctrl-D or /quit to exit")
    if sys.stdin.isatty():
        check_update()
    pending = ""
    while True:
        text = read_multiline_input()
        if text == "\x04":
            print()
            break
        if text == "\x03":
            print()
            continue
        if text.startswith("/"):
            cmd = text.split()[0].lower()
            if cmd in ("/q", "/quit"):
                break
            elif cmd in ("/c", "/clear"):
                HISTORY.clear()
                print("cleared")
            elif cmd in ("/h", "/help"):
                print("commands: /quit /clear /help /update /remember <phrase> :: <cmd>   — plain words ask anything; [map] and [tldr] answers offer run? y/n; 'run it' re-runs the last suggestion")
            elif cmd == "/hi":
                print("llm: local Spark-X2.5-1.7B — no history on disk, no API key")
            elif cmd == "/remember":
                rest = text[len("/remember"):].strip()
                if "::" not in rest:
                    print("usage: /remember <phrase> :: <shell command>")
                else:
                    phrase, command = (p.strip() for p in rest.split("::", 1))
                    print(remember(phrase, command))
            elif cmd in ("/u", "/update"):
                # same safe path as the README one-liner: checksum-verified re-install
                if os.name == "nt":
                    print("update: download the latest exe from https://github.com/pratikwayal01/shellmate/releases/latest")
                else:
                    print("updating...")
                    os.system(f"curl -fsSL {INSTALLER_URL} | bash")
            continue
        if not text.strip():
            continue
        if text.strip().lower() in ("q", "quit", "exit"):
            break
        if text.strip().lower() in ("run it", "run that", "run", "execute", "do it"):
            if LAST_SUGGESTED[0] is None:
                print("  nothing suggested yet")
            else:
                maybe_run(LAST_SUGGESTED[0], LAST_SUGGESTED[1])
            continue
        m = re.match(r"(?i)^run\s+(.+)$", text.strip())
        if m:
            tag, reply, elapsed = answer(m.group(1).strip())
            print(f"{tag} {reply}")
            if tag == "[model]":
                print(f"( {elapsed:.1f}s )")
            maybe_run(reply, tag)   # force the run? offer on any tier
            continue
        tag, reply, elapsed = answer(text)
        print(f"{tag} {reply}")
        if tag in ("[map]", "[tldr]", "[gpt]"):
            maybe_run(reply, tag)
            LAST_SUGGESTED[:] = (reply, tag)
        elif tag == "[model]":
            LAST_SUGGESTED[:] = (reply, tag)
            print(f"( {elapsed:.1f}s )")


if __name__ == "__main__":
    main()