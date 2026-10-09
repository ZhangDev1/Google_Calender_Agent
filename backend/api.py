from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai

from agent import get_calendar_service, build_agent_context, run_turn, resolve_confirmation, transcribe_audio
from pathlib import Path

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


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


def _handle_message(session: dict, message: str) -> dict:
    """
    Run one message through a session's agent state, handling the
    pending-confirmation dance generically. Shared by /chat and /voice so
    a voice-triggered confirmation gate ("create this event?") can be
    answered by a later /chat OR /voice call — both check the same
    session["pending"], so there's no special-casing between modalities.
    """
    if session["pending"] is not None:
        confirmed = message.strip().lower() in ("y", "yes")
        pending = session["pending"]
        session["pending"] = None
        return resolve_confirmation(client, system_instruction, tool_functions,
                                     tools_by_name, session["history"],
                                     pending["tool_name"], pending["args"], confirmed)
    session["history"].append(genai.types.Content(role="user", parts=[genai.types.Part(text=message)]))
    return run_turn(client, system_instruction, tool_functions, tools_by_name, session["history"])


@app.post("/chat")
def chat(request: ChatRequest):
    session = sessions.setdefault(request.session_id, {"history": [], "pending": None})
    result = _handle_message(session, request.message)

    if result["status"] == "done":
        return {"response": result["text"]}
    elif result["status"] == "needs_confirmation":
        session["pending"] = {"tool_name": result["tool_name"], "args": result["args"]}
        return {"response": f"About to run {result['tool_name']} with {result['args']}. Proceed? [y/n]"}
    else:
        return {"response": "Unexpected result status."}


@app.post("/voice")
async def voice(session_id: str = Form(...), audio: UploadFile = None):
    session = sessions.setdefault(session_id, {"history": [], "pending": None})
    audio_bytes = await audio.read()
    transcript = transcribe_audio(client, audio_bytes, audio.content_type or "audio/m4a")
    result = _handle_message(session, transcript)

    if result["status"] == "done":
        return {"transcript": transcript, "response": result["text"]}
    elif result["status"] == "needs_confirmation":
        session["pending"] = {"tool_name": result["tool_name"], "args": result["args"]}
        return {"transcript": transcript, "response": f"About to run {result['tool_name']} with {result['args']}. Proceed? [y/n]"}
    else:
        return {"transcript": transcript, "response": "Unexpected result status."}

