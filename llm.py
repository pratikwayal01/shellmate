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

import requests

MODEL = "x"
URL = "http://127.0.0.1:11434/v1/chat/completions"

TERMINAL_SYSTEM_PROMPT = ("You are an expert Linux systems engineer. When the user asks for a shell "
                          "command, output ONLY the command on a single line. No markdown, no "
                          "explanation, no preamble.")

HISTORY = []


def read_multiline_input(prompt=">>> "):
    """Line input that supports pasting whole blocks (multi-line paste)."""
    # paste-drain only for piped/non-tty input; a TTY uses readline (arrows, editing)
    if not sys.stdin.isatty():
        lines = []
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
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


def main():
    print("llm (Spark-X2.5-1.7B local) — /help for commands, Ctrl-D or /quit to exit")
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
                print("commands: /quit /clear /help   — or just type a question in plain words")
            elif cmd == "/hi":
                print("llm: local Spark-X2.5-1.7B — no history on disk, no API key")
            continue
        if not text.strip():
            continue
        # instant map hit first — model only wakes for misses
        m = cmdmap.match(text)
        if m:
            print(m.command)
            continue
        t0 = time.time()
        ans = chat(text)
        print(ans)
        print(f"( {time.time() - t0:.1f}s )")


if __name__ == "__main__":
    main()