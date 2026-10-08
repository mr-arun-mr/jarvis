"""Collects every tool module and decides which tools to offer for a given request."""
import apple_tool
import files_tool
import github_tool
import gmail_tool
import mac_tool
import memory_tool
import weather_tool
import web_tool
import whatsapp_tool

MODULES = [gmail_tool, whatsapp_tool, github_tool, apple_tool, weather_tool, mac_tool, files_tool,
           web_tool, memory_tool]

FUNCTIONS = {name: fn for m in MODULES for name, fn in m.FUNCTIONS.items()}

# Tools that change something. Refused once untrusted content (email, web, chat...) has been read in the same turn,
# so text hidden in a message or web page cannot make Jarvis act.
MUTATING = {"add_reminder", "add_note", "remember", "forget", "set_volume", "open_app", "music_control"}
UNTRUSTED = {"check_inbox", "list_whatsapp_chats", "read_whatsapp_chat", "github_notifications", "github_my_work",
             "web_search", "search_notes", "read_file", "find_files", "get_calendar_events", "list_reminders"}


def select_tools(user_texts: list[str]) -> list[dict]:
    """Offer only tool groups whose keywords appear in the recent user messages (all tools if none match)."""
    text = " ".join(user_texts).lower()
    chosen = [m for m in MODULES if any(k in text for k in m.KEYWORDS)]
    return [t for m in (chosen or MODULES) for t in m.TOOLS]
