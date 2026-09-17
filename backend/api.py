from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai

from agent import get_calendar_service, build_agent_context, run_turn
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env") # Load environment variables from .env file


app = FastAPI()

client = genai.Client()
service = get_calendar_service()
tool_functions, tools_by_name, system_instruction = build_agent_context(service)

sessions: dict[str, list] = {}  # session_id -> history, in-memory, one process only


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest):
    history = sessions.setdefault(request.session_id, [])
    history.append(genai.types.Content(role="user", parts=[genai.types.Part(text=request.message)]))
    response = run_turn(client, system_instruction, tool_functions, tools_by_name, history)
    return {"response": response}

