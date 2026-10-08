"""Read-only GitHub access. Token lives in macOS Keychain (service 'jarvis-github')."""
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request

SERVICE = "jarvis-github"                      # fine-grained, read-only repo access
NOTIF_SERVICE = "jarvis-github-notifications"  # classic token, only the `notifications` scope
API = "https://api.github.com"


def _token(service: str) -> str | None:
    r = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _get(path: str, params: dict | None = None, service: str = SERVICE):
    token = _token(service)
    if not token:
        raise RuntimeError(f"GitHub is not set up. Run: security add-generic-password -s {service} -a github -w")
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("GitHub rejected the token. Check it is valid and has read access.")
        raise RuntimeError(f"GitHub API error {e.code}")


def github_notifications(limit: int = 8) -> str:
    """Unread GitHub notifications."""
    limit = max(1, min(int(limit), 20))
    try:
        items = _get("/notifications", {"per_page": limit}, NOTIF_SERVICE)
    except RuntimeError as e:
        if "rejected" in str(e):
            return ("ERROR: The notifications token was rejected. It must be a classic token with the 'notifications' scope, "
                    "stored as jarvis-github-notifications.")
        return f"ERROR: {e}"
    if not items:
        return "No unread GitHub notifications."
    lines = [f"{len(items)} unread notification(s):"]
    for n in items:
        s = n["subject"]
        lines.append(f"- {n['repository']['full_name']} | {s['type']} | {s['title']} | reason: {n['reason']}")
    return "\n".join(lines)


def github_my_work(limit: int = 5) -> str:
    """Open PRs waiting on the user's review, issues assigned to them, and their own open PRs."""
    limit = max(1, min(int(limit), 10))
    queries = {
        "Review requested": "is:open is:pr review-requested:@me",
        "Issues assigned to you": "is:open is:issue assignee:@me",
        "Your open PRs": "is:open is:pr author:@me",
    }
    try:
        out = []
        for label, q in queries.items():
            res = _get("/search/issues", {"q": q, "per_page": limit, "sort": "updated"})
            out.append(f"{label}: {res['total_count']}")
            for it in res["items"]:
                repo = it["repository_url"].split("/repos/")[-1]
                out.append(f"  - {repo}#{it['number']} {it['title']}")
        return "\n".join(out)
    except RuntimeError as e:
        return f"ERROR: {e}"


KEYWORDS = ['github', 'pull request', ' pr', 'review', 'issue', 'repo', 'notification', 'assigned']

TOOLS = [
    {"type": "function", "function": {
        "name": "github_notifications",
        "description": "Read the user's real unread GitHub notifications (read-only).",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Max items, up to 20 (default 8)"}}}}},
    {"type": "function", "function": {
        "name": "github_my_work",
        "description": "Summarise the user's GitHub work: PRs awaiting their review, issues assigned to them, and their open PRs (read-only).",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Max items per group, up to 10 (default 5)"}}}}},
]
FUNCTIONS = {"github_notifications": github_notifications, "github_my_work": github_my_work}
