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
    - **Toolbelt** — `create_event`, `list_events`, `check_availability`,
      `update_event`, `delete_event`. Not just one function; the agent
      should chain calls (e.g., check for conflicts before creating).
    - **Agent loop** — observe → reason → act → observe result → decide
      whether done or needs another step/clarification from the user.
    - **Memory** — short-term: conversation state within a session.
      Long-term: a small DB (Postgres/Firestore) the agent reads/writes as
      a tool, for facts like "lunch defaults to 12pm" or past corrections.
    - **Guardrails** — confirmation gate before irreversible actions
      (create/delete real events), scope limits (reject non-calendar
      requests), and validation of tool-call arguments before execution.
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
