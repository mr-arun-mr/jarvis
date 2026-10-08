"""User settings from config.json (next to this file). Missing file or keys fall back to defaults."""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DEFAULTS = {"default_city": "", "model": "qwen2.5:14b"}


def load() -> dict:
    try:
        with open(PATH) as f:
            return {**DEFAULTS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)
