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
- [ ] **Phase 1 — Text-in agent.** The core of the project. Built and tested
      entirely with text input, decoupled from voice — voice is just an I/O
      modality bolted on in Phase 3/4, the agent itself doesn't know the
      difference. Hand-rolled (not a framework like LangGraph/ADK) so the
      concepts are actually learned rather than abstracted away. Components:
    - **Toolbelt** — [x] `create_event`, [x] `list_events`,
      [ ] `check_availability`, [ ] `update_event`, [ ] `delete_event`.
      Not just one function; the agent should chain calls (confirmed
      working: it now checks `list_events` for conflicts before deciding
      whether to call `create_event`).
    - **Agent loop** — [x] built. Automatic function calling turned out to
      be the wrong fit (see Roadblocks below) — replaced with a manual
      loop: inspect `response.candidates[0].content.parts` for
      `function_call`s, validate, dispatch by hand.
    - **Memory** — [ ] not started. Short-term (conversation state within a
      session) and long-term (a small DB the agent reads/writes as a tool,
      for facts like "lunch defaults to 12pm") both still to do.
    - **Guardrails** — [x] unsupported-tool rejection, [x] date-range clamp.
      [ ] Confirmation gate before irreversible actions (create/delete) and
      [ ] scope limits (reject non-calendar requests) still to do. See
      "Guardrails" section below for what each existing one actually does.
- [ ] **Phase 2 — Bare-bones RN app.** A screen with a text box hitting the
      Phase 1 backend. Establishes React Native project setup, API calls,
      and mobile OAuth/token handoff before audio enters the picture.
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

Still to build: a confirmation gate before irreversible actions
(create/delete), and scope limits that reject non-calendar requests
outright.
