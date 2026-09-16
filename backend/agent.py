from google import genai
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from pathlib import Path
from dotenv import load_dotenv

from datetime import datetime, timedelta
from tzlocal import get_localzone_name

import json


# Confirmation gate tools that are irreversible (create, update, delete) to prevent accidental changes
IRREVERSIBLE_TOOLS = {"create_event_tool", "update_event_tool", "delete_event_tool"}

MAX_RANGE_DAYS = 31

MEMORY_PATH = "memory.json"

def get_calendar_service(token_path="token.json"):
    """
    Authenticate and return the Google Calendar service object.

    Args:
        token_path (str or Path): Path to the cached token file. Defaults to
            "token.json"; tests can override this to isolate their own file.

    Returns:
        googleapiclient.discovery.Resource: The Google Calendar service object.
    """

    token_path = Path(token_path)
    creds = None

    # Checks if the path exists AND is a file (returns True/False)
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(token_path, scopes=["https://www.googleapis.com/auth/calendar.events"])
        print("The token file exists.")


    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("Token refreshed successfully!")
            except Exception as e:
                print(f"Failed to refresh token: {e}")
                creds = None  # fall through to full re-auth below

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                "backend/client_secret_47034214311-jvaau3v3idk6no14mjlv6o83vq9k8a7h.apps.googleusercontent.com.json",
                scopes=["https://www.googleapis.com/auth/calendar.events"]
            )
            flow.run_local_server(port=0)
            creds = flow.credentials

        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)
    
    return service


def load_memory(memory_path=MEMORY_PATH):
    """
    Load the agent's memory from a JSON file.

    Args:
        memory_path (str or Path): Path to the memory JSON file. Defaults to
            "memory.json"; tests can override this to isolate their own file.

    Returns:
        dict: The loaded memory data.
    """
    memory_path = Path(memory_path)
    if memory_path.is_file():
        with open(memory_path, 'r') as f:
            return json.load(f)
    else:
        return {}


def save_memory(memory, memory_path=MEMORY_PATH):
    """
    Save the agent's memory to a JSON file.

    Args:
        memory (dict): The memory data to save.
        memory_path (str or Path): Path to the memory JSON file. Defaults to
            "memory.json"; tests can override this to isolate their own file.
    """
    memory_path = Path(memory_path)
    with open(memory_path, 'w') as f:
        json.dump(memory, f, indent=4)


def list_events(service, time_min, time_max, max_results=10):
    """
    List events on the user's Google Calendar within a time range.

    Args:
        service: Authenticated Google Calendar service object.
        time_min (str): Start of the range, RFC3339 with UTC offset. Choose a
            range appropriate to the request — e.g. the full day for checking
            conflicts around a specific event, or the relevant period (week,
            month) for an open-ended query.
        time_max (str): End of the range, RFC3339 with UTC offset.
        max_results (int): Maximum number of results to return.

    Returns:
        list[dict]: Matching events, each with 'id', 'summary', 'start', 'end'.
    """

    parsed_min = datetime.fromisoformat(time_min)
    parsed_max = datetime.fromisoformat(time_max)

    if parsed_max - parsed_min > timedelta(days=MAX_RANGE_DAYS):
        clamped_max = parsed_min + timedelta(days=MAX_RANGE_DAYS)
        print(f"Requested range ({time_min} to {time_max}) exceeds {MAX_RANGE_DAYS} days - clamping end to {clamped_max.isoformat()}.")
        time_max = clamped_max.isoformat()

    
    events_result = service.events().list(
        calendarId='primary', 
        timeMin=time_min, 
        timeMax=time_max,
        maxResults=max_results,
        singleEvents=True, 
        orderBy='startTime').execute()

    events = events_result.get('items', [])

    return [
        {
            "id": event["id"],
            "summary": event.get("summary", "(no title)"),
            "start": event["start"].get("dateTime", event["start"].get("date")),
            "end": event["end"].get("dateTime", event["end"].get("date")),
        }
        for event in events
    ]


