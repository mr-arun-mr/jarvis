"""Movie info from TMDB (Malayalam, Tamil and other languages). Read-only.

Key in macOS Keychain (service 'jarvis-tmdb'): the "API Read Access Token" (long) or the v3 API key (32 hex chars).
This product uses the TMDB API but is not endorsed or certified by TMDB.
"""
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

SERVICE = "jarvis-tmdb"
API = "https://api.themoviedb.org/3"
KEYWORDS = ["movie", "film", "cinema", "release", "releasing", "malayalam", "tamil", "mollywood", "kollywood",
            "telugu", "ott", "stream", "actor", "actress", "director", "trailer", "box office", "theatre", "theater"]
LANGS = {"malayalam": "ml", "tamil": "ta", "telugu": "te", "hindi": "hi", "kannada": "kn", "english": "en",
         "ml": "ml", "ta": "ta", "te": "te", "hi": "hi", "kn": "kn", "en": "en"}


def _key() -> str | None:
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-w"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _get(path: str, **params):
    key = _key()
    if not key:
        raise RuntimeError("TMDB is not set up. Create a free key at themoviedb.org, then run: "
                           "security add-generic-password -s jarvis-tmdb -a tmdb -w")
    headers = {"Accept": "application/json", "User-Agent": "jarvis-assistant/1.0"}
    if len(key) == 32:
        params["api_key"] = key
    else:
        headers["Authorization"] = f"Bearer {key}"
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError("TMDB rejected the key." if e.code == 401 else f"TMDB error {e.code}.")
    except OSError:
        raise RuntimeError("TMDB is unreachable right now.")


def _lang(name: str) -> str:
    return LANGS.get(name.strip().lower(), name.strip().lower()[:2])


def movies_releasing(language: str = "malayalam", days_ahead: int = 30, days_back: int = 0, region: str = "IN") -> str:
    """Films in a language releasing between (today - days_back) and (today + days_ahead). Theatrical, by date."""
    days_ahead, days_back = max(0, min(int(days_ahead), 180)), max(0, min(int(days_back), 90))
    today = date.today()
    try:
        data = _get("/discover/movie", with_original_language=_lang(language), region=region,
                    **{"primary_release_date.gte": (today - timedelta(days=days_back)).isoformat(),
                       "primary_release_date.lte": (today + timedelta(days=days_ahead)).isoformat()},
                    sort_by="primary_release_date.asc", with_release_type="2|3", include_adult="false")
    except RuntimeError as e:
        return f"ERROR: {e}"
    films = data.get("results", [])[:15]
    if not films:
        return f"No {language} releases found in that window (TMDB may not list them yet)."
    out = [f"{language.title()} films, {today - timedelta(days=days_back)} to {today + timedelta(days=days_ahead)} "
           "(dates from TMDB, may change):"]
    for f in films:
        rating = f" | rated {f['vote_average']:.1f}" if f.get("vote_count", 0) >= 5 else ""
        out.append(f"- {f['release_date']} | {f['title']}{rating}")
    return "\n".join(out)


def popular_movies(language: str = "malayalam") -> str:
    """Currently popular films in a language."""
    try:
        data = _get("/discover/movie", with_original_language=_lang(language), sort_by="popularity.desc",
                    include_adult="false", **{"primary_release_date.gte": (date.today() - timedelta(days=365)).isoformat()})
    except RuntimeError as e:
        return f"ERROR: {e}"
    films = data.get("results", [])[:10]
    return (f"Popular {language.title()} films (past year):\n" + "\n".join(
        f"- {f['title']} ({f.get('release_date', '?')[:4]})" + (f" | rated {f['vote_average']:.1f}" if f.get("vote_count", 0) >= 5 else "")
        for f in films)) if films else "Nothing found."


def movie_info(title: str, year: int = 0) -> str:
    """Details for one film: plot, rating, director, cast, and where to stream (UK and India)."""
    try:
        params = {"query": title}
        if int(year):
            params["year"] = int(year)
        hits = _get("/search/movie", **params).get("results", [])
        if not hits:
            return f"No film found for '{title}'."
        m = _get(f"/movie/{hits[0]['id']}", append_to_response="credits,watch/providers")
    except RuntimeError as e:
        return f"ERROR: {e}"
    crew = m.get("credits", {}).get("crew", [])
    director = next((c["name"] for c in crew if c.get("job") == "Director"), "unknown")
    cast = ", ".join(c["name"] for c in m.get("credits", {}).get("cast", [])[:6])
    lines = [f"{m['title']} ({(m.get('release_date') or '?')[:4]}), language {m.get('original_language')}, "
             f"{m.get('runtime') or '?'} min, rated {m.get('vote_average', 0):.1f}/10 ({m.get('vote_count', 0)} votes)",
             f"Director: {director}. Cast: {cast or 'unknown'}.", (m.get("overview") or "No plot listed.")[:400]]
    prov = m.get("watch/providers", {}).get("results", {})
    for region, label in (("GB", "UK"), ("IN", "India")):
        names = [p["provider_name"] for p in prov.get(region, {}).get("flatrate", [])]
        lines.append(f"Streaming in {label}: {', '.join(names) if names else 'not listed'}")
    return "\n".join(lines)


def actor_movies(name: str, upcoming_only: bool = True) -> str:
    """Films for an actor or director: upcoming ones, or their latest releases."""
    try:
        people = _get("/search/person", query=name).get("results", [])
        if not people:
            return f"No person found for '{name}'."
        p = people[0]
        credits = _get(f"/person/{p['id']}/movie_credits")
    except RuntimeError as e:
        return f"ERROR: {e}"
    films = {f["id"]: f for f in credits.get("cast", []) + credits.get("crew", []) if f.get("release_date")}
    today = date.today().isoformat()
    rows = sorted(films.values(), key=lambda f: f["release_date"], reverse=not upcoming_only)
    rows = [f for f in rows if (f["release_date"] >= today) == upcoming_only][:10]
    if not rows:
        return f"No {'upcoming' if upcoming_only else 'recent'} films listed for {p['name']}."
    return f"{p['name']} - {'upcoming' if upcoming_only else 'latest'}:\n" + "\n".join(
        f"- {f['release_date']} | {f['title']}" for f in rows)


def _t(name, desc, props, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required or []}}}


TOOLS = [
    _t("movies_releasing", "Real film release schedule in a language (Malayalam, Tamil, Telugu, Hindi...). Use days_back for "
       "'now in cinemas' / 'recent releases' and days_ahead for upcoming ones.",
       {"language": {"type": "string"}, "days_ahead": {"type": "integer"}, "days_back": {"type": "integer"},
        "region": {"type": "string", "description": "Country code, default IN"}}),
    _t("popular_movies", "Popular films in a language.", {"language": {"type": "string"}}),
    _t("movie_info", "Details about one film: plot, rating, cast, director, streaming availability.",
       {"title": {"type": "string"}, "year": {"type": "integer"}}, ["title"]),
    _t("actor_movies", "Upcoming or latest films of an actor or director.",
       {"name": {"type": "string"}, "upcoming_only": {"type": "boolean"}}, ["name"]),
]
FUNCTIONS = {f.__name__: f for f in (movies_releasing, popular_movies, movie_info, actor_movies)}
