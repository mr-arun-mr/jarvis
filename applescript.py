"""Small helper for running AppleScript with arguments passed safely (no string interpolation)."""
import subprocess
import time


class ScriptError(Exception):
    pass


def run(script: str, *args: str, timeout: int = 40) -> str:
    """Run an AppleScript whose body is the contents of `on run argv ... end run`."""
    full = "on run argv\n" + script + "\nend run"
    for attempt in range(2):
        try:
            r = subprocess.run(["osascript", "-e", full, *args], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ScriptError("The app took too long to respond (it may be waiting for a permission prompt).")
        if r.returncode == 0 or "-609" not in r.stderr or attempt:
            break
        time.sleep(2)  # app was still starting up; macOS drops the first connection
    if r.returncode:
        err = r.stderr.strip()
        if "-1743" in err or "not allowed" in err.lower():
            raise ScriptError(
                "macOS blocked access. Allow it in System Settings > Privacy & Security > Automation."
            )
        raise ScriptError(err or "AppleScript failed.")
    return r.stdout.strip()
