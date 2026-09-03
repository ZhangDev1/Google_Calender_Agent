from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.service_account import Credentials

from pathlib import Path

from httpcore import Request


def get_calendar_service():
    """
    Authenticate and return the Google Calendar service object.

    Returns:
        googleapiclient.discovery.Resource: The Google Calendar service object.
    """

    token_path = Path("token.json")
    creds = None

    # Checks if the path exists AND is a file (returns True/False)
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(token_path, scopes=["https://www.googleapis.com/auth/calendar.events"])
        print("The token file exists.")


    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token is expired. Attempting refresh...")
            try:
                # This automatically handles the token refresh flow
                creds.refresh(Request())
                
                # Save the updated token back to your file
                with open('token.json', 'w') as token_file:
                    token_file.write(creds.to_json())
                print("Token refreshed successfully!")

            except Exception as e:
                print(f"Failed to refresh token: {e}")
                print("Re-authentication is required.")

        else:
            # Credentials are either not present or cannot be refreshed, so we need to re-authenticate
            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secret_47034214311-jvaau3v3idk6no14mjlv6o83vq9k8a7h.apps.googleusercontent.com.json",
                scopes=["https://www.googleapis.com/auth/calendar.events"]
            )
        
            flow.run_local_server(port=0)
            print("Re-authentication successful. Saving new token...")
    
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