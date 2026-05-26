# tests/unit/test_slack_notify.py
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

INCIDENT = {
    "id": "inc1",
    "name": "API Down",
    "impact": "major",
    "shortlink": "https://stspg.io/inc1",
    "started_at": "2025-05-01T12:00:00Z",
    "affected_components": ["API", "Web"],
}


def test_notify_skipped_when_no_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    from slack_notify import notify_incident_opened
    # should not raise
    notify_incident_opened("Service A", INCIDENT)


@patch("slack_notify.requests.post")
def test_notify_incident_opened_posts_webhook(mock_post, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    mock_post.return_value.status_code = 200
    from slack_notify import notify_incident_opened
    import time
    notify_incident_opened("Service A", INCIDENT)
    time.sleep(0.1)  # let the daemon thread fire
    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "API Down" in payload["blocks"][0]["text"]["text"]


@patch("slack_notify.requests.post")
def test_notify_incident_resolved_posts_webhook(mock_post, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    mock_post.return_value.status_code = 200
    from slack_notify import notify_incident_resolved
    import time
    notify_incident_resolved("Service A", INCIDENT)
    time.sleep(0.1)
    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "resolved" in payload["blocks"][0]["text"]["text"].lower()


@patch("slack_notify.requests.post")
def test_notify_logs_warning_on_non_200(mock_post, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    mock_post.return_value.status_code = 500
    mock_post.return_value.text = "Internal Server Error"
    from slack_notify import notify_incident_opened
    import time
    notify_incident_opened("Service A", INCIDENT)
    time.sleep(0.1)
    mock_post.assert_called_once()