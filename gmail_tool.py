"""Read-only Gmail access over IMAP. Credentials live in macOS Keychain (service 'jarvis-gmail')."""
import email
import imaplib
import re
import subprocess
from email.header import decode_header, make_header

SERVICE = "jarvis-gmail"


class NotConfigured(Exception):
    pass


def _credentials() -> tuple[str, str]:
    base = ["security", "find-generic-password", "-s", SERVICE]
    meta = subprocess.run(base, capture_output=True, text=True)
    pw = subprocess.run(base + ["-w"], capture_output=True, text=True)
    m = re.search(r'"acct"<blob>="([^"]+)"', meta.stdout)
    if meta.returncode or pw.returncode or not m:
        raise NotConfigured(
            "Gmail is not set up. Run: security add-generic-password -s jarvis-gmail -a YOUR_ADDRESS -w"
        )
    return m.group(1), pw.stdout.strip()


def _decode(value: str | None) -> str:
    return str(make_header(decode_header(value or ""))).strip()


def check_inbox(unread_only: bool = True, limit: int = 5) -> str:
    """Return the newest messages (sender, subject, date). Never marks anything read."""
    limit = max(1, min(int(limit), 15))
    try:
        user, password = _credentials()
        box = imaplib.IMAP4_SSL("imap.gmail.com")
        box.login(user, password)
    except NotConfigured as e:
        return f"ERROR: {e}"
    except imaplib.IMAP4.error:
        return "ERROR: Gmail rejected the login. Check the app password and that IMAP is enabled."
    try:
        box.select("INBOX", readonly=True)
        _, data = box.search(None, "UNSEEN" if unread_only else "ALL")
        ids = data[0].split()
        if not ids:
            return "No unread messages." if unread_only else "The inbox is empty."
        lines = [f"{len(ids)} {'unread ' if unread_only else ''}message(s). Newest {min(limit, len(ids))}:"]
        for num in reversed(ids[-limit:]):
            _, msg = box.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            h = email.message_from_bytes(msg[0][1])
            lines.append(f"- From {_decode(h['From'])} | {_decode(h['Subject']) or '(no subject)'} | {h['Date']}")
        return "\n".join(lines)
    finally:
        box.logout()


KEYWORDS = ['email', 'e-mail', 'mail', 'inbox', 'unread', 'gmail']

TOOLS = [{
    "type": "function",
    "function": {
        "name": "check_inbox",
        "description": "Read the user's real Gmail inbox (read-only). Use for any question about their email.",
        "parameters": {
            "type": "object",
            "properties": {
                "unread_only": {"type": "boolean", "description": "Only unread messages (default true)"},
                "limit": {"type": "integer", "description": "How many messages to list, max 15 (default 5)"},
            },
        },
    },
}]
FUNCTIONS = {"check_inbox": check_inbox}
