from google import genai
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from pathlib import Path
from dotenv import load_dotenv

from datetime import datetime, timedelta
from tzlocal import get_localzone_name

MAX_RANGE_DAYS = 31

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
        list[dict]: Matching events, each with 'summary', 'start', 'end'.
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

    tool_functions = [create_event_tool, list_events_tool]
    tools_by_name = {fn.__name__: fn for fn in tool_functions}

    # Get the current date and time
    today_str = datetime.now().astimezone().isoformat()

    # Get the local timezone name
    local_tz = get_localzone_name()  # e.g. "America/New_York"

    # System instruction for the model, including the current date/time and user's timezone
    system_instruction = (
        f"The current date and time is {today_str}. The user's timezone is {local_tz}. "
        "You are a calendar assistant. Only use your tools to manage the user's Google "
        "Calendar. If the user asks something unrelated to their calendar, politely "
        "decline and explain that you can only help with calendar-related requests."
    )

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="Schedule a test event tomorrow at 3pm for 30 minutes",
        config = genai.types.GenerateContentConfig(
            tools=tool_functions,
            system_instruction=system_instruction,
            automatic_function_calling=genai.types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )


    for part in response.candidates[0].content.parts:
        if not part.function_call:
            continue

        call = part.function_call
        if call.name not in tools_by_name:
            print(f"Model requested unsupported tool '{call.name}' with args {call.args} — refusing to execute.")
            continue

        result = tools_by_name[call.name](**call.args)
        print(f"Executed {call.name} -> {result}")


    print(response.candidates[0].content.parts)

    if response.text:
        print(response.text)



if __name__ == "__main__":
    main()