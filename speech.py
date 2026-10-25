"""Spoken output through macOS `say`, one voice at a time.

server.py (timers, briefings, alerts) and wake.py (replies) are separate processes that both speak, so they take
turns through a file lock instead of talking over each other.
"""
import fcntl
import os
import subprocess
import tempfile
import threading

LOCK_PATH = os.path.join(tempfile.gettempdir(), f"jarvis-speech-{os.getuid()}.lock")


def say(text: str, voice: str) -> None:
    """Speak and wait until finished. Blocks while anything else is speaking."""
    with open(LOCK_PATH, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            subprocess.run(["say", "-v", voice, text])
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def say_async(text: str, voice: str) -> None:
    """Queue speech without blocking the caller; it still waits its turn."""
    threading.Thread(target=say, args=(text, voice), name="speech", daemon=True).start()
