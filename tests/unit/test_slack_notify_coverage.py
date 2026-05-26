"""
Additional slack_notify tests to cover missing lines:
  38 : slack_webhook_enabled returns True when URL set
  44 : _get_webhook_url returns the env value
  60-61: _format_affected when parts is not a list (str branch)
  105: notify_incident_resolved early-return when webhook disabled
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


# ── line 38: slack_webhook_enabled → True ────────────────────────────────────

def test_slack_webhook_enabled_true(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    from slack_notify import slack_webhook_enabled
    assert slack_webhook_enabled() is True


# ── line 44: _get_webhook_url returns value ───────────────────────────────────

def test_get_webhook_url_returns_env(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/abc")
    from slack_notify import _get_webhook_url
    assert _get_webhook_url() == "https://hooks.slack.com/services/abc"


# ── lines 60-61: _format_affected with non-list parts ────────────────────────

def test_format_affected_non_list_parts():
    from slack_notify import _format_affected
    # When affected_components is a plain string (non-list)
    result = _format_affected({"affected_components": "API"})
    assert result == "API"


def test_format_affected_empty():
    from slack_notify import _format_affected
    assert _format_affected({}) == "—"
    assert _format_affected({"affected_components": []}) == "—"
    assert _format_affected({"affected_components": None}) == "—"


# ── line 105: notify_incident_resolved skips when no webhook ─────────────────

def test_notify_incident_resolved_skipped_when_no_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    from slack_notify import notify_incident_resolved
    # Should return early without posting — no exception, no HTTP call
    with patch("slack_notify.requests.post") as mock_post:
        notify_incident_resolved("Service A", {"id": "inc1", "name": "Down", "shortlink": ""})
        mock_post.assert_not_called()
