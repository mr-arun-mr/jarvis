# Jarvis

A local AI assistant for macOS. The language model runs on your machine through [Ollama](https://ollama.com). There is a sci-fi HUD in the browser with voice and text input, an optional "Hey Jarvis" wake-word listener, and tools that give it real data from your Mac and accounts.

What leaves your machine, and only when you use that feature:
- **Chrome voice input** sends mic audio to Google for transcription (Safari differs). The model itself stays local.
- **Gmail** connects to `imap.gmail.com`. **GitHub** calls `api.github.com`.
- **Weather** sends a city name to Open-Meteo. **Web search** sends your query to DuckDuckGo.

## What it can do

| Tool | What it does | Access |
|---|---|---|
| `check_inbox` | Unread Gmail: sender, subject, date | read-only |
| `list_whatsapp_chats`, `read_whatsapp_chat` | WhatsApp Desktop chats and recent messages | read-only |
| `github_my_work`, `github_notifications` | PRs awaiting review, assigned issues, your PRs, notifications | read-only |
| `get_calendar_events` | Events from today through N days | read-only |
| `list_reminders`, `add_reminder` | Open reminders; create one (optionally due in N minutes) | read + create |
| `search_notes`, `add_note` | Find Apple Notes by title; create a note | read + create |
| `get_weather`, `get_time` | Forecast for a city; time anywhere | read-only |
| `mac_status`, `set_volume`, `open_app` | Battery, disk, uptime, busiest processes; volume; open an app | fixed safe actions |
| `music_control` | Play, pause, next, previous, what's playing (Spotify or Apple Music) | control |
| `find_files`, `read_file` | Spotlight search; read plain-text files in your home folder | read-only |
| `web_search` | Web and news search | read-only |
| `remember`, `forget` | Long-term facts, shown to the model on every request | local file |

Nothing can send email or WhatsApp messages, edit or delete calendar events, notes or files, or run arbitrary shell commands.

Safety rules built in:
- **Outside content is data.** Emails, messages, web pages, notes and files can contain text trying to give the model orders. The system prompt says to ignore it, and the code also refuses any state-changing tool (`add_*`, `remember`, `forget`, `set_volume`, `open_app`, `music_control`) after reading such content in the same turn.
- **Files:** hidden folders (`.ssh`, `.aws`, ...), `~/Library`, anything outside your home folder, and files that look like secrets (`.env`, keys, tokens) cannot be read.
- **Tool selection:** only tool groups matching your message are offered to the model (all tools if none match). This keeps an 8B model accurate.

## Files

| File | Purpose |
|---|---|
| `server.py` | HTTP server for the HUD; streams replies. |
| `static/index.html` | The HUD (orb, transcript, mic and voice controls). Speech runs in the browser. |
| `wake.py` | "Hey Jarvis" listener that works without the browser. |
| `brain.py` | Shared core: system prompt, memory injection, tool selection, tool-calling loop. |
| `registry.py` | Collects all tool modules; defines which tools are state-changing or untrusted. |
| `gmail_tool.py`, `whatsapp_tool.py`, `github_tool.py` | Account tools. |
| `apple_tool.py` | Calendar, Reminders, Notes (AppleScript). |
| `weather_tool.py`, `mac_tool.py`, `files_tool.py`, `web_tool.py`, `memory_tool.py` | The other tools. |
| `applescript.py` | Safe AppleScript runner (arguments are never string-interpolated). |
| `config.py`, `config.json` | Your settings (git-ignored). Copy `config.example.json` to `config.json`. |
| `memory.json` | Saved facts (created on first use, owner-only permissions). Plain text; delete the file to wipe memory. |
| `jarvis.py` | Original terminal version (voice or `--text`). No tools. |
| `requirements.txt` | Python dependencies. |

## Local setup

macOS on Apple Silicon (tested), with [Homebrew](https://brew.sh).

```bash
brew install ollama ffmpeg portaudio python@3.12
brew services start ollama
ollama pull qwen2.5:14b

cd ~/jarvis
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "from openwakeword import utils; utils.download_models(model_names=['hey_jarvis'])"
```

Python 3.12 is used on purpose: several speech packages have no wheels for the newest Python (e.g. 3.14). The venv keeps it separate from your system Python.

## Run it

```bash
cd ~/jarvis && .venv/bin/python server.py
```

Open <http://127.0.0.1:8765> in Chrome or Safari. **Listen** keeps the mic open and answers after each pause; **Voice** mutes replies; the text box always works.

### Wake word ("Hey Jarvis")

```bash
cd ~/jarvis && .venv/bin/python wake.py --test   # prints scores when it hears the wake word
cd ~/jarvis && .venv/bin/python wake.py          # the real thing
```

After the wake word you hear a tick, speak your request, and pause; Jarvis answers aloud. macOS asks for microphone access for your terminal on first use. The threshold (`THRESHOLD = 0.5` in `wake.py`) trades false triggers against missed wakes. Press Ctrl+C to quit.

To run it at login, once the manual test works (see next section):

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.arun.jarvis.wake.plist
```

Background services may not get microphone permission automatically. If `~/Library/Logs/jarvis/wake.log` shows silence or errors, run it from Terminal instead, which is already allowed.

## Account setup

Credentials live in macOS Keychain; they are never stored in this folder.

**Gmail (read-only).** Turn on 2-Step Verification, create an app password at <https://myaccount.google.com/apppasswords>, then:

```bash
security add-generic-password -s jarvis-gmail -a YOUR_ADDRESS@gmail.com -w
```

**GitHub (read-only).** Create a token at <https://github.com/settings/personal-access-tokens/new> with read access to metadata, issues, pull requests and your repos, then:

```bash
security add-generic-password -s jarvis-github -a github -w
```

Fine-grained tokens cannot read notifications; for `github_notifications` use a classic token with the `notifications` scope. `github_my_work` works with either.

**WhatsApp.** Install WhatsApp Desktop (`brew install --cask whatsapp`), link it from your phone (Settings → Linked Devices), and let it sync. Jarvis reads its local database read-only. If it reports it can't read the database, give the Python that runs Jarvis Full Disk Access in System Settings → Privacy & Security. The database format is undocumented and may break after WhatsApp updates; it only holds what the Mac has synced.

**Calendar, Reminders, Notes, Music.** The first use of each makes macOS ask whether Python may control the app: click Allow. Calendar shows whatever is added to the Calendar app (iCloud, or Google via Internet Accounts).

**Remove a credential:** `security delete-generic-password -s jarvis-gmail` (or `jarvis-github`).

Facebook and Instagram are not supported: Meta has no API for personal accounts, and scraping would break their terms.

## Run at startup

Templates are in `launchd/`. Install them with your home path filled in. The `com.arun.*` label is just a name; if you pick a different one, substitute it in every command below:

```bash
mkdir -p ~/Library/Logs/jarvis
sed "s#__HOME__#$HOME#g" launchd/com.arun.jarvis.plist.example > ~/Library/LaunchAgents/com.arun.jarvis.plist
sed "s#__HOME__#$HOME#g" launchd/com.arun.jarvis.wake.plist.example > ~/Library/LaunchAgents/com.arun.jarvis.wake.plist
```

Two LaunchAgents in `~/Library/LaunchAgents/`:
- `com.arun.jarvis.plist`: runs `server.py` at login and restarts it if it crashes (enabled).
- `com.arun.jarvis.wake.plist`: runs `wake.py` the same way (created, **not enabled** until you've tested the mic).

Ollama starts separately through `brew services`.

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.arun.jarvis.plist      # enable
launchctl bootout gui/$(id -u)/com.arun.jarvis                                      # disable
launchctl kickstart -k gui/$(id -u)/com.arun.jarvis                                 # restart after code changes
launchctl print gui/$(id -u)/com.arun.jarvis | grep -E "state|pid"                  # status
tail -f ~/Library/Logs/jarvis/server.log                                            # logs (tool calls show as "tool: name")
```

Use the `.wake` label and `wake.log` for the wake listener. If you move this folder or your username differs, update the paths in the plists. To uninstall, run `bootout` and delete the plist files.

The server runs in the background but doesn't open a browser tab, and browser voice only works while the HUD tab is open. The wake listener doesn't need the browser.

## Configuration

| Setting | Where | Default |
|---|---|---|
| Model | `JARVIS_MODEL` env var, or `model` in `config.json` | `qwen2.5:14b` |
| Home city for weather | `default_city` in `config.json` | empty (Jarvis asks) |
| Port | `JARVIS_PORT` env var | `8765` |
| Personality and rules | `SYSTEM` in `brain.py` | concise, witty, plain text |
| Wake word and sensitivity | `wakeword_models`, `THRESHOLD` in `wake.py` | `hey_jarvis`, `0.5` |
| Spoken voice (wake mode) | `VOICE` in `wake.py` (list with `say -v '?'`) | `Daniel` |
| Speech model (wake mode) | `WhisperModel("small.en")` in `wake.py` | `small.en` |
| Browser voice and language | `speak()` and `rec.lang` in `static/index.html` | British male if available, `en-US` |
| What it remembers | `memory.json` | empty |

After editing `config.json` or any `.py` file, restart the service with the `kickstart` command. The LaunchAgent does not read your shell profile, so to set `JARVIS_MODEL` or `JARVIS_PORT` for it, add an `EnvironmentVariables` dict to the plist.

Model advice: it must support tool-calling. 8B is quick but sometimes picks the wrong tool or writes a tool call as text; with 48 GB RAM a 14B+ model (`ollama pull <name>`, then set `model`) is noticeably more reliable.

## Adding a tool

Make a module with `TOOLS` (JSON schemas), `FUNCTIONS` (name to function) and `KEYWORDS` (words that should offer it), import it in `registry.py`, and add its name to `MUTATING` if it changes anything and to `UNTRUSTED` if it returns outside content. Keep new tools read-only unless there's a good reason.

## Troubleshooting

| Problem | Fix |
|---|---|
| Page won't load | `launchctl print gui/$(id -u)/com.arun.jarvis`, then the log. |
| "Connection fault" | Ollama isn't running: `brew services start ollama`. |
| Mic does nothing in the browser | Use Chrome or Safari; allow the mic in the address bar. |
| Wake word never fires | Run `wake.py --test`; lower `THRESHOLD`; check the mic is allowed for your terminal. |
| Wake word fires on TV or music | Raise `THRESHOLD` (e.g. 0.7). |
| Tool says "macOS blocked access" | System Settings → Privacy & Security → Automation: allow Python for that app. |
| Jarvis writes raw JSON or the wrong answer | The 8B model slipped. Rephrase, or switch to a larger model. |
| "Gmail rejected the login" | Recreate the app password and re-add it to Keychain. |
| `pip install` fails on `webrtcvad` | You're on Python 3.13+; use the 3.12 venv. |
