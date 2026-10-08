"""Clipboard and screen. Both are read on request only and processed locally.

describe_screen takes a screenshot and asks a local vision model about it (default qwen2.5vl:7b).
macOS must allow Screen Recording for the app running Jarvis (System Settings > Privacy & Security).
"""
import base64
import os
import subprocess
import tempfile

import ollama

import config

KEYWORDS = ["clipboard", "copied", "pasted", "screen", "screenshot", "what am i looking at", "on my display",
            "this page", "this window"]
VISION_MODEL = config.load().get("vision_model", "qwen2.5vl:7b")


def read_clipboard(max_chars: int = 3000) -> str:
    """Text currently on the clipboard."""
    max_chars = max(100, min(int(max_chars), 8000))
    text = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout
    if not text.strip():
        return "The clipboard is empty (or holds something that isn't text)."
    return text[:max_chars] + ("\n[truncated]" if len(text) > max_chars else "")


def describe_screen(question: str = "Describe what is on the screen.") -> str:
    """Take a screenshot of the main display and answer a question about it with a local vision model."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        r = subprocess.run(["screencapture", "-x", "-t", "png", path], capture_output=True, text=True, timeout=15)
        if r.returncode or os.path.getsize(path) < 1000:
            return ("ERROR: Could not capture the screen. Allow Screen Recording for the app running Jarvis in "
                    "System Settings > Privacy & Security > Screen & System Audio Recording.")
        with open(path, "rb") as f:
            img = base64.b64encode(f.read()).decode()
        try:
            resp = ollama.chat(model=VISION_MODEL, messages=[{"role": "user", "content": question, "images": [img]}])
        except ollama.ResponseError as e:
            return f"ERROR: Vision model unavailable ({e}). Install it with: ollama pull {VISION_MODEL}"
        return resp["message"]["content"].strip()
    finally:
        os.remove(path)


def _t(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


TOOLS = [
    _t("read_clipboard", "Read the text the user last copied.", {"max_chars": {"type": "integer"}}),
    _t("describe_screen", "Look at the user's screen right now and answer a question about it.",
       {"question": {"type": "string", "description": "What to look for or explain"}}),
]
FUNCTIONS = {"read_clipboard": read_clipboard, "describe_screen": describe_screen}
