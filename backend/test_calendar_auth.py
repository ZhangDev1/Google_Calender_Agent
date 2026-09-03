from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# Initialize the flow
flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret_47034214311-jvaau3v3idk6no14mjlv6o83vq9k8a7h.apps.googleusercontent.com.json", scopes=["https://www.googleapis.com/auth/calendar.events"]
)

flow.run_local_server(port=0)

creds = flow.credentials
service = build('calendar', 'v3', credentials=creds)

service.events().insert(calendarId='primary', body={
    "summary": "Test event",
    "start": {"dateTime": "2026-07-28T10:00:00", "timeZone": "America/Los_Angeles"},
    "end": {"dateTime": "2026-07-28T11:00:00", "timeZone": "America/Los_Angeles"},
}
).execute()