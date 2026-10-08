"""Mac status/control and music. Only a fixed set of safe actions; no arbitrary shell."""
import re
import shutil
import subprocess

from applescript import ScriptError, run

KEYWORDS = ["battery", "disk", "cpu", "memory usage", "volume", "open ", "launch", "uptime", "mac", "system",
            "music", "song", "play", "pause", "skip", "next track", "spotify", "playing", "track"]


def _sh(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()


def mac_status() -> str:
    """Battery, disk, uptime, volume and the busiest processes."""
    batt = _sh("pmset", "-g", "batt").splitlines()
    d = shutil.disk_usage("/")
    procs = _sh("ps", "-Ao", "pcpu,comm", "-r").splitlines()[1:6]
    names = [f"{p.split(None, 1)[1].rsplit('/', 1)[-1]} {p.split()[0]}%" for p in procs if p.strip()]
    try:
        vol = run('return output volume of (get volume settings)')
    except ScriptError:
        vol = "?"
    return "\n".join([
        "Battery: " + (batt[1].strip() if len(batt) > 1 else "no battery / " + (batt[0] if batt else "unknown")),
        f"Disk: {d.free / 1e9:.0f} GB free of {d.total / 1e9:.0f} GB",
        "Uptime: " + _sh("uptime").split(" up ", 1)[-1].split(",  ")[0],
        f"Volume: {vol}%",
        "Busiest processes: " + ", ".join(names),
    ])


def set_volume(percent: int) -> str:
    """Set output volume 0-100."""
    p = max(0, min(100, int(percent)))
    try:
        run("set volume output volume (item 1 of argv) as integer", str(p))
    except ScriptError as e:
        return f"ERROR: {e}"
    return f"Volume set to {p}%."


def open_app(name: str) -> str:
    """Open an installed application by name."""
    if not re.fullmatch(r"[\w .&+-]{1,60}", name):
        return "ERROR: That is not a valid app name."
    r = subprocess.run(["open", "-a", name], capture_output=True, text=True, timeout=15)
    return f"Opened {name}." if r.returncode == 0 else f"ERROR: No app called '{name}' found."


def _player() -> str | None:
    for app in ("Spotify", "Music"):
        if subprocess.run(["pgrep", "-x", app], capture_output=True).returncode == 0:
            return app
    return None


def music_control(action: str) -> str:
    """action: play, pause, toggle, next, previous, now_playing. Controls Spotify or Apple Music."""
    action = action.lower().strip()
    cmds = {"play": "play", "pause": "pause", "toggle": "playpause", "next": "next track", "previous": "previous track"}
    app = _player()
    if action == "now_playing":
        if not app:
            return "Nothing is playing (no music app is open)."
        try:
            return run('tell application "' + app + '" to return (name of current track) & " by " & (artist of current track)')
        except ScriptError:
            return "Nothing is playing right now."
    if action not in cmds:
        return "ERROR: action must be one of play, pause, toggle, next, previous, now_playing."
    app = app or "Music"
    try:
        run('tell application "' + app + '" to ' + cmds[action])
    except ScriptError as e:
        return f"ERROR: {e}"
    return f"{app}: {action} done."


def _t(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


TOOLS = [
    _t("mac_status", "Real battery, disk space, uptime, volume and busiest processes on this Mac."),
    _t("set_volume", "Set the Mac's output volume.", {"percent": {"type": "integer", "description": "0-100"}}, ["percent"]),
    _t("open_app", "Open an application on this Mac by name.", {"name": {"type": "string"}}, ["name"]),
    _t("music_control", "Control Spotify or Apple Music, or say what is playing.",
       {"action": {"type": "string", "enum": ["play", "pause", "toggle", "next", "previous", "now_playing"]}}, ["action"]),
]
FUNCTIONS = {f.__name__: f for f in (mac_status, set_volume, open_app, music_control)}
