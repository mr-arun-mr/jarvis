"""Timers and alarms. Stored in timers.json so they survive restarts and can be set from any Jarvis process.

The scheduler (scheduler.py, started by server.py) fires them: spoken alert plus notification.
"""
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
KEYWORDS = ["timer", "alarm", "wake me", "remind me in", "countdown", "in 5 minutes", "minutes", "seconds", "alert me"]
_lock = threading.Lock()


def _load() -> list[dict]:
    try:
        with open(PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items: list[dict]) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(PATH))
    with os.fdopen(fd, "w") as f:
        json.dump(items, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, PATH)


def _fmt(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return " ".join(p for p in (f"{h}h" if h else "", f"{m}m" if m else "", f"{s}s" if s and not h else "") if p) or "0s"


def set_timer(minutes: float = 0, seconds: float = 0, label: str = "") -> str:
    """Start a countdown timer."""
    total = float(minutes) * 60 + float(seconds)
    if total < 1 or total > 24 * 3600:
        return "ERROR: A timer must be between 1 second and 24 hours."
    due = time.time() + total
    with _lock:
        items = _load()
        items.append({"id": int(time.time() * 1000), "due": due, "label": label.strip()[:80] or "Timer", "kind": "timer"})
        _save(items)
    return f"Timer set for {_fmt(total)}" + (f" ({label})" if label else "") + "."


def set_alarm(time_of_day: str, label: str = "") -> str:
    """Set an alarm for a clock time like '07:30' or '7:30pm'. Uses the next time that clock time occurs."""
    m = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*", time_of_day.lower())
    if not m:
        return "ERROR: Give a time like 07:30 or 7:30pm."
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return "ERROR: That is not a valid time."
    now = datetime.now()
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if due <= now:
        due += timedelta(days=1)
    with _lock:
        items = _load()
        items.append({"id": int(time.time() * 1000), "due": due.timestamp(), "label": label.strip()[:80] or "Alarm", "kind": "alarm"})
        _save(items)
    return f"Alarm set for {due.strftime('%A %H:%M')}" + (f" ({label})" if label else "") + "."


def list_timers() -> str:
    """Active timers and alarms."""
    items = sorted(_load(), key=lambda i: i["due"])
    if not items:
        return "No active timers or alarms."
    now = time.time()
    return "Active:\n" + "\n".join(
        f"- {i['label']} ({i['kind']}): {_fmt(i['due'] - now)} left, at {datetime.fromtimestamp(i['due']).strftime('%H:%M')}"
        for i in items)


def cancel_timer(label: str = "") -> str:
    """Cancel timers whose label contains the text; with no label, cancels all."""
    with _lock:
        items = _load()
        keep = [i for i in items if label.strip() and label.lower() not in i["label"].lower()]
        _save(keep)
    n = len(items) - len(keep)
    return f"Cancelled {n} timer(s)/alarm(s)." if n else "Nothing matched."


def pop_due() -> list[dict]:
    """Remove and return timers that are due (called by the scheduler)."""
    with _lock:
        items = _load()
        now = time.time()
        due = [i for i in items if i["due"] <= now]
        if due:
            _save([i for i in items if i["due"] > now])
    return due


def _t(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


TOOLS = [
    _t("set_timer", "Start a countdown timer. Give minutes and/or seconds.",
       {"minutes": {"type": "number"}, "seconds": {"type": "number"}, "label": {"type": "string"}}),
    _t("set_alarm", "Set an alarm for a clock time such as 07:30 or 7:30pm.",
       {"time_of_day": {"type": "string"}, "label": {"type": "string"}}, ["time_of_day"]),
    _t("list_timers", "List active timers and alarms."),
    _t("cancel_timer", "Cancel timers/alarms matching a label (all if no label given).", {"label": {"type": "string"}}),
]
FUNCTIONS = {f.__name__: f for f in (set_timer, set_alarm, list_timers, cancel_timer)}
