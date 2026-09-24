# Voice Calendar Agent — Architecture & Roadmap

A voice-driven agent that lets a user speak to their phone to create events on
their Google Calendar. Built as a portfolio project using technology choices
that are standard at large tech companies.

## Goal

Full streaming voice conversation (not just record-a-command): the user talks
naturally, the agent can ask clarifying questions, and it creates real events
on the user's Google Calendar via tool-calling.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Mobile app | **React Native** | Used at Meta (created it), Shopify, Coinbase, Discord. Large ecosystem, transferable JS/TS skills. |
| Backend | **Python + FastAPI** | Dominant for AI/agent backends; async support for streaming; integrates cleanly with Google's Python SDKs. |
| Realtime voice + LLM | **Gemini Live API** (Google) | Bidirectional audio streaming with native function/tool-calling — no manual STT→LLM→TTS stitching required. Fits naturally with Google Calendar since both are Google APIs. (OpenAI's Realtime API is the equivalent if using GPT instead — worth knowing as an alternative.) |
| Calendar integration | **Google Calendar API v3** via **OAuth 2.0** | Standard "Sign in with Google" consent flow, `calendar.events` scope. |
| Transport (app ↔ backend) | **WebSocket** | Standard for low-latency bidirectional audio streaming. |
| Deployment | **Docker on Cloud Run** (or ECS/Fargate as alternative) | Standard containerized deploy pattern. |
| CI/CD | **GitHub Actions** | Ubiquitous for build/test/deploy pipelines. |

### Agent pattern

Define a `create_calendar_event` tool (JSON schema: title, start, end,
attendees, etc.) and register it with Gemini Live. When the user's speech
implies a calendar action, the model emits a tool call; the backend executes
it against the Google Calendar API and returns the result into the
conversation so the agent can confirm back to the user.

## Roadmap

Built incrementally — each phase proves one piece in isolation before adding
the next layer of complexity.

- [x] **Phase 0 — Plumbing.** GCP project, OAuth consent screen, a FastAPI
      endpoint that creates a hardcoded event on a real calendar via the
      Calendar API. Proves auth + API access before any agent logic exists.
- [x] **Phase 1 — Text-in agent.** The core of the project. Built and tested
      entirely with text input, decoupled from voice — voice is just an I/O
      modality bolted on in Phase 3/4, the agent itself doesn't know the
      difference. Hand-rolled (not a framework like LangGraph/ADK) so the
      concepts are actually learned rather than abstracted away. Components:
    - **Toolbelt** — [x] `create_event`, [x] `list_events`,
      [x] `update_event`, [x] `delete_event`. `check_availability` was
      dropped from the plan rather than built — `list_events` already
      covers exactly that need (proven repeatedly in testing), so a
      separate tool would've just been a redundant way to ask the same
      question. Not just one function; the agent chains calls (confirmed
      working: it checks `list_events` for conflicts before deciding
      whether to call `create_event`). `update_event`/`delete_event` both
      sit behind the confirmation gate, same as `create_event`.
    - **Agent loop** — [x] built. Automatic function calling turned out to
      be the wrong fit (see Roadblocks below) — replaced with a manual
      loop: inspect `response.candidates[0].content.parts` for
      `function_call`s, validate, dispatch by hand.
    - **Memory** — [x] short-term (session-scoped `history` list, verified
      working across real multi-turn REPL exchanges — the model correctly
      remembered an event it had just created in an earlier turn of the
      same session). [x] Long-term: `memory.json` (flat key/value facts),
      read on session start and injected into `system_instruction` so the
      model always has known preferences in context without needing to
      ask for them; written via a `remember_fact(key, value)` tool the
      model calls when the user states a preference worth persisting.
      Verified end-to-end: asked the model to remember a lunch-duration
      preference, it chose a sensible key/value pair on its own
      (`lunch_duration: "30 minutes"`), and it persisted to disk correctly.
      Known limitation, deliberately not solved yet: this always injects
      the *entire* memory file into every session — fine at the current
      scale (a handful of facts), but doesn't scale to a large, long-lived
      memory store. At that point the fix is on-demand retrieval (a
      `recall_facts(query)` tool backed by a real queryable DB, likely
      with embedding-based relevance filtering) instead of always-inject
      — the same "don't solve it before you need it" call already made
      for `token.json` and the flat `history` list.
    - **Guardrails** — [x] unsupported-tool rejection, [x] date-range clamp,
      [x] scope limits, [x] confirmation gate before irreversible actions.
      All four built and verified. See "Guardrails" section below for what
      each one actually does.
- [x] **Phase 2 — Bare-bones RN app.** A screen with a text box hitting the
      Phase 1 backend. Establishes React Native project setup, API calls,
      and mobile OAuth/token handoff before audio enters the picture.
    - **Backend as an HTTP API** — [x] done. `backend/api.py` (FastAPI):
      `GET /health`, `POST /chat` (`{session_id, message}` ->
      `{response}`). In-memory `sessions` dict keyed by `session_id`
      (`{"history": [...], "pending": ...}`) stands in for real per-user
      session storage — same "don't solve it before you need it" call as
      `token.json`/`memory.json`; doesn't survive a server restart or scale
      past one process, deliberately, for now.
    - **Confirmation gate over HTTP** — [x] done. `input()` cannot block
      across two separate HTTP requests, so `run_turn` was restructured to
      return a `{"status": "needs_confirmation", ...}` result instead of
      executing an irreversible tool immediately; the pending action is
      stashed on the session, and a new `resolve_confirmation()` executes
      it once a follow-up request supplies a deterministic yes/no (not
      model-interpreted — same reasoning as the original gate). Verified
      live over real HTTP calls: request 1 triggers the gate with nothing
      created yet, request 2 ("yes") actually creates the event.
    - **React Native app** — [x] done. Built on the default Expo Router
      (`expo-router` + `expo-router/ui` tabs) scaffold in `mobile/`. The home
      screen (`mobile/src/app/index.tsx`) holds a `TextInput`, a scrollable
      message list (`{role, text}` bubbles, user vs. assistant styled
      differently), and a `Submit` button wired to `sendMessage()`, which
      `POST`s `{session_id, message}` to `/chat` and appends the returned
      `response` as a new bubble. `session_id` is a `uuid.v4()` generated
      once per app session via a `useState` lazy initializer and held stable
      for the component's lifetime. `API_URL` (`mobile/src/constants/api.ts`)
      is picked by `Platform.OS`: `localhost` on web, LAN IP on native — the
      backend has to run with `uvicorn api:app --host 0.0.0.0` for the LAN
      IP case to be reachable from a phone. Verified end-to-end over a real
      HTTP round trip from the app to the backend and back.
    - **Light/dark theme toggle** — [x] done, not originally scoped but built
      alongside the chat screen since it surfaced a real architectural gap:
      `_layout.tsx` (react-navigation's `ThemeProvider`) and `use-theme.ts`
      (the app's own `Colors` lookup) were two *independent* systems, both
      reading the raw OS scheme via `useColorScheme()` with no shared state.
      Consolidated both onto one `ThemePreferenceProvider` context
      (`mobile/src/context/theme-preference.tsx`) holding a `'light' |
      'dark' | 'system'` preference and the resolved `scheme`; `use-theme.ts`
      and `use-color-scheme.ts`/`.web.ts` now all read from it instead of
      the system directly, and a toggle button on the home screen flips it.
      `app-tabs.web.tsx` and `web-badge.tsx` were also switched over from
      importing `useColorScheme` straight from `react-native` — they'd have
      silently stayed on the OS setting otherwise, out of sync with the rest
      of the app.
- [ ] **Phase 3 — Voice, non-streaming.** Record button → send audio blob →
      transcribe → run through Phase 1 agent → speak back the response.
      Proves the mobile audio capture/playback pipeline in isolation.
- [ ] **Phase 4 — Full streaming conversation.** Swap in Gemini Live over
      WebSocket; mic streams continuously, model can ask clarifying
      questions, handle barge-in, etc. This is the target experience.
- [ ] **Phase 5 — Polish.** Error handling for ambiguous requests, deploy
      backend to Cloud Run, basic logging/observability, README + demo
      video for the portfolio.

## Roadblocks & Resolutions

### Environment / tooling
- The VS Code Code Runner extension ran scripts with the system Python, not
  the project venv, causing a false `ModuleNotFoundError` for installed
  packages. Fixed by using the VS Code Python extension with the venv
  explicitly selected as the interpreter instead of Code Runner.

### OAuth / auth
- Google's OAuth consent screen blocks unverified apps ("Access blocked")
  until the signing-in account is on the test users list. Fixed by adding
  the account under OAuth consent screen → Test users.
- Trying to also add the project's own developer/owner account to that same
  test users list fails with "ineligible" — that account already has
  implicit access and doesn't need (or accept) being added. The earlier
  block turned out to be caused by the browser defaulting to the wrong
  signed-in Google account during consent, not a missing test-user entry.
- `client_secret_*.json` identifies the *app*, not a user — the same file
  is reused for every user who ever authorizes it. `token.json` is what's
  actually unique per authenticated user. Multi-user support later means
  per-user token storage in a database, not a single shared file.
- The Calendar OAuth client and the `GOOGLE_API_KEY` are unrelated
  credentials for unrelated trust relationships: OAuth delegates access to
  one specific user's private data; the API key just authenticates the app
  itself to a stateless Gemini call. Conflating them caused early confusion.

### Auth code bugs (`get_calendar_service`)
- Used `google.oauth2.service_account.Credentials` (server-to-server auth)
  instead of `google.oauth2.credentials.Credentials` (delegated user auth)
  — wrong class for what this function does.
- Used `httpcore.Request` instead of `google.auth.transport.requests.Request`
  for token refresh — an unrelated HTTP library's request object.
- Fresh credentials from `flow.run_local_server()` were never captured into
  `creds`, so a "successful" re-auth was never actually saved to
  `token.json`.
- A failed token refresh had no fallback path to full re-authentication —
  fixed by restructuring a single `if/elif/else` into two independent
  `if not creds or not creds.valid` checks, so a failed refresh falls
  through to the full OAuth flow instead of proceeding with invalid creds.

### SDK usage
- `import googleapiclient` alone doesn't pull in the `discovery` submodule
  — needed an explicit `from googleapiclient.discovery import build`.
- `body={...}` was a literal Python `Ellipsis` object, not a placeholder —
  needed a real event dict.
- `.env` values aren't loaded automatically — needed an explicit
  `load_dotenv()` call before constructing the Gemini client.
- `client.interactions.create(...)` is a different, higher-level "Agent
  Platform" API surface with its own contract (structured tool dicts, an
  `agent` field) aimed at deploying onto Google's own agent-hosting
  platform — not what we want here, since the goal is to hand-roll the
  loop. Reverted to `client.models.generate_content(...)` with automatic
  function calling explicitly disabled and manual dispatch instead.

### Agent behavior discoveries
- The model would occasionally call tools that were never declared to it
  (`list_events_tool`, `search_events_tool`) — a real, if intermittent,
  failure mode on this model, not a code bug. This is what motivated the
  unsupported-tool guardrail.
- The model has no innate sense of "today" or the user's timezone — it
  guessed wildly wrong dates (querying January 2026 when it was actually
  September) and an unverified timezone until both were explicitly
  injected via `system_instruction`, sourced from the server's own clock
  (`datetime.now()`) and `tzlocal.get_localzone_name()`. General lesson:
  never assume a model knows "now" or "where" — always inject real-world
  context the app already has rather than let the model guess it.
- Docstring guidance alone didn't reliably keep the model's date ranges
  narrow — it requested a full year even after being told to "choose an
  appropriate range." This is what motivated the hard range-clamp
  guardrail rather than relying on prompting alone: instructions shape
  behavior, they don't guarantee it.
- What looked like working multi-step reasoning early on (the model
  checking `list_events` and then not creating a duplicate) turned out to
  be incomplete — the script executed one tool call and exited without
  ever feeding the result back to the model, so it never actually
  "decided" anything. Real check-then-act reasoning needed a genuine loop:
  a growing `history` list of `Content` turns, sent back to the model
  after every tool execution, continuing until it produces a text-only
  response. This is what `run_turn`/`run_agent` actually implement, and
  it's also what session-scoped short-term memory turned out to *be* —
  not a separate feature, but a direct consequence of building the loop
  correctly.
- After adding a system_instruction telling the model to ask before
  creating a conflicting event, one successful test made conversational
  confirmation look sufficient. It isn't, reliably: nothing stops the
  model from bundling a confirmation question and the actual tool call
  into the same response, and prompted behavior was already proven
  unreliable once before (the date-range case above). Fixed by adding a
  hard, unconditional confirmation gate in the dispatch code itself
  (`IRREVERSIBLE_TOOLS`) — verified by declining at the hard gate right
  after conversationally agreeing via the model, confirming the two are
  genuinely independent checkpoints, not redundant ones.
- Development/testing burned through the Gemini free tier's daily quota
  (20 `generate_content` requests/day for `gemini-3.6-flash`) more than
  once. It's a per-day cap, not a short cooldown — the fix is waiting for
  the daily reset or switching to a different model (separate quota
  bucket) for continued testing, not retrying quickly.
- A refactor left `run_agent` no longer returning a value (it became an
  open-ended REPL), but `main()` still printed its old return value,
  silently printing `None` after every session. Cleanup: stop capturing/
  printing a return value that no longer exists.
- A multi-line `system_instruction` built as a single triple-quoted
  f-string, with leftover literal `"` characters from an earlier
  parenthesized-adjacent-literals version, compiled without error but
  produced a string full of stray quotes and raw newlines baked into the
  actual text sent to the model. Triple-quoted strings don't
  auto-concatenate the way adjacent string literals in parentheses do —
  fixed by returning to the parenthesized-adjacent-literals form.

### Mobile app (Expo / React Native)
- Running `expo` directly in a shell failed with "command not found" —
  `expo` is a local dependency (`mobile/node_modules/.bin/expo`), not a
  global install, and that folder isn't on PATH by default. Fixed by using
  `npm start` (already mapped to `expo start` in `package.json`) or
  `npx expo start` instead of a bare `expo` command; avoided installing the
  deprecated standalone `expo-cli` globally, which would conflict with the
  local `expo` package.
- A bare `<TextInput>` rendered with no visible border, background, or
  padding — React Native gives it zero default styling, so it was present
  but genuinely invisible against the themed background. Fixed by adding an
  explicit style; later revisited to fill it with `colors.backgroundElement`
  instead of a hardcoded border color, matching the pill/card visual
  language already used elsewhere (`TabButton`, the theme-toggle button)
  rather than inventing a new one-off border color not in the palette.
- `session_id` was computed as `uuid.v4()` directly in the component body,
  so a *new* session ID was generated on every re-render — including every
  keystroke into the `TextInput` — meaning no two requests would ever land
  in the same backend session. Fixed with `useState(() => uuid.v4())`, a
  lazy initializer that only runs once, on mount.
- The web build's `/chat` request failed with **405 Method Not Allowed**.
  Cause: the Expo web dev server and FastAPI run on different ports, so the
  browser treats them as different origins and sends a preflight `OPTIONS`
  request before the real `POST`; `api.py` had no CORS middleware, so
  FastAPI (correctly) replied 405 since only `POST` was declared for that
  route. Fixed by adding `CORSMiddleware` to `api.py`
  (`allow_origins=["*"]` — fine for local dev, needs locking down to a real
  origin before any deployment).

## Guardrails

What each currently-implemented guardrail actually protects against:

1. **Unsupported-tool rejection** (dispatch loop in `main()`). If the model
   requests a tool name that isn't in `tools_by_name`, log and skip instead
   of executing or crashing. Purpose: never execute something the app
   didn't explicitly register, no matter what the model invents.
2. **Date-range clamp** (`list_events`, `MAX_RANGE_DAYS = 31`). Caps any
   requested `time_min`/`time_max` span to 31 days regardless of what the
   model asks for. Purpose: docstring instructions shape model behavior but
   don't guarantee it — this enforces a hard limit so an oversized,
   expensive query can't happen no matter what the model decides.
3. **Scope limits** (`system_instruction`). Tells the model it's a
   calendar assistant only and should decline unrelated requests. Purpose:
   keep the conversation on-topic. Lower-stakes than the other guardrails
   since the model has no tools to misuse for anything non-calendar
   anyway — this is about UX, not safety.
4. **Confirmation gate** (`run_turn`, `IRREVERSIBLE_TOOLS`). Before
   executing any tool in `IRREVERSIBLE_TOOLS` (currently
   `create_event_tool`), pauses for an explicit human `y`/`N` regardless of
   what the model's accompanying text says. Purpose: the model asking the
   user "should I proceed?" conversationally is not a guarantee it won't
   *also* call the tool in the same breath — this is a structural
   checkpoint the model cannot talk its way past. Verified by
   conversationally agreeing to double-book, then declining at this gate
   anyway, and confirming no event was created.
