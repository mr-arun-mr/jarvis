"""Delivery for alerts, timers and briefings: macOS notification, speech, HUD feed, optional phone push.

Phone push (optional, config.json):
  "phone": {"ntfy_topic": "<long random topic>"}          # free, via ntfy.sh; anyone with the topic can read it
  "phone": {"ntfy_topic": "...", "ntfy_server": "https://ntfy.example.com"}   # self-hosted
Only the title and short body are sent. Keep sensitive details out of alerts.
"""
import itertools
import subprocess
import threading
import urllib.request
from collections import deque
from datetime import datetime

import config
import speech

_events: deque = deque(maxlen=50)
_ids = itertools.count(1)
_lock = threading.Lock()
VOICE = "Daniel"


def in_quiet_hours(now: datetime | None = None) -> bool:
    cfg = config.load().get("alerts", {})
    start, end = cfg.get("quiet_start", "23:00"), cfg.get("quiet_end", "07:00")
    t = (now or datetime.now()).strftime("%H:%M")
    return (start <= t or t < end) if start > end else (start <= t < end)


def _mac_notification(title: str, body: str) -> None:
    script = 'on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run'
    subprocess.run(["osascript", "-e", script, title[:80], body[:240]], capture_output=True, timeout=10)


def _phone_push(title: str, body: str, urgent: bool) -> None:
    phone = config.load().get("phone", {})
    topic = phone.get("ntfy_topic")
    if not topic:
        return
    server = phone.get("ntfy_server", "https://ntfy.sh").rstrip("/")
    req = urllib.request.Request(
        f"{server}/{topic}", data=body.encode(), method="POST",
        headers={"Title": title.encode("ascii", "replace").decode(), "Priority": "high" if urgent else "default"})
    urllib.request.urlopen(req, timeout=10).read()


def notify(title: str, body: str, speak: bool = False, urgent: bool = False, phone: bool = False) -> None:
    """Show a Mac notification and queue it for the HUD. Speaks only outside quiet hours (urgent overrides)."""
    quiet = in_quiet_hours() and not urgent
    with _lock:
        _events.append({"id": next(_ids), "title": title, "body": body, "time": datetime.now().strftime("%H:%M")})
    for step in (lambda: _mac_notification(title, body),
                 lambda: _phone_push(title, body, urgent) if phone or urgent else None):
        try:
            step()
        except Exception:
            pass  # a failing channel must not stop the others
    if speak and not quiet:
        speech.say_async(body, VOICE)


def events_since(last_id: int) -> list[dict]:
    with _lock:
        return [e for e in _events if e["id"] > last_id]
