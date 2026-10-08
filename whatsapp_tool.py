"""Read-only access to WhatsApp Desktop's local database (macOS).

Needs WhatsApp Desktop installed and linked, and Full Disk Access for whatever
process runs the server. Opens the database read-only; never writes or sends.
"""
import os
import sqlite3
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


def _when(apple_ts: float | None) -> str:
    if apple_ts is None:
        return "?"
    return datetime.fromtimestamp(apple_ts + APPLE_EPOCH).strftime("%a %d %b %H:%M")


def _clip(text: str | None) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "..."


def list_whatsapp_chats(unread_only: bool = True, limit: int = 8) -> str:
    """Most recent chats with unread counts and the last message."""
    limit = max(1, min(int(limit), 20))
    try:
        con = _connect()
    except Unavailable as e:
        return f"ERROR: {e}"
    with con:
        rows = con.execute(
            f"""SELECT ZPARTNERNAME, ZUNREADCOUNT, ZLASTMESSAGETEXT, ZLASTMESSAGEDATE, ZSESSIONTYPE
                FROM ZWACHATSESSION
                WHERE ZREMOVED = 0 AND ZSESSIONTYPE IN (0, 1) AND ZPARTNERNAME IS NOT NULL
                {'AND ZUNREADCOUNT > 0' if unread_only else ''}
                ORDER BY ZLASTMESSAGEDATE DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    if not rows:
        return "No unread WhatsApp chats." if unread_only else "No WhatsApp chats found."
    lines = [f"{len(rows)} WhatsApp chat(s), newest first:"]
    for name, unread, last, date, kind in rows:
        group = " (group)" if kind == 1 else ""
        lines.append(f"- {name}{group} | {unread or 0} unread | {_when(date)} | last: {_clip(last) or '[media]'}")
    return "\n".join(lines)


def read_whatsapp_chat(contact: str, limit: int = 10) -> str:
    """Latest messages from the chat whose name best matches `contact`."""
    limit = max(1, min(int(limit), 25))
    try:
        con = _connect()
    except Unavailable as e:
        return f"ERROR: {e}"
    with con:
        chat = con.execute(
            """SELECT Z_PK, ZPARTNERNAME FROM ZWACHATSESSION
               WHERE ZREMOVED = 0 AND ZSESSIONTYPE IN (0, 1) AND ZPARTNERNAME LIKE ?
               ORDER BY ZLASTMESSAGEDATE DESC LIMIT 1""",
            (f"%{contact}%",),
        ).fetchone()
        if not chat:
            return f"No WhatsApp chat matching '{contact}'."
        rows = con.execute(
            """SELECT ZISFROMME, ZPUSHNAME, ZTEXT, ZMESSAGETYPE, ZMESSAGEDATE
               FROM ZWAMESSAGE WHERE ZCHATSESSION = ?
               ORDER BY ZSORT DESC LIMIT ?""",
            (chat[0], limit),
        ).fetchall()
    lines = [f"Last {len(rows)} message(s) in chat '{chat[1]}', oldest first:"]
    for from_me, push, text, mtype, date in reversed(rows):
        who = "Me" if from_me else (push or chat[1])
        body = _clip(text) if text else f"[non-text message, type {mtype}]"
        lines.append(f"- {_when(date)} {who}: {body}")
    return "\n".join(lines)


KEYWORDS = ['whatsapp', 'chat', 'message', 'texted', 'text me', 'wrote to me']

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_whatsapp_chats",
            "description": "List the user's real WhatsApp chats (read-only), e.g. which chats have unread messages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "unread_only": {"type": "boolean", "description": "Only chats with unread messages (default true)"},
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