def create_event(service, summary, start_datetime, end_datetime, timezone="America/Los_Angeles"):
    """
    Create a calendar event using Google Calendar API.

    Args:
        summary (str): The summary or title of the event.
        start_datetime (str): The start date and time of the event in ISO format.
        end_datetime (str): The end date and time of the event in ISO format.
        timezone (str): The timezone for the event. Default is "America/Los_Angeles".

    Returns:
        dict: The created event object.
    """

    event = {
        "summary": summary,
        "start": {"dateTime": start_datetime, "timeZone": timezone},
        "end": {"dateTime": end_datetime, "timeZone": timezone},
    }

    created_event = service.events().insert(calendarId='primary', body=event).execute()

    return created_event


def update_event(service, event_id, summary=None, start_datetime=None, end_datetime=None, timezone=None):
    """
    Update an existing calendar event. Only fields that are provided (not
    None) should actually change; leave everything else untouched.

    Args:
        service: Authenticated Google Calendar service object.
        event_id (str): The ID of the event to update (from list_events).
        summary (str, optional): New title for the event.
        start_datetime (str, optional): New start time, RFC3339 with UTC offset.
        end_datetime (str, optional): New end time, RFC3339 with UTC offset.
        timezone (str, optional): New IANA timezone name.

    Returns:
        dict: The updated event object.
    """

    body = {}
    if summary is not None:
        body["summary"] = summary
    if start_datetime is not None:
        body["start"] = {"dateTime": start_datetime}
    if timezone is not None:
        body.setdefault("start", {})["timeZone"] = timezone
    if end_datetime is not None:
        body["end"] = {"dateTime": end_datetime}
    if timezone is not None:
        body.setdefault("end", {})["timeZone"] = timezone

    return service.events().patch(calendarId='primary', eventId=event_id, body=body).execute()


def delete_event(service, event_id):
    """
    Delete an event from the user's Google Calendar.

    Args:
        service: Authenticated Google Calendar service object.
        event_id (str): The ID of the event to delete (from list_events).

    Returns:
        None
    """

    service.events().delete(calendarId='primary', eventId=event_id).execute()

    return


