"""Long-term memory: short facts saved in memory.json and shown to the model on every request."""
import json
import os
from datetime import date

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.json")
KEYWORDS = ["remember", "forget", "memory", "my name", "i like", "i prefer", "don't forget"]
MAX_FACTS = 100


def _load() -> list[dict]:
    try:
        with open(PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(facts: list[dict]) -> None:
    fd = os.open(PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(facts, f, indent=1)


def facts_for_prompt() -> str:
    facts = _load()
    return "\n".join(f"- {f['fact']}" for f in facts[-MAX_FACTS:])


def remember(fact: str) -> str:
    """Save a fact about the user for later."""
    fact = fact.strip()[:300]
    if not fact:
        return "ERROR: Nothing to remember."
    facts = _load()
    if any(f["fact"].lower() == fact.lower() for f in facts):
        return "Already remembered."
    facts.append({"fact": fact, "saved": date.today().isoformat()})
    _save(facts[-MAX_FACTS:])
    return f"Remembered: {fact}"


def forget(match: str) -> str:
    """Delete saved facts containing the given text."""
    match = match.strip().lower()
    if len(match) < 3:
        return "ERROR: Be more specific about what to forget."
    facts = _load()
    keep = [f for f in facts if match not in f["fact"].lower()]
    _save(keep)
    n = len(facts) - len(keep)
    return f"Forgot {n} fact(s)." if n else "I had nothing matching that."


TOOLS = [
    {"type": "function", "function": {"name": "remember",
     "description": "Save a lasting fact or preference about the user (only when they ask you to remember something).",
     "parameters": {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]}}},
    {"type": "function", "function": {"name": "forget",
     "description": "Delete saved facts that contain the given text.",
     "parameters": {"type": "object", "properties": {"match": {"type": "string"}}, "required": ["match"]}}},
]
FUNCTIONS = {"remember": remember, "forget": forget}
