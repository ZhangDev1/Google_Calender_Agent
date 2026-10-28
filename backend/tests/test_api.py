import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError


@pytest.fixture
def api():
    # api.py authenticates and builds a Gemini client at import time — stub
    # both so tests never touch real credentials or the network.
    sys.modules.pop("api", None)
    with patch("agent.get_calendar_service", return_value=MagicMock()), patch("google.genai.Client"):
        import api
    api.sessions.clear()
    yield api
    sys.modules.pop("api", None)


@pytest.mark.parametrize("reply", ["y", "yes", "Yes.", "YES!", "yeah, do it", " Sure. ", "Okay"])
def test_is_affirmative_accepts_spoken_yes(api, reply):
    assert api.is_affirmative(reply)


@pytest.mark.parametrize("reply", ["no", "No.", "", "yes but make it 4pm", "not yet"])
def test_is_affirmative_rejects_everything_else(api, reply):
    assert not api.is_affirmative(reply)


def test_describe_create_is_readable(api):
    text = api.describe_pending_action("create_event_tool", {
        "summary": "Dentist", "start_datetime": "2026-10-28T15:00:00", "end_datetime": "2026-10-28T15:30:00"})
    assert "Dentist" in text and "create_event_tool" not in text and "{" not in text


def test_chat_sets_pending_and_returns_readable_prompt(api):
    with patch("api.run_turn", return_value={"status": "needs_confirmation",
                                             "tool_name": "delete_event_tool", "args": {"event_id": "e1"}}):
        res = TestClient(api.app).post("/chat", json={"session_id": "s", "message": "delete it"})
    assert res.json() == {"response": "Delete that event? Say yes to confirm."}
    assert api.sessions["s"]["pending"] == {"tool_name": "delete_event_tool", "args": {"event_id": "e1"}}


def test_failed_turn_rolls_back_session(api):
    with patch("api.run_turn", side_effect=RefreshError("expired")):
        res = TestClient(api.app).post("/chat", json={"session_id": "s", "message": "hi"})
    assert res.status_code == 503 and "authorization expired" in res.json()["detail"]
    assert api.sessions["s"]["history"] == []


def test_failure_after_confirmed_tool_does_not_rerun_it(api):
    api.sessions["s"] = {"history": ["call"], "pending": {"tool_name": "delete_event_tool", "args": {}}}

    def tool_ran_then_model_failed(*args, **kwargs):
        args[4].append("function_response")
        raise RuntimeError("quota")

    with patch("api.resolve_confirmation", side_effect=tool_ran_then_model_failed):
        res = TestClient(api.app).post("/chat", json={"session_id": "s", "message": "yes"})
    assert res.status_code == 500
    assert api.sessions["s"] == {"history": ["call", "function_response"], "pending": None}


def test_voice_empty_transcript_skips_agent(api):
    with patch("api.transcribe_audio", return_value=""), patch("api.run_turn") as run_turn:
        res = TestClient(api.app).post("/voice", data={"session_id": "s"},
                                       files={"audio": ("recording.m4a", b"abc", "application/octet-stream")})
    assert res.json()["transcript"] == ""
    run_turn.assert_not_called()


def test_voice_infers_mime_type_from_extension(api):
    with patch("api.transcribe_audio", return_value="hello") as transcribe, \
         patch("api.run_turn", return_value={"status": "done", "text": "hi"}):
        res = TestClient(api.app).post("/voice", data={"session_id": "s"},
                                       files={"audio": ("recording.webm", b"abc", "application/octet-stream")})
    assert res.json() == {"transcript": "hello", "response": "hi"}
    assert transcribe.call_args.args[2] == "audio/webm"


def test_voice_rejects_missing_or_empty_audio(api):
    client = TestClient(api.app)
    assert client.post("/voice", data={"session_id": "s"}).status_code == 422
    assert client.post("/voice", data={"session_id": "s"},
                       files={"audio": ("recording.m4a", b"", "audio/m4a")}).status_code == 400
