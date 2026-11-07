# Voice Calendar Agent

[![CI](https://github.com/ZhangDev1/Google_Calender_Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/ZhangDev1/Google_Calender_Agent/actions/workflows/ci.yml)

Talk to your phone and manage your Google Calendar. Ask "what's on my calendar
tomorrow?" or say "schedule lunch with Sam Friday at noon". A Gemini-powered
agent checks for conflicts, asks before changing anything, and creates, updates
or deletes real events through the Google Calendar API.

The agent loop is written by hand rather than with an agent framework, so the
tool dispatch, memory and guardrails are all visible in the code.
[ARCHITECTURE.md](ARCHITECTURE.md) has the design, the roadmap, and the
problems hit along the way and how each was solved.

## Features

- **Voice or text input.** Record a request in the app, or type it. Replies to
  voice requests are spoken aloud on the device.
- **Tool-calling agent.** `list_events`, `create_event`, `update_event`,
  `delete_event` and `remember_fact`. The agent chains them, for example
  checking for conflicts before it creates an event.
- **Confirmation gate.** Creates, updates and deletes always pause for an
  explicit "yes". This check runs in code, so the model can't skip it.
- **Guardrails.** The agent refuses tools that were never registered, caps
  calendar queries at 31 days, and declines requests that aren't about the
  calendar.
- **Memory.** Short-term memory within a session, plus long-term preferences
  (such as "lunch is 30 minutes") saved to `memory.json` and given to the model
  at the start of every session.
- **Light and dark themes** in the app.

## How it works

```
React Native app (Expo)                FastAPI backend
───────────────────────                ─────────────────────────────────────
type a message ──── POST /chat ──────▶ agent loop ◀──▶ Gemini (tool calling)
                                           │
record audio ────── POST /voice ─────▶ transcribe (Gemini) ─▶ same agent loop
                                           │
speak the reply ◀── {response} ──────── Google Calendar API (OAuth 2.0)
```

Voice is only an input method. `/voice` turns the recording into text and
sends it through the same code path as a typed `/chat` message, so the agent
never knows whether the request was spoken.

## Design decisions

**The agent loop is hand-written.** Gemini's automatic function calling runs
tools as soon as the model asks for them, which leaves no place to stop and
check a call first. The manual loop inspects every requested tool call, then
decides whether to run it, refuse it or pause for the user. It was also built
this way to learn how agents work, rather than hide that behind a framework.

**Safety rules live in code, not in the prompt.** Prompts shape what a model
does, but they don't guarantee it. In testing, the model requested a full year
of events after being told to pick a sensible range, and it called tools that
didn't exist. So the 31-day query limit and the rejection of unregistered tools
are hard checks that run whatever the model decides.

**The model can't approve its own actions.** Creating, updating and deleting
events all stop at a confirmation gate. The model could ask "should I proceed?"
and make the tool call in the same response, so the prompt alone isn't enough.
The user's reply is matched against a fixed list of affirmatives, with no model
involved. "Yes." passes, but "yes but make it 4pm" counts as a no. Because a
confirmation spans two HTTP requests, the pending action is stored on the
session and only runs when the follow-up reply arrives.

**Voice is kept separate from the agent.** Transcription is its own step, and
its output goes through the same code path as typed text. The agent needed no
changes to support voice, and a confirmation raised by voice can be answered by
typing, or the other way around.

**Failed requests can't corrupt a session.** Gemini expects every tool call in
the history to have a matching result, so an error partway through a turn would
break every later request in that session. The session is rolled back to its
state before the message. The exception is a confirmed action that already ran:
its result is kept, so retrying "yes" can't create or delete an event twice.

**Storage is as simple as the current scale allows.** Sessions live in a plain
dictionary, preferences in `memory.json`, and the Google token in `token.json`.
That's enough for one user on one server, and each one has a clear replacement
when that stops being true: a session store, a queryable database and per-user
token storage.

## Stack

| Layer | Tech |
|---|---|
| Mobile app | React Native, Expo Router, TypeScript, `expo-audio`, `expo-speech` |
| Backend | Python 3.11, FastAPI |
| LLM and transcription | Google Gemini (`google-genai`) |
| Calendar | Google Calendar API v3, OAuth 2.0 |
| CI | GitHub Actions (pytest and a TypeScript typecheck) |

## Project structure

```
backend/
  agent.py          agent loop, tools, guardrails, memory, OAuth
  api.py            FastAPI app: /health, /chat, /voice
  tests/            pytest suite (Google and Gemini are mocked)
mobile/
  src/app/index.tsx chat screen: text input, recording, message list
  src/constants/    API URL and theme
ARCHITECTURE.md     design, roadmap, roadblocks and fixes
```

## Running it locally

### 1. Google Cloud setup

1. Create a Google Cloud project and enable the **Google Calendar API**.
2. Configure the **OAuth consent screen**, and add your Google account as a
   test user.
3. Create an **OAuth client ID** of type *Desktop app*. Download the JSON file
   into `backend/`, then set `CLIENT_SECRET_PATH` in `backend/agent.py` to
   that file's name.
4. Get a **Gemini API key** from [Google AI Studio](https://aistudio.google.com/).

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn api:app --port 8000 --reload
```

Before starting the server, create a file named `.env` in `backend/` containing
one line:

```
GOOGLE_API_KEY=your-key-here
```

The first time it starts, a browser window opens for Google sign-in. The
resulting token is saved to `backend/token.json`.

### 3. Mobile app

```bash
cd mobile
npm install
npm start          # then press w for web, or scan the QR code with Expo Go
```

To use the app on a phone, set `LAN_IP` in `mobile/src/constants/api.ts` to
your computer's local IP address, and start the backend with `--host 0.0.0.0`
so the phone can reach it. The phone and computer must be on the same network.
Only do this on a network you trust (see Known limitations).

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests
```

## Roadmap

- [x] Phase 0: OAuth and Calendar API plumbing
- [x] Phase 1: text-based agent (tools, agent loop, memory, guardrails)
- [x] Phase 2: React Native app
- [x] Phase 3: voice input and spoken replies (not streaming)
- [ ] Phase 4: full streaming conversation over Gemini Live and WebSocket
- [ ] Phase 5: deployment to Cloud Run, per-user Google sign-in, polish

## Known limitations

- The API has no login and allows requests from any origin, so it's for local
  development only. With `--host 0.0.0.0`, anyone on your network can reach it
  and change your calendar.
- The backend serves one Google account: whoever signs in on the server.
  Per-user sign-in from the app is planned for Phase 5.
- Sessions are kept in memory and are lost when the server restarts.
- While the OAuth consent screen is in *Testing* mode, Google expires the
  sign-in after 7 days. Restart the backend to sign in again.

## License

[MIT](LICENSE)
