from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai

from agent import get_calendar_service, build_agent_context, run_turn, resolve_confirmation
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env") # Load environment variables from .env file


app = FastAPI()

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


@app.post("/chat")
def chat(request: ChatRequest):
    session = sessions.setdefault(request.session_id, {"history": [], "pending": None})

    if session["pending"] is not None:
        confirmed = request.message.strip().lower() in ("y", "yes")
        pending = session["pending"]
        session["pending"] = None
        result = resolve_confirmation(client, system_instruction, tool_functions,
                                       tools_by_name, session["history"],
                                       pending["tool_name"], pending["args"], confirmed)
    else:
        session["history"].append(genai.types.Content(role="user", parts=[genai.types.Part(text=request.message)]))
        result = run_turn(client, system_instruction, tool_functions, tools_by_name, session["history"])


    if result["status"] == "done":
        return {"response": result["text"]}
    elif result["status"] == "needs_confirmation":
        session["pending"] = {"tool_name": result["tool_name"], "args": result["args"]}
        return {"response": f"About to run {result['tool_name']} with {result['args']}. Proceed? [y/n]"}
    else:
        return {"response": "Unexpected result status."}

