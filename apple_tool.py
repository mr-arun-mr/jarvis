"""Calendar, Reminders and Notes via macOS apps (AppleScript).

Calendar is read-only. Reminders and Notes can read and create, never edit or delete.
Anything synced to macOS (iCloud, Google calendars added in Internet Accounts) shows up.
"""
from applescript import ScriptError, run

KEYWORDS = ["calendar", "meeting", "schedule", "event", "appointment", "agenda", "remind", "todo",
            "to-do", "task", "note", "today", "tomorrow", "week"]


def get_calendar_events(days_ahead: int = 1) -> str:
    """Events from the start of today through the next `days_ahead` days."""
    days_ahead = max(1, min(int(days_ahead), 14))
    script = """
set d0 to current date
set time of d0 to 0
set d1 to d0 + (""" + "(item 1 of argv) as integer" + """) * days
set out to {}
tell application "Calendar"
  repeat with c in calendars
    try
      set evs to (every event of c whose start date >= d0 and start date < d1)
      repeat with e in evs
        set end of out to ((start date of e) as string) & " | " & (summary of e) & " | " & (name of c)
      end repeat
    end try
  end repeat
end tell
set AppleScript's text item delimiters to linefeed
return out as text
"""
    try:
        out = run(script, str(days_ahead), timeout=90)
    except ScriptError as e:
        return f"ERROR: {e}"
    if not out:
        return f"No calendar events in the next {days_ahead} day(s)."
    lines = sorted(set(out.splitlines()))
    return f"{len(lines)} event(s) (start | title | calendar):\n" + "\n".join("- " + l for l in lines[:40])


def list_reminders(limit: int = 10) -> str:
    """Incomplete reminders."""
    limit = max(1, min(int(limit), 30))
    script = """
set out to {}
tell application "Reminders"
  repeat with r in (reminders whose completed is false)
    set end of out to name of r
    if (count of out) >= (item 1 of argv) as integer then exit repeat
  end repeat
end tell
set AppleScript's text item delimiters to linefeed
return out as text
"""
    try:
        out = run(script, str(limit))
    except ScriptError as e:
        return f"ERROR: {e}"
    return ("Open reminders:\n" + "\n".join("- " + l for l in out.splitlines())) if out else "No open reminders."


def add_reminder(title: str, minutes_from_now: int = 0) -> str:
    """Create a reminder (optionally due in N minutes)."""
    title = title.strip()[:200]
    if not title:
        return "ERROR: A reminder needs a title."
    script = """
set mins to (item 2 of argv) as integer
tell application "Reminders"
  if mins > 0 then
    make new reminder with properties {name:(item 1 of argv), due date:((current date) + mins * minutes)}
  else
    make new reminder with properties {name:(item 1 of argv)}
  end if
end tell
return "ok"
"""
    try:
        run(script, title, str(max(0, int(minutes_from_now))))
    except ScriptError as e:
        return f"ERROR: {e}"
    return f"Reminder created: {title}" + (f" (due in {int(minutes_from_now)} min)" if int(minutes_from_now) > 0 else "")


def search_notes(query: str, limit: int = 3) -> str:
    """Notes whose title contains the query, with the start of each body."""
    limit = max(1, min(int(limit), 5))
    script = """
set out to {}
tell application "Notes"
  repeat with n in (every note whose name contains (item 1 of argv))
    set b to plaintext of n
    if (count of b) > 400 then set b to (text 1 thru 400 of b)
    set end of out to (name of n) & " :: " & b
    if (count of out) >= (item 2 of argv) as integer then exit repeat
  end repeat
end tell
set AppleScript's text item delimiters to linefeed & "---" & linefeed
return out as text
"""
    try:
        out = run(script, query, str(limit))
    except ScriptError as e:
        return f"ERROR: {e}"
    return out.replace("\n\n", "\n") if out else f"No notes with '{query}' in the title."


def add_note(title: str, body: str = "") -> str:
    """Create a new note."""
    title = title.strip()[:150]
    if not title:
        return "ERROR: A note needs a title."
    script = """
tell application "Notes"
  make new note with properties {name:(item 1 of argv), body:(item 1 of argv) & "<br>" & (item 2 of argv)}
end tell
return "ok"
"""
    try:
        run(script, title, body[:4000])
    except ScriptError as e:
        return f"ERROR: {e}"
    return f"Note created: {title}"


def _t(name, desc, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


TOOLS = [
    _t("get_calendar_events", "Read the user's real calendar events from today through the next N days (read-only).",
       {"days_ahead": {"type": "integer", "description": "1 = today only, 2 = today and tomorrow, up to 14"}}),
    _t("list_reminders", "List the user's open reminders.", {"limit": {"type": "integer"}}),
    _t("add_reminder", "Create a reminder, optionally due in N minutes from now.",
       {"title": {"type": "string"}, "minutes_from_now": {"type": "integer", "description": "0 for no due time"}}, ["title"]),
    _t("search_notes", "Find the user's Apple Notes by title and show the start of each.",
       {"query": {"type": "string"}}, ["query"]),
    _t("add_note", "Create a new Apple Note.", {"title": {"type": "string"}, "body": {"type": "string"}}, ["title"]),
]
FUNCTIONS = {f.__name__: f for f in (get_calendar_events, list_reminders, add_reminder, search_notes, add_note)}
