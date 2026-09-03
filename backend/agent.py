from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from pathlib import Path


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
                "client_secret_47034214311-jvaau3v3idk6no14mjlv6o83vq9k8a7h.apps.googleusercontent.com.json",
                scopes=["https://www.googleapis.com/auth/calendar.events"]
            )
            flow.run_local_server(port=0)
            creds = flow.credentials

        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)
    
    return service


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