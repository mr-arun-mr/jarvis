"""Background scheduler (runs inside server.py): fires timers, briefings and proactive alerts.

Settings in config.json (all optional):
  "briefings": {"morning": "07:30", "night": "21:30"}      # leave out a key to disable it
  "alerts": {"quiet_start": "23:00", "quiet_end": "07:00",
             "calendar": true, "github": true, "email": true, "vehicles": true}
  "doc_reindex_time": "03:00"
Alerts show as notifications by default; only timers, calendar and briefings speak aloud (and not in quiet hours).
State (what was already announced) is kept in alerts_state.json so restarts do not repeat alerts.
"""
import json
import os
import re
import threading
import time
from datetime import date, datetime

import config
import notify
import timer_tool
import vehicle_tool
from applescript import ScriptError, run

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts_state.json")


def _state() -> dict:
    try:
        with open(STATE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(state: dict) -> None:
    with open(STATE, "w") as f:
        json.dump(state, f)
    os.chmod(STATE, 0o600)


def _enabled(name: str) -> bool:
    return config.load().get("alerts", {}).get(name, True)


# ---- jobs -------------------------------------------------------------------------------------

def fire_timers() -> None:
    for t in timer_tool.pop_due():
        what = "Your alarm" if t["kind"] == "alarm" else "Your timer"
        notify.notify(t["label"], f"{what} {t['label']} is done." if t["label"] not in ("Timer", "Alarm")
                      else f"{what} is done.", speak=True, urgent=True)


def briefing(kind: str) -> None:
    import briefing_tool
    text = briefing_tool.get_briefing(kind)
    if not text.startswith("ERROR"):
        notify.notify(f"{kind.title()} briefing", text, speak=True)


def calendar_soon() -> None:
    """Announce events starting within 10 minutes."""
    if not _enabled("calendar"):
        return
    script = """
set out to {}
tell application "Calendar"
  repeat with c in calendars
    try
      set evs to (every event of c whose start date > (current date) and start date <= ((current date) + 10 * minutes))
      repeat with e in evs
        set end of out to (round (((start date of e) - (current date)) / minutes)) & "|" & (summary of e)
      end repeat
    end try
  end repeat
end tell
set AppleScript's text item delimiters to linefeed
return out as text
"""
    try:
        out = run(script, timeout=60)
    except ScriptError:
        return
    state, today = _state(), date.today().isoformat()
    seen = set(state.get("calendar", {}).get(today, []))
    for line in filter(None, out.splitlines()):
        mins, _, title = line.partition("|")
        key = f"{title}@{today}"
        if key in seen:
            continue
        seen.add(key)
        notify.notify("Coming up", f"{title} starts in about {mins.strip()} minutes.", speak=True)
    state["calendar"] = {today: sorted(seen)}
    _save(state)


def github_review() -> None:
    """Notify when a new PR is waiting for the user's review."""
    if not _enabled("github"):
        return
    import github_tool
    try:
        res = github_tool._get("/search/issues", {"q": "is:open is:pr review-requested:@me", "per_page": 10})
    except RuntimeError:
        return
    state = _state()
    seen = set(state.get("github_prs", []))
    for it in res["items"]:
        if it["id"] not in seen:
            repo = it["repository_url"].split("/repos/")[-1]
            notify.notify("Review requested", f"{repo}#{it['number']}: {it['title'][:80]}")
            seen.add(it["id"])
    state["github_prs"] = sorted(seen)[-200:]
    _save(state)


def new_email() -> None:
    """Notify about unread mail that arrived since the last check (counts only, no content)."""
    if not _enabled("email"):
        return
    import gmail_tool
    out = gmail_tool.check_inbox(True, 1)
    m = re.match(r"(\d+) unread", out)
    if not m:
        return
    count, state = int(m.group(1)), _state()
    if state.get("unread") is not None and count > state["unread"]:
        notify.notify("New email", f"{count - state['unread']} new unread email(s); {count} unread in total.")
    state["unread"] = count
    _save(state)


def vehicles() -> None:
    """Remind as car tax/MOT/insurance/service dates approach (30, 14, 7, 3, 1, 0 days)."""
    if not _enabled("vehicles"):
        return
    state, today = _state(), date.today().isoformat()
    sent = state.get("vehicles", {})
    for name, item, due, left in vehicle_tool.due_items():
        key = f"{name}|{item}|{due.isoformat()}"
        if left in vehicle_tool.ALERT_DAYS and sent.get(key) != f"{today}":
            if sent.get(key, "")[:10] == today:
                continue
            label = "MOT" if item == "mot" else item
            when = "today" if left == 0 else f"in {left} day(s)"
            notify.notify("Car admin", f"{name} {label} is due {when} ({due.strftime('%d %b')}).",
                          speak=left <= 3, phone=True)
            sent[key] = today
    state["vehicles"] = {k: v for k, v in sent.items() if (date.fromisoformat(v) - date.today()).days > -400}
    _save(state)


def docs_changed() -> None:
    """Every few minutes: re-index only if files in the document folders were added, changed or removed."""
    folders = config.load().get("doc_folders")
    if not folders:
        return
    import docs_tool
    paths = list(docs_tool._walk(folders))
    fingerprint = [len(paths), max((os.path.getmtime(p) for p in paths), default=0), sum(os.path.getsize(p) for p in paths)]
    state = _state()
    if state.get("docs_fingerprint") == fingerprint:
        return
    first_run = "docs_fingerprint" not in state
    state["docs_fingerprint"] = fingerprint
    _save(state)
    if not first_run:  # the first sighting is the index already built by hand or at 03:00
        print("scheduler: documents changed, re-indexing", flush=True)
        docs_tool.build_index()


def reindex_documents() -> None:
    import docs_tool
    if config.load().get("doc_folders"):
        docs_tool.build_index()


# ---- loop -------------------------------------------------------------------------------------

PERIODIC = [  # (name, every N seconds, function)
    ("calendar", 300, calendar_soon),
    ("github", 1800, github_review),
    ("email", 600, new_email),
    ("vehicles", 3600, vehicles),
    ("docs", 600, docs_changed),
]


def _at(hhmm: str, key: str, fn, *args) -> None:
    """Run once per day at HH:MM (also if the Mac was asleep and wakes up within 2 hours after)."""
    now = datetime.now()
    try:
        target = now.replace(hour=int(hhmm[:2]), minute=int(hhmm[3:5]), second=0, microsecond=0)
    except ValueError:
        return
    state = _state()
    if state.get("daily", {}).get(key) == now.date().isoformat():
        return
    if 0 <= (now - target).total_seconds() <= 7200:
        state.setdefault("daily", {})[key] = now.date().isoformat()
        _save(state)
        fn(*args)


_running: set[str] = set()


def _spawn(name: str, fn, *args) -> None:
    """Run a job in its own thread so a slow one (calendar, IMAP) can never delay timers."""
    def runner():
        _running.add(name)
        try:
            fn(*args)
        except Exception as e:
            print(f"scheduler: {name} failed: {type(e).__name__}", flush=True)
        finally:
            _running.discard(name)
    threading.Thread(target=runner, name=f"job-{name}", daemon=True).start()


def _loop() -> None:
    last = {name: 0.0 for name, _, _ in PERIODIC}
    time.sleep(15)  # let the server finish starting
    while True:
        try:
            fire_timers()
            now = time.time()
            for name, every, fn in PERIODIC:
                if now - last[name] >= every and name not in _running:
                    last[name] = now
                    _spawn(name, fn)
            cfg = config.load()
            for kind, hhmm in cfg.get("briefings", {}).items():
                if kind in ("morning", "night"):
                    _at(hhmm, f"briefing-{kind}", _spawn, f"briefing-{kind}", briefing, kind)
            if cfg.get("doc_folders"):
                _at(cfg.get("doc_reindex_time", "03:00"), "reindex", _spawn, "reindex", reindex_documents)
        except Exception as e:
            print(f"scheduler error: {type(e).__name__}: {e}", flush=True)
        time.sleep(1)


def start() -> None:
    threading.Thread(target=_loop, name="scheduler", daemon=True).start()
