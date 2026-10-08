# Jarvis

A local AI assistant for macOS. The language model runs on your machine through [Ollama](https://ollama.com). There is a sci-fi HUD in the browser with voice and text input, a "Hey Jarvis" wake-word listener, a background scheduler for timers, briefings and alerts, and tools that give it real data from your Mac and accounts.

What leaves your machine, and only when you use that feature:
- **Chrome voice input** sends mic audio to Google for transcription (Safari differs). The model itself stays local.
- **Gmail** connects to `imap.gmail.com`; **GitHub** to `api.github.com`; **movies** to `api.themoviedb.org`.
- **Weather** sends a city name to Open-Meteo; **currency conversion** sends currency codes to Frankfurter; **web search** sends your query to DuckDuckGo.
- **Phone push** (optional) sends alert titles and short text to ntfy.sh, or your own ntfy server.

This product uses the TMDB API but is not endorsed or certified by TMDB.

## Setup checklist (in order)

1. **Install and pull models**: follow "Local setup" below (Homebrew packages, three Ollama models, Python venv).
2. **Create your config**: `cp config.example.json config.json`, then set `default_city`, and check `briefings` times (remove the key to disable spoken briefings).
3. **Start the server and sign in**: `server.py`, then open the link from `server.py --print-url` once per browser.
4. **Connect accounts (each optional)**: Gmail, GitHub (two tokens), TMDB movies, WhatsApp Desktop. See "Account setup".
5. **Grant macOS permissions**: Automation (Calendar, Reminders, Notes, Music), Screen Recording, Microphone. See "Account setup".
6. **Index your documents (optional)**: set `doc_folders` in `config.json`, run `docs_tool.py index`.
7. **Add car dates (optional)**: say "set my car MOT date to 2027-05-10", or edit `vehicles` in `config.json`.
8. **Test the wake word (optional)**: `wake.py --test`, then enable its LaunchAgent.
9. **Run at login**: install the LaunchAgent so the server (and scheduler) start automatically.
10. **Phone access and phone alerts (optional)**: Tailscale and ntfy sections.

Everything marked optional is off until configured; Jarvis answers with a clear "not set up" message if you ask for it anyway.

## What it can do

| Tool | What it does | Access |
|---|---|---|
| `check_inbox` | Unread Gmail: sender, subject, date | read-only |
| `list_whatsapp_chats`, `read_whatsapp_chat` | WhatsApp Desktop: chats with new messages in the last N hours (cannot tell what you read on your phone); latest messages of one chat | read-only |
| `github_my_work`, `github_notifications` | PRs awaiting review, assigned issues, your PRs, notifications | read-only |
| `get_calendar_events` | Events from today through N days | read-only |
| `list_reminders`, `add_reminder` | Open reminders; create one | read + create |
| `search_notes`, `add_note` | Find Apple Notes by title; create a note | read + create |
| `get_weather`, `get_time` | Forecast (your default city unless you name one); time anywhere | read-only |
| `calculate`, `convert` | Exact arithmetic; units and live currency rates | read-only |
| `set_timer`, `set_alarm`, `list_timers`, `cancel_timer` | Countdown timers and clock alarms that speak when due | local |
| `get_briefing` | Spoken summary of your day (morning or night) | read-only |
| `vehicle_status`, `set_vehicle_date` | Car tax, MOT, insurance and service due dates | local file |
| `movies_releasing`, `popular_movies`, `movie_info`, `actor_movies` | Malayalam, Tamil and other-language film releases, details, streaming | read-only |
| `search_documents` | Semantic search over folders you choose (PDF, Word, text) | read-only |
| `read_clipboard`, `describe_screen` | Read what you copied; look at your screen with a local vision model | read-only |
| `mac_status`, `set_volume`, `open_app` | Battery, disk, uptime, processes; volume; open an app | fixed safe actions |
| `music_control` | Play, pause, next, previous, what's playing | control |
| `find_files`, `read_file` | Spotlight search; read plain-text files in your home folder | read-only |
| `web_search` | Web and news search | read-only |
| `remember`, `forget` | Long-term facts, shown to the model on every request | local file |

Nothing can send email or WhatsApp messages, edit or delete calendar events, notes or files, or run arbitrary shell commands.

### Safety rules built in
- **Outside content is data.** Emails, messages, web pages, notes, documents, the clipboard and the screen can contain text trying to give the model orders. The system prompt says to ignore it, and the code also refuses any state-changing tool (`add_*`, `remember`, `forget`, timers, volume, open app, music, vehicle dates) after reading such content in the same turn.
- **Files:** hidden folders (`.ssh`, `.aws`, ...), `~/Library`, anything outside your home folder, and files that look like secrets cannot be read or indexed.
- **Tool selection:** only tool groups matching your message are offered to the model (all if none match), which keeps it accurate.
- **The HUD server refuses outsiders.** It holds access to your mail and files, so it checks the Host header (blocks DNS rebinding), the Origin header (blocks other websites posting to it), and requires a secret access key held in a cookie. See "Sign in" below.

## Files

| File | Purpose |
|---|---|
| `server.py` | HTTP server: HUD, chat streaming, alert feed, security checks; starts the scheduler. |
| `static/index.html` | The HUD (orb, transcript, mic, voice, language picker, alerts). |
| `scheduler.py` | Background jobs: timers, briefings, calendar/PR/email/car alerts, document re-indexing. |
| `notify.py` | Delivery: Mac notification, speech (respecting quiet hours), HUD feed, optional phone push. |
| `wake.py` | "Hey Jarvis" listener that works without the browser. |
| `brain.py` | Shared core: prompt, memory, language, tool selection, tool-calling loop. |
| `registry.py` | Collects all tool modules; marks which tools change things or return outside content. |
| `*_tool.py` | One module per tool group (gmail, whatsapp, github, apple, weather, mac, files, web, memory, calc, timer, screen, vehicle, tmdb, docs, briefing). |
| `applescript.py` | Safe AppleScript runner (arguments never string-interpolated; retries a macOS startup glitch). |
| `config.py`, `config.example.json` | Settings loader and a template. Copy the template to `config.json` (git-ignored). |
| `jarvis.py` | Original terminal version (voice or `--text`). No tools. |
| `launchd/*.plist.example` | Login-service templates. |

Git-ignored local state: `config.json` (your settings, city, car dates), `memory.json`, `timers.json`, `alerts_state.json`, `docs_index.*` (contains text from your documents), `.access_key`.

## Local setup

macOS on Apple Silicon (tested), with [Homebrew](https://brew.sh).

```bash
brew install ollama ffmpeg portaudio python@3.12
brew services start ollama
ollama pull qwen2.5:14b          # main model (~9 GB)
ollama pull qwen2.5vl:7b         # vision, for describe_screen (~6 GB)
ollama pull nomic-embed-text     # embeddings, for document search (~0.3 GB)

cd ~/jarvis
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "from openwakeword import utils; utils.download_models(model_names=['hey_jarvis'])"
cp config.example.json config.json     # then edit it
```

Python 3.12 is used on purpose: several speech packages have no wheels for the newest Python (e.g. 3.14). The venv keeps it separate from your system Python.

## Run it and sign in

```bash
cd ~/jarvis && .venv/bin/python server.py
```

The server needs a one-time sign-in per browser. Print your private link and open it once (it sets a cookie and redirects):

```bash
cd ~/jarvis && .venv/bin/python server.py --print-url
```

Treat that link like a password. To invalidate every browser, delete `.access_key` and restart the server.

In the HUD: **Listen** keeps the mic open; **Voice** mutes replies; the language box switches between English, മലയാളം and தமிழ்; the text box always works. Alerts, timers and briefings appear in green in the transcript.

### Wake word ("Hey Jarvis")

```bash
cd ~/jarvis && .venv/bin/python wake.py --test   # prints scores when it hears the wake word
cd ~/jarvis && .venv/bin/python wake.py          # the real thing
```

After the wake word you hear a tick, speak, and pause. macOS asks for microphone access for your terminal on first use. For Malayalam or Tamil speech set `"wake_stt_model": "large-v3-turbo"` and `"wake_language": "ml"` (or `"auto"`) in `config.json`. To run it at login, once the manual test works:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.arun.jarvis.wake.plist
```

Background services may not get microphone permission automatically; if `wake.log` shows silence or errors, run it from Terminal instead.

## Account setup

Credentials live in macOS Keychain; never in this folder, and never in notes or chat.

**Gmail (read-only).** Turn on 2-Step Verification, create an app password at <https://myaccount.google.com/apppasswords>, then:

```bash
security add-generic-password -U -s jarvis-gmail -a YOUR_ADDRESS@gmail.com -w
```

**GitHub (read-only), two tokens so each has the least access.**

```bash
security add-generic-password -U -s jarvis-github -a github -w                 # fine-grained: read Metadata, Issues, Pull requests
security add-generic-password -U -s jarvis-github-notifications -a github -w   # classic, ONLY the "notifications" scope
```

Create them at <https://github.com/settings/personal-access-tokens/new> and <https://github.com/settings/tokens/new>. Fine-grained tokens cannot read notifications, which is why the second token exists. Do not tick `repo` or `workflow` on it.

**Movies (TMDB).** Create a free account at <https://www.themoviedb.org>, request an API key under Settings → API, and store the "API Read Access Token":

```bash
security add-generic-password -U -s jarvis-tmdb -a tmdb -w
```

**WhatsApp.** Install WhatsApp Desktop (`brew install --cask whatsapp`), link it from your phone (Settings → Linked Devices), and let it sync. Jarvis reads its local database read-only. The format is undocumented and may break after updates; it holds only what the Mac has synced.

**macOS permissions** (System Settings → Privacy & Security). The first use of each triggers a prompt:
- **Automation:** allow Python to control Calendar, Reminders, Notes, Music/Spotify.
- **Screen & System Audio Recording:** needed by `describe_screen`. Add the real Python binary, `/opt/homebrew/Cellar/python@3.12/<version>/Frameworks/Python.framework/Versions/3.12/Resources/Python.app`, and restart the service.
- **Microphone:** for the terminal or app that runs `wake.py`.

**Remove a credential:** `security delete-generic-password -s jarvis-gmail` (or `jarvis-github`, `jarvis-github-notifications`, `jarvis-tmdb`).

Facebook and Instagram are not supported: Meta has no API for personal accounts, and scraping would break their terms.

## Scheduler, briefings and alerts

`scheduler.py` runs inside the server (so the server must be running; it starts at login). Each check runs in its own thread, so a slow one never delays a timer.

| What | When | How you're told |
|---|---|---|
| Timers and alarms | when due | spoken + notification |
| Morning / night briefing | `briefings` times (default 07:30 / 21:30) | spoken + notification |
| Calendar event starting | within 10 minutes, checked every 5 min | spoken + notification |
| New PR awaiting your review | every 30 min | notification |
| New unread email | every 10 min (count only, no content) | notification |
| Car tax / MOT / insurance / service | at 30, 14, 7, 3, 1, 0 days | notification (spoken within 3 days) |
| New or changed documents re-indexed | every 10 min, plus nightly at 03:00 | silent |

Speech is suppressed during quiet hours (default 23:00 to 07:00); timers are urgent and still speak. A briefing missed because the Mac was asleep runs when it wakes, up to 2 hours late. A briefing reads your calendar, reminders, email senders and GitHub aloud, so remove the `briefings` key if others may be in earshot.

### Car dates

Set them by talking ("set my car MOT date to 2027-05-10") or in `config.json` under `vehicles`. UK DVLA/MOT lookups need an approved API key, so dates are entered by you.

### Documents

Add folders to `config.json` (`doc_folders`, optional `doc_exclude` folder names such as `github`, and `doc_extensions`), then build the index once:

```bash
cd ~/jarvis && .venv/bin/python docs_tool.py index
```

After that the scheduler picks up new, changed and deleted files within about 10 minutes. Only documents are indexed (PDF, Word, text, Markdown, RTF, CSV); scanned PDFs with no text layer are skipped. Everything stays on your Mac.

### Phone alerts (optional)

For notifications on your phone, install the ntfy app, subscribe to a long random topic, and add to `config.json`:

```json
"phone": {"ntfy_topic": "your-long-random-topic"}
```

Anyone who knows the topic can read the alerts, so use a random one and keep sensitive details out of alerts. Voice calls are not implemented.

## Using Jarvis from your phone

Not set up by default. The private way is Tailscale, which links your Mac and phone into an encrypted network that only your own devices can join:

1. Install Tailscale on the Mac and the phone and sign in with the same account (this is how it knows both devices are yours).
2. In the Tailscale admin console enable MagicDNS and HTTPS certificates (phone browsers only allow the microphone over HTTPS).
3. On the Mac: `tailscale serve --bg 8765`. Note the `https://<mac>.<tailnet>.ts.net` address it prints.
4. Add that host name (no `https://`) to `allowed_hosts` in `config.json`, restart the server, then on the phone open the address with `/?key=...` from `--print-url`.

Do not forward a router port or use a public tunnel: the server is protected by a single key and was designed for private use. This path has not been tested end to end.

## Languages

The language picker uses Chrome's speech recognition for Malayalam and Tamil, and shows replies in that script. Honest limits:
- `qwen2.5:14b` understands Malayalam and Tamil only roughly and writes them poorly (wrong words, odd phrasing). English is far more reliable.
- macOS has a Tamil voice (Vani) but **no Malayalam voice**; Malayalam replies are shown on screen (and as a notification in wake mode), not spoken.
- Whisper's Malayalam accuracy varies; `large-v3-turbo` is the better choice for `wake.py`.

## Run at startup

Templates are in `launchd/`. Install them with your home path filled in. The `com.arun.*` label is just a name; if you pick a different one, substitute it in every command below:

```bash
mkdir -p ~/Library/Logs/jarvis
sed "s#__HOME__#$HOME#g" launchd/com.arun.jarvis.plist.example > ~/Library/LaunchAgents/com.arun.jarvis.plist
sed "s#__HOME__#$HOME#g" launchd/com.arun.jarvis.wake.plist.example > ~/Library/LaunchAgents/com.arun.jarvis.wake.plist
```

- `com.arun.jarvis`: runs `server.py` (and the scheduler) at login and restarts it if it crashes.
- `com.arun.jarvis.wake`: runs `wake.py` the same way (leave off until you've tested the mic).

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.arun.jarvis.plist      # enable
launchctl bootout gui/$(id -u)/com.arun.jarvis                                      # disable
launchctl kickstart -k gui/$(id -u)/com.arun.jarvis                                 # restart after code changes
launchctl print gui/$(id -u)/com.arun.jarvis | grep -E "state|pid"                  # status
tail -f ~/Library/Logs/jarvis/server.log                                            # logs (tool calls show as "tool: name")
```

Use the `.wake` label and `wake.log` for the listener. The server runs in the background but doesn't open a browser tab, and browser voice only works while the HUD tab is open. The wake listener doesn't need the browser. Ollama starts separately through `brew services`.

## Configuration

`config.json` keys (all optional; see `config.example.json`): `default_city`, `model`, `vision_model`, `briefings`, `alerts` (`quiet_start`, `quiet_end`, and on/off for `calendar`, `github`, `email`, `vehicles`), `vehicles`, `doc_folders`, `doc_exclude`, `doc_extensions`, `doc_reindex_time`, `allowed_hosts`, `phone`, `wake_stt_model`, `wake_language`.

| Setting | Where | Default |
|---|---|---|
| Model | `JARVIS_MODEL` env var, or `model` in `config.json` | `qwen2.5:14b` |
| Port | `JARVIS_PORT` env var | `8765` |
| Personality and rules | `SYSTEM` in `brain.py` | concise, witty, plain text |
| Wake word and sensitivity | `wakeword_models`, `THRESHOLD` in `wake.py` | `hey_jarvis`, `0.5` |
| Spoken voice | `VOICE` in `wake.py` and `notify.py` (list with `say -v '?'`) | `Daniel` |

After editing any `.py` file or `config.json`, restart with the `kickstart` command. The LaunchAgent does not read your shell profile; to set `JARVIS_MODEL` or `JARVIS_PORT` for it, add an `EnvironmentVariables` dict to the plist.

Model advice: it must support tool-calling. `qwen2.5:14b` is reliable for tools; if it ever writes a tool call as plain text, `brain.py` recovers it. With 48 GB RAM a larger model is possible but slower.

## Adding a tool

Make a module with `TOOLS` (JSON schemas), `FUNCTIONS` (name to function) and `KEYWORDS` (words that should offer it), import it in `registry.py`, and add its name to `MUTATING` if it changes anything and to `UNTRUSTED` if it returns outside content. Keep new tools read-only unless there's a good reason.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Jarvis: not signed in" | Open the link from `server.py --print-url` once in that browser. |
| 403 Forbidden | The Host or Origin isn't allowed. For a new address, add its host name to `allowed_hosts`. |
| Page won't load | `launchctl print gui/$(id -u)/com.arun.jarvis`, then the log. |
| "Connection fault" | Ollama isn't running: `brew services start ollama`. |
| Mic does nothing in the browser | Use Chrome or Safari; allow the mic in the address bar. |
| Wake word never fires | Run `wake.py --test`; lower `THRESHOLD`; allow the mic for your terminal. |
| Wake word fires on TV or music | Raise `THRESHOLD` (e.g. 0.7). |
| "macOS blocked access" | Privacy & Security → Automation: allow Python for that app. |
| `describe_screen` can't capture | Grant Screen & System Audio Recording to the Python app (see above). |
| Reminders "Connection is invalid" once | A macOS startup glitch; Jarvis retries automatically. |
| "Gmail rejected the login" | The app password was revoked or mistyped; create a new one and store it again. |
| Timers or alerts never fire | The server must be running (it hosts the scheduler); check the log. |
| Documents not found | Run `docs_tool.py index`; check `doc_folders`; scanned PDFs have no text to index. |
| Wrong or garbled answer in Malayalam/Tamil | A model limit; see "Languages". |
| `pip install` fails on `webrtcvad` | You're on Python 3.13+; use the 3.12 venv. |
