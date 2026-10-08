"""Find files with Spotlight and read text files. Read-only, limited to the home folder.

Blocked: hidden folders (.ssh, .aws, .gnupg, ...), ~/Library, and anything that looks like a secret.
"""
import os
import re
import subprocess

KEYWORDS = ["file", "document", "folder", "downloaded", "download", "find my", "pdf", "spreadsheet", "read the"]

HOME = os.path.realpath(os.path.expanduser("~"))
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".ts", ".html", ".css", ".yaml", ".yml",
            ".toml", ".ini", ".xml", ".sh", ".java", ".c", ".cpp", ".go", ".rs", ".sql", ".tex", ".rtf"}
SECRET_NAME = re.compile(r"(\.env|id_rsa|id_ed25519|\.pem|\.key|\.p12|secret|credential|password|token|\.kdbx)", re.I)


def _blocked(path: str) -> str | None:
    rel = os.path.relpath(path, HOME)
    if rel.startswith(".."):
        return "outside your home folder"
    parts = rel.split(os.sep)
    if any(p.startswith(".") for p in parts):
        return "inside a hidden folder"
    if parts[0] == "Library":
        return "inside ~/Library"
    if SECRET_NAME.search(parts[-1]):
        return "it looks like a secret or credential file"
    if "node_modules" in parts or ".venv" in parts:
        return "inside a dependency folder"
    return None


def find_files(name: str, days: int = 0, limit: int = 8) -> str:
    """Search by (part of) file name. `days` limits to files changed in the last N days."""
    limit = max(1, min(int(limit), 20))
    name = name.replace('"', "").replace("\\", "").strip()
    if not name:
        return "ERROR: Give part of a file name."
    q = f'kMDItemDisplayName == "*{name}*"cd'
    if int(days) > 0:
        q += f" && kMDItemFSContentChangeDate >= $time.today(-{int(days)})"
    try:
        out = subprocess.run(["mdfind", "-onlyin", HOME, q], capture_output=True, text=True, timeout=20).stdout
    except subprocess.TimeoutExpired:
        return "ERROR: The search took too long."
    hits = [p for p in out.splitlines() if p and not _blocked(os.path.realpath(p)) and os.path.isfile(p)]
    hits.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    if not hits:
        return f"No files matching '{name}'."
    return f"{len(hits)} match(es), newest first:\n" + "\n".join("- " + p for p in hits[:limit])


def read_file(path: str, max_chars: int = 3000) -> str:
    """Read the start of a text file inside the home folder."""
    max_chars = max(200, min(int(max_chars), 8000))
    real = os.path.realpath(os.path.expanduser(path))
    why = _blocked(real)
    if why:
        return f"ERROR: Not allowed to read that file ({why})."
    if not os.path.isfile(real):
        return "ERROR: No such file."
    if os.path.splitext(real)[1].lower() not in TEXT_EXT:
        return "ERROR: Only plain-text files can be read (PDFs and Office files are not supported yet)."
    with open(real, "r", errors="replace") as f:
        text = f.read(max_chars + 1)
    return text[:max_chars] + ("\n[truncated]" if len(text) > max_chars else "")


def _t(name, desc, props, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required or []}}}


TOOLS = [
    _t("find_files", "Find the user's real files by name using Spotlight (read-only).",
       {"name": {"type": "string", "description": "Part of the file name"},
        "days": {"type": "integer", "description": "Only files changed in the last N days (0 = any time)"},
        "limit": {"type": "integer"}}, ["name"]),
    _t("read_file", "Read the start of a plain-text file in the home folder, e.g. to summarise it.",
       {"path": {"type": "string"}, "max_chars": {"type": "integer"}}, ["path"]),
]
FUNCTIONS = {"find_files": find_files, "read_file": read_file}
