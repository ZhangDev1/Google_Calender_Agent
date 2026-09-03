from unittest.mock import MagicMock, patch

from agent import create_event, get_calendar_service


# ---- create_event ----

def test_create_event_calls_api_with_correct_body():
    mock_service = MagicMock()
    mock_service.events().insert().execute.return_value = {"id": "abc123", "summary": "Test"}

    result = create_event(
        mock_service, "Test", "2026-07-28T10:00:00", "2026-07-28T11:00:00", "America/Los_Angeles"
    )

    mock_service.events().insert.assert_called_with(
        calendarId="primary",
        body={
            "summary": "Test",
            "start": {"dateTime": "2026-07-28T10:00:00", "timeZone": "America/Los_Angeles"},
            "end": {"dateTime": "2026-07-28T11:00:00", "timeZone": "America/Los_Angeles"},
        },
    )
    assert result == {"id": "abc123", "summary": "Test"}


def test_create_event_uses_default_timezone():
    mock_service = MagicMock()
    mock_service.events().insert().execute.return_value = {"id": "xyz"}

    create_event(mock_service, "Standup", "2026-07-28T09:00:00", "2026-07-28T09:15:00")

    _, kwargs = mock_service.events().insert.call_args
    assert kwargs["body"]["start"]["timeZone"] == "America/Los_Angeles"


# ---- get_calendar_service ----

@patch("agent.build")
@patch("agent.InstalledAppFlow")
@patch("agent.Credentials")
def test_uses_valid_cached_token(mock_credentials_cls, mock_flow_cls, mock_build, tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")

    mock_creds = MagicMock(valid=True)
    mock_credentials_cls.from_authorized_user_file.return_value = mock_creds

    get_calendar_service(token_path=token_path)

    mock_credentials_cls.from_authorized_user_file.assert_called_once()
    mock_creds.refresh.assert_not_called()
    mock_flow_cls.from_client_secrets_file.assert_not_called()
    mock_build.assert_called_once_with("calendar", "v3", credentials=mock_creds)


@patch("agent.build")
@patch("agent.InstalledAppFlow")
@patch("agent.Credentials")
def test_refreshes_expired_token(mock_credentials_cls, mock_flow_cls, mock_build, tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")

    mock_creds = MagicMock(valid=False, expired=True, refresh_token="refresh-me")
    mock_creds.to_json.return_value = "{}"

    def fake_refresh(request):
        mock_creds.valid = True  # mirrors real Credentials: valid flips true after a successful refresh

    mock_creds.refresh.side_effect = fake_refresh
    mock_credentials_cls.from_authorized_user_file.return_value = mock_creds

    get_calendar_service(token_path=token_path)

    mock_creds.refresh.assert_called_once()
    mock_flow_cls.from_client_secrets_file.assert_not_called()
    mock_build.assert_called_once_with("calendar", "v3", credentials=mock_creds)


@patch("agent.build")
@patch("agent.InstalledAppFlow")
@patch("agent.Credentials")
def test_falls_back_to_full_reauth_when_refresh_fails(mock_credentials_cls, mock_flow_cls, mock_build, tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")

    mock_creds = MagicMock(valid=False, expired=True, refresh_token="refresh-me")
    mock_creds.refresh.side_effect = Exception("network error")
    mock_credentials_cls.from_authorized_user_file.return_value = mock_creds

    mock_new_creds = MagicMock()
    mock_new_creds.to_json.return_value = "{}"
    mock_flow_instance = MagicMock()
    mock_flow_instance.credentials = mock_new_creds
    mock_flow_cls.from_client_secrets_file.return_value = mock_flow_instance

    get_calendar_service(token_path=token_path)

    mock_creds.refresh.assert_called_once()
    mock_flow_cls.from_client_secrets_file.assert_called_once()
    mock_flow_instance.run_local_server.assert_called_once()
    mock_build.assert_called_once_with("calendar", "v3", credentials=mock_new_creds)


@patch("agent.build")
@patch("agent.InstalledAppFlow")
@patch("agent.Credentials")
def test_runs_full_auth_flow_when_no_token_file(mock_credentials_cls, mock_flow_cls, mock_build, tmp_path):
    token_path = tmp_path / "token.json"  # deliberately never created

    mock_new_creds = MagicMock()
    mock_new_creds.to_json.return_value = "{}"
    mock_flow_instance = MagicMock()
    mock_flow_instance.credentials = mock_new_creds
    mock_flow_cls.from_client_secrets_file.return_value = mock_flow_instance

    get_calendar_service(token_path=token_path)

    mock_credentials_cls.from_authorized_user_file.assert_not_called()
    mock_flow_instance.run_local_server.assert_called_once()
    mock_build.assert_called_once_with("calendar", "v3", credentials=mock_new_creds)
