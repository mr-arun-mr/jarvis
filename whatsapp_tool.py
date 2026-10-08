"""Read-only access to WhatsApp Desktop's local database (macOS).

Needs WhatsApp Desktop installed and linked, and Full Disk Access for whatever
process runs the server. Opens the database read-only; never writes or sends.
"""
import os
import re
import sqlite3
import time
from datetime import datetime

DB = os.path.expanduser(
    "~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite"
)
APPLE_EPOCH = 978307200  # WhatsApp stores seconds since 2001-01-01
MAX_TEXT = 300


class Unavailable(Exception):
    pass


def _connect() -> sqlite3.Connection:
    if not os.path.exists(DB):
        raise Unavailable("WhatsApp Desktop data not found. Install and link WhatsApp Desktop first.")
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
        con.execute("select 1 from ZWAMESSAGE limit 1")
        return con
    except sqlite3.OperationalError as e:
        raise Unavailable(
            "Cannot read the WhatsApp database. Grant Full Disk Access to the Python "
            f"that runs Jarvis (System Settings > Privacy & Security). Detail: {e}"
        )


REAL_TYPES = (0, 1, 2, 3, 4, 5, 7, 8, 14, 15)  # text, photo, video, voice, contact, location, link, document, ...
LABELS = {1: "[photo]", 2: "[video]", 3: "[voice note]", 4: "[contact]", 5: "[location]", 8: "[document]", 15: "[sticker]"}
_IN = ",".join(map(str, REAL_TYPES))


def _when(apple_ts: float | None) -> str:
    try:
        return datetime.fromtimestamp(apple_ts + APPLE_EPOCH).strftime("%a %d %b %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"  # some chats store a malformed timestamp


def _clip(text: str | None) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "..."


_BLOB = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")


def _is_blob(t: str) -> bool:
    return bool(_BLOB.fullmatch(t)) and any(c.isdigit() for c in t) and any(c.islower() for c in t) and any(c.isupper() for c in t)


def _sender(push: str | None, chat: str, is_group: bool) -> str:
    """Sender name. WhatsApp sometimes stores an encoded blob as the display name; fall back to the chat name
    for one-to-one chats and to 'Someone' in groups."""
    if push and not _is_blob(push.strip()):
        return push.strip()
    return "Someone" if is_group else chat


def _body(text: str | None, mtype: int) -> str:
    """Message text, or a label when there is none or it is an undecoded payload (e.g. a sticker stored as base64)."""
    t = (text or "").strip()
    if t and _is_blob(t):
        return "[unreadable message: probably a sticker or emoji WhatsApp could not decode]"
    return _clip(text) or LABELS.get(mtype, "[media]")


def list_whatsapp_chats(hours: int = 24, limit: int = 8) -> str:
    """Chats that received new messages in the last `hours` hours, newest first.

    WhatsApp Desktop is a linked device and does not know what you have read on your phone, so this reports
    activity, not 'unread'."""
    hours, limit = max(1, min(int(hours), 24 * 30)), max(1, min(int(limit), 20))
    since = time.time() - APPLE_EPOCH - hours * 3600
    try:
        con = _connect()
    except Unavailable as e:
        return f"ERROR: {e}"
    with con:
        rows = con.execute(
            f"""SELECT s.ZPARTNERNAME, s.ZSESSIONTYPE, COUNT(*) AS n, MAX(m.ZMESSAGEDATE) AS newest, s.Z_PK
                FROM ZWAMESSAGE m JOIN ZWACHATSESSION s ON s.Z_PK = m.ZCHATSESSION
                WHERE s.ZREMOVED = 0 AND s.ZSESSIONTYPE IN (0, 1) AND s.ZPARTNERNAME IS NOT NULL
                  AND m.ZISFROMME = 0 AND m.ZMESSAGETYPE IN ({_IN}) AND m.ZMESSAGEDATE >= ?
                GROUP BY s.Z_PK ORDER BY newest DESC LIMIT ?""",
            (since, limit),
        ).fetchall()
        if not rows:
            return f"No new WhatsApp messages in the last {hours} hour(s)."
        lines = [f"{len(rows)} chat(s) with new incoming messages in the last {hours} hour(s), newest first "
                 "(this cannot tell what you already read on your phone):"]
        for name, kind, n, newest, pk in rows:
            last = con.execute(
                f"""SELECT ZTEXT, ZMESSAGETYPE FROM ZWAMESSAGE WHERE ZCHATSESSION = ? AND ZISFROMME = 0
                    AND ZMESSAGETYPE IN ({_IN}) ORDER BY ZMESSAGEDATE DESC LIMIT 1""", (pk,)).fetchone()
            group = " (group)" if kind == 1 else ""
            lines.append(f"- {name}{group} | {n} new | latest {_when(newest)} | {_body(*last) if last else ''}")
    return "\n".join(lines)


def read_whatsapp_chat(contact: str, limit: int = 10) -> str:
    """Latest messages from the chat whose name best matches `contact`."""
    limit = max(1, min(int(limit), 25))
    try:
        con = _connect()
    except Unavailable as e:
        return f"ERROR: {e}"
    with con:
        chats = con.execute(
            """SELECT s.Z_PK, s.ZPARTNERNAME, (SELECT MAX(ZMESSAGEDATE) FROM ZWAMESSAGE WHERE ZCHATSESSION = s.Z_PK) AS newest, s.ZSESSIONTYPE
               FROM ZWACHATSESSION s
               WHERE s.ZREMOVED = 0 AND s.ZSESSIONTYPE IN (0, 1) AND s.ZPARTNERNAME LIKE ?
               ORDER BY newest DESC LIMIT 3""", (f"%{contact}%",)).fetchall()
        if not chats:
            return f"No WhatsApp chat matching '{contact}'."
        chat = chats[0]
        rows = con.execute(
            f"""SELECT ZISFROMME, ZPUSHNAME, ZTEXT, ZMESSAGETYPE, ZMESSAGEDATE FROM ZWAMESSAGE
                WHERE ZCHATSESSION = ? AND ZMESSAGETYPE IN ({_IN}) ORDER BY ZMESSAGEDATE DESC LIMIT ?""",
            (chat[0], limit)).fetchall()
    others = f" (other matches: {', '.join(c[1] for c in chats[1:])})" if len(chats) > 1 else ""
    lines = [f"Last {len(rows)} message(s) in chat '{chat[1]}'{others}, oldest first:"]
    for from_me, push, text, mtype, date in reversed(rows):
        lines.append(f"- {_when(date)} {'Me' if from_me else _sender(push, chat[1], chat[3] == 1)}: {_body(text, mtype)}")
    return "\n".join(lines)


KEYWORDS = ['whatsapp', 'chat', 'message', 'texted', 'text me', 'wrote to me']

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_whatsapp_chats",
            "description": "Which of the user's real WhatsApp chats received new messages recently (read-only). Cannot tell what was read on the phone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "Look back this many hours (default 24)"},
                    "limit": {"type": "integer", "description": "How many chats, max 20 (default 8)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_whatsapp_chat",
            "description": "Read the latest messages from one WhatsApp chat, found by contact or group name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact": {"type": "string", "description": "Contact or group name (partial match)"},
                    "limit": {"type": "integer", "description": "How many messages, max 25 (default 10)"},
                },
                "required": ["contact"],
            },
        },
    },
]
FUNCTIONS = {"list_whatsapp_chats": list_whatsapp_chats, "read_whatsapp_chat": read_whatsapp_chat}
