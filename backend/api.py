import re
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.auth.exceptions import RefreshError

from agent import get_calendar_service, build_agent_context, run_turn, resolve_confirmation, transcribe_audio

load_dotenv(Path(__file__).parent / ".env") # Load environment variables from .env file


app = FastAPI()

# Dev-only: the Expo web dev server runs on a different port than this API,
# so the browser treats it as a different origin and preflights every
# request. allow_origins=["*"] is fine for local development; lock this down
# to your actual deployed frontend origin(s) before this goes anywhere real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client()
service = get_calendar_service()
tool_functions, tools_by_name, system_instruction = build_agent_context(service)

# session_id -> {"history": [...], "pending": None or {"tool_name": str, "args": dict}}
# in-memory, one process only — same "don't solve it before you need it" call
# already made for memory.json; a real multi-user deployment needs this
# backed by something that survives a server restart, not a plain dict.
sessions: dict[str, dict] = {}

# Replies that count as "yes" at the confirmation gate. Still a fixed,
# deterministic list (not model-interpreted), just wider than "y"/"yes" since
# spoken replies come back from transcription as e.g. "Yes." or "Yeah, do it".
AFFIRMATIVE_REPLIES = {"y", "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
                       "yes please", "do it", "go ahead", "yes do it", "yeah do it", "sure go ahead"}

# Uploads from React Native often arrive as application/octet-stream, which
# Gemini rejects — fall back to the file extension the app sends instead.
AUDIO_MIME_BY_EXTENSION = {".m4a": "audio/m4a", ".mp4": "audio/mp4", ".webm": "audio/webm",
                           ".wav": "audio/wav", ".mp3": "audio/mp3", ".ogg": "audio/ogg"}


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


def is_affirmative(reply: str) -> bool:
    """Deterministic yes-check that tolerates punctuation/casing from transcription."""
    normalized = " ".join(re.sub(r"[^\w\s]", " ", reply.lower()).split())
    return normalized in AFFIRMATIVE_REPLIES


def describe_pending_action(tool_name: str, args: dict) -> str:
    """Human-readable (and speakable) confirmation prompt for an irreversible tool call."""
    if tool_name == "create_event_tool":
        return (f"Create \"{args.get('summary', 'an event')}\" from {args.get('start_datetime')} "
                f"to {args.get('end_datetime')}? Say yes to confirm.")
    if tool_name == "update_event_tool":
        changes = ", ".join(f"{k.replace('_', ' ')} to {v}" for k, v in args.items()
                            if k != "event_id" and v is not None)
        return f"Update that event, changing {changes or 'nothing'}? Say yes to confirm."
    if tool_name == "delete_event_tool":
        return "Delete that event? Say yes to confirm."
    return f"Run {tool_name}? Say yes to confirm."


def _handle_message(session: dict, message: str) -> str:
    """
    Run one message through a session's agent state, handling the
    pending-confirmation dance generically. Shared by /chat and /voice so
    a voice-triggered confirmation gate ("create this event?") can be
    answered by a later /chat OR /voice call — both check the same
    session["pending"], so there's no special-casing between modalities.

    If anything fails mid-turn (expired Google auth, Gemini quota, ...),
    the session is rolled back to how it was before this message. Otherwise
    history would be left ending in a function_call with no matching
    function_response, and every later request in the session would fail.
    """
    history_len = len(session["history"])
    pending = session["pending"]
    try:
        if pending is not None:
            session["pending"] = None
            result = resolve_confirmation(client, system_instruction, tool_functions,
                                          tools_by_name, session["history"],
                                          pending["tool_name"], pending["args"], is_affirmative(message))
        else:
            session["history"].append(genai.types.Content(role="user", parts=[genai.types.Part(text=message)]))
            result = run_turn(client, system_instruction, tool_functions, tools_by_name, session["history"])
    except Exception as e:
        if pending is not None and len(session["history"]) > history_len:
            # The confirmed tool already ran (its function_response is in
            # history) — keep that, so retrying "yes" can't run it twice.
            del session["history"][history_len + 1:]
        else:
            del session["history"][history_len:]
            session["pending"] = pending
        raise _to_http_error(e)

    if result["status"] == "needs_confirmation":
        session["pending"] = {"tool_name": result["tool_name"], "args": result["args"]}
        return describe_pending_action(result["tool_name"], result["args"])
    return result["text"]


def _to_http_error(e: Exception) -> HTTPException:
    print(f"Request failed: {e!r}")
    if isinstance(e, RefreshError):
        return HTTPException(503, "Google Calendar authorization expired. Restart the backend to sign in again.")
    if isinstance(e, genai_errors.APIError) and e.code == 429:
        return HTTPException(503, "The Gemini API quota is used up. Try again later.")
    return HTTPException(500, f"Something went wrong on the server: {e}")


@app.post("/chat")
def chat(request: ChatRequest):
    session = sessions.setdefault(request.session_id, {"history": [], "pending": None})
    return {"response": _handle_message(session, request.message)}


@app.post("/voice")
async def voice(session_id: str = Form(...), audio: UploadFile = File(...)):
    session = sessions.setdefault(session_id, {"history": [], "pending": None})
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "The recording was empty.")

    mime_type = audio.content_type
    if not mime_type or not mime_type.startswith("audio/"):
        mime_type = AUDIO_MIME_BY_EXTENSION.get(Path(audio.filename or "").suffix.lower(), "audio/m4a")

    try:
        transcript = transcribe_audio(client, audio_bytes, mime_type)
    except Exception as e:
        raise _to_http_error(e)
    if not transcript:
        return {"transcript": "", "response": "Sorry, I didn't catch that. Could you try again?"}

    return {"transcript": transcript, "response": _handle_message(session, transcript)}