def run_turn(client, system_instruction, tool_functions, tools_by_name, history, model="gemini-3.6-flash"):
    max_turns = 20

    # Set a max number of turns to prevent infinite loops that drive up token usage
    for _ in range(max_turns):
        response = client.models.generate_content(
            model=model,
            contents=history,
            config=genai.types.GenerateContentConfig(
                tools=tool_functions,
                system_instruction=system_instruction,
                automatic_function_calling=genai.types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )

        model_content = response.candidates[0].content
        history.append(model_content)

        function_calls = [part.function_call for part in model_content.parts if part.function_call]
        if not function_calls:
            return response.text  # no more tool calls — this is the final answer

        response_parts = []
        for call in function_calls:
            if call.name not in tools_by_name:
                # Function call requested by the model is not in our list of tools - refuse to execute it
                print(f"Model requested unsupported tool '{call.name}' with args {call.args} — refusing to execute.")
                result = {"error": f"Tool '{call.name}' does not exist."}
            elif call.name in IRREVERSIBLE_TOOLS:
                # Function call is irreversible - ask the user to confirm before executing it
                print(f"About to run {call.name} with {call.args}")
                if input("Proceed? [y/N] ").strip().lower() != "y":
                    result = {"error": "User declined to confirm this action."}
                else:
                    result = tools_by_name[call.name](**call.args)
                    print(f"Executed {call.name} -> {result}")
            else:
                # Function call is safe to execute - run it
                result = tools_by_name[call.name](**call.args)
                print(f"Executed {call.name} -> {result}")
            response_parts.append(genai.types.Part.from_function_response(name=call.name, response={"result": result}))

        history.append(genai.types.Content(role="user", parts=response_parts))

    return "Sorry, I couldn't complete this after multiple attempts."


def run_agent(client, system_instruction, tool_functions, tools_by_name, user_message, model="gemini-3.6-flash"):
    history = [genai.types.Content(role="user", parts=[genai.types.Part(text=user_message)])]

    while True:
        reply = run_turn(client, system_instruction, tool_functions, tools_by_name, history, model)
        print(f"Agent: {reply}")

        # This is temporary for testing so the user can have turns with the agent
        user_input = input("You: ")
        if user_input.strip().lower() in ("quit", "exit"):
            break
        history.append(genai.types.Content(role="user", parts=[genai.types.Part(text=user_input)]))


def main():
    load_dotenv()  # Load environment variables from .env file
    client = genai.Client()

    service = get_calendar_service()


    def list_events_tool(start_datetime: str, end_datetime: str, max_results: int = 10) -> list:
        """
        List events on the user's Google Calendar within a time range.

        Args:
            start_datetime: Start of the range, RFC3339 with UTC offset,
                e.g. "2026-07-28T00:00:00-07:00". Choose a range appropriate
                to the request — the full day for checking conflicts around
                a specific event, or the relevant period for an open-ended query.
            end_datetime: End of the range, RFC3339 with UTC offset.
            max_results: The maximum number of events to return.
        """
        return list_events(service, start_datetime, end_datetime, max_results)




    def create_event_tool(summary: str, start_datetime: str, end_datetime: str, timezone: str = "America/Los_Angeles") -> dict:
        """
        Create an event on the user's Google Calendar.

        Args:
            summary: The title of the event.
            start_datetime: Start time in ISO 8601 format, e.g. "2026-07-28T15:00:00".
            end_datetime: End time in ISO 8601 format, e.g. "2026-07-28T15:30:00".
            timezone: IANA timezone name, e.g. "America/Los_Angeles".
        """
        return create_event(service, summary, start_datetime, end_datetime, timezone)


    def update_event_tool(event_id: str, summary: str = None, start_datetime: str = None, end_datetime: str = None, timezone: str = None) -> dict:
        """
        Update an existing event on the user's Google Calendar. Only pass the
        fields that should actually change; leave the rest unset.

        Args:
            event_id: The ID of the event to update, from a prior list_events call.
            summary: New title for the event, if changing.
            start_datetime: New start time, RFC3339 with UTC offset, if changing.
            end_datetime: New end time, RFC3339 with UTC offset, if changing.
            timezone: New IANA timezone name, if changing.
        """

        return update_event(service, event_id, summary, start_datetime, end_datetime, timezone)


    def delete_event_tool(event_id: str) -> str:
        """
        Delete an event from the user's Google Calendar.

        Args:
            event_id: The ID of the event to delete, from a prior list_events call.
        """

        delete_event(service, event_id)
        return f"Event deleted: {event_id}"


    def remember_fact(key: str, fact: str) -> str:
        """
        Store or update a fact about the user's preferences in long-term memory.
        If this fact matches something already known (check the current known
        facts provided in your instructions), reuse that same key to update it
        rather than creating a new one.

        Args:
            key: A short, consistent identifier for this fact, e.g. "lunch_default_time".
            fact: The fact's value, e.g. "12:00".
        """
        memory = load_memory()
        memory[key] = fact
        save_memory(memory)
        return f"Fact remembered: {key} = {fact}"

    tool_functions = [create_event_tool, list_events_tool, update_event_tool, delete_event_tool, remember_fact]
    tools_by_name = {fn.__name__: fn for fn in tool_functions}

    # Get the current date and time
    today_str = datetime.now().astimezone().isoformat()

    # Get the local timezone name
    local_tz = get_localzone_name()  # e.g. "America/New_York"

    # Load previously remembered facts from memory
    memory = load_memory()
    memory_str = "\n".join(f"- {k}: {v}" for k, v in memory.items()) or "No stored preferences yet."

    # System instruction for the model, including the current date/time and user's timezone
    system_instruction = (
        f"The current date and time is {today_str}. The user's timezone is {local_tz}. "
        "You are a calendar assistant. Only use your tools to manage the user's Google "
        "Calendar. If the user asks something unrelated to their calendar, politely "
        "decline and explain that you can only help with calendar-related requests. "
        "Before creating any new event, always first check the user's calendar for "
        "conflicts in that time window using list_events. If there is  a conflict, "
        "inform the user and ask whether to proceed or choose another time; only "
        "create the event after they confirm. "
        f"Known user preferences from past sessions:\n{memory_str}\n"
        "Take these into account when interpreting requests."
    )


    run_agent(client, system_instruction, tool_functions, tools_by_name,
                              "Schedule a test event tomorrow at 3pm for 30 minutes")




if __name__ == "__main__":
    main()