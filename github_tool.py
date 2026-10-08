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
    for attempt in range(2):  # one retry: GitHub occasionally drops the TLS connection
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError("GitHub rejected the token. Check it is valid and has read access.")
            raise RuntimeError(f"GitHub API error {e.code}")
        except OSError:
            if attempt:
                raise RuntimeError("GitHub is unreachable right now.")


def _unread() -> list[dict]:
    """Up to 100 unread notifications (GitHub's page maximum)."""
    return _get("/notifications", {"per_page": 100}, NOTIF_SERVICE)


def _split(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(people-driven notifications, automated CI alerts). CI alerts are build-failure noise."""
    ci = [n for n in items if n["reason"] == "ci_activity"]
    return [n for n in items if n["reason"] != "ci_activity"], ci


def _describe(items: list[dict], limit: int) -> list[str]:
    groups: dict[str, int] = {}
    for n in items:
        key = f"{n['repository']['full_name']} | {n['subject']['type']} | {n['subject']['title']} | reason: {n['reason']}"
        groups[key] = groups.get(key, 0) + 1
    rows = [f"- {c} x {k}" if c > 1 else f"- {k}" for k, c in sorted(groups.items(), key=lambda kv: -kv[1])[:limit]]
    if len(groups) > limit:
        rows.append(f"(and {len(groups) - limit} more)")
    return rows


def github_notifications(limit: int = 8, include_ci: bool = False) -> str:
    """Unread notifications from people: mentions, review requests, assignments, comments. CI failures are summarised."""
    limit = max(1, min(int(limit), 20))
    try:
        items = _unread()
    except RuntimeError as e:
        if "rejected" in str(e):
            return ("ERROR: The notifications token was rejected. It must be a classic token with the 'notifications' scope, "
                    "stored as jarvis-github-notifications.")
        return f"ERROR: {e}"
    people, ci = _split(items)
    cap = "+" if len(items) >= 100 else ""
    lines = []
    if people:
        lines.append(f"The user has {len(people)}{cap} unread GitHub notification(s) from people or assignments:")
        lines += _describe(people, limit)
    else:
        lines.append("No unread GitHub notifications from people (no mentions, reviews, assignments or comments).")
    if ci:
        repos = sorted({n["repository"]["full_name"] for n in ci})
        lines.append(f"Separately, {len(ci)}{cap} automated CI build-failure alerts are unread, from: {', '.join(repos)}.")
        if include_ci:
            lines += _describe(ci, limit)
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
        try:  # needs the separate notifications token; skip quietly if it is not set up
            people, ci = _split(_unread())
            out.append(f"Unread notifications from people: {len(people)}; automated CI failure alerts: {len(ci)}")
        except RuntimeError:
            pass
        return "\n".join(out)
    except RuntimeError as e:
        return f"ERROR: {e}"


KEYWORDS = ['github', 'pull request', ' pr', 'review', 'issue', 'repo', 'notification', 'assigned']

TOOLS = [
    {"type": "function", "function": {
        "name": "github_notifications",
        "description": "Read the user's real unread GitHub notifications (read-only): mentions, reviews, assignments. CI build failures are summarised separately.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Max items, up to 20 (default 8)"},
            "include_ci": {"type": "boolean", "description": "Also list the CI build-failure alerts (only if the user asks about CI or builds)"}}}}},
    {"type": "function", "function": {
        "name": "github_my_work",
        "description": "Summarise the user's GitHub work: PRs awaiting their review, issues assigned to them, and their open PRs (read-only).",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Max items per group, up to 10 (default 5)"}}}}},
]
FUNCTIONS = {"github_notifications": github_notifications, "github_my_work": github_my_work}
