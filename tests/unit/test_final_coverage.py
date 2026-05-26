"""
Final coverage patch — targets every remaining uncovered line:

cache_manager.py  47-49  : logger.debug in ensure_cache_directory
service_checker.py 85-92 : _error_response body lines
service_checker.py 172   : duplicate-incident logger.debug
service_checker.py 541-548: generic HTTP 4xx branch via raise_for_status()
service_checker.py 588-590: check_service_status dispatcher body
slack_notify.py 44       : _get_webhook_url return
slack_notify.py 60-61    : _format_affected non-list branch
service_monitor.py 178   : no-cache fallback log line
service_monitor.py 252-257: normalize_timestamp regex path
service_monitor.py 353-358: _update_status_and_app_timestamp body
service_monitor.py 417-428: _update_active_incidents empty sentinel
service_monitor.py 529-533: _update_gauges_for_service from_cache path
service_monitor.py 544-547: resolved incident notify
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest
import responses as rsps_lib
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SERVICES_ONE = {"svc_a": {"name": "Service A", "url": "https://example.com"}}

_GAUGE_PATCHES = [
    "service_monitor.statuspage_status_gauge",
    "service_monitor.statuspage_response_time_gauge",
    "service_monitor.statuspage_incident_info",
    "service_monitor.statuspage_maintenance_info",
    "service_monitor.statuspage_component_status",
    "service_monitor.statuspage_component_timestamp",
    "service_monitor.statuspage_probe_check",
    "service_monitor.statuspage_application_timestamp",
]


def _apply_gauge_patches(func):
    for p in reversed(_GAUGE_PATCHES):
        func = patch(p)(func)
    return func


def _ok_result(**kwargs):
    base = {
        "success": True,
        "status": 1,
        "raw_status": "none",
        "status_text": "Operational",
        "details": "All good",
        "response_time": 0.5,
        "incident_metadata": [],
        "maintenance_metadata": [],
        "component_metadata": [{"name": "API", "status": "operational", "status_value": 1}],
        "from_cache": False,
        "original_failure": None,
    }
    base.update(kwargs)
    return base


def _fail_result():
    return {
        "success": False,
        "status": None,
        "raw_status": "timeout",
        "status_text": "Timeout",
        "details": "Request timed out",
        "response_time": 0.0,
        "error": "Timed out",
        "incident_metadata": [],
        "maintenance_metadata": [],
        "component_metadata": [],
        "from_cache": False,
        "original_failure": None,
    }


# ---------------------------------------------------------------------------
# cache_manager — lines 47-49
# Calling ensure_cache_directory() on a brand-new path exercises mkdir + debug log
# ---------------------------------------------------------------------------

def test_ensure_cache_directory_debug_log(tmp_path, caplog):
    """Calling ensure_cache_directory on a new path hits the mkdir + logger.debug lines."""
    import logging
    from cache_manager import ensure_cache_directory

    new_dir = tmp_path / "fresh_cache_dir"
    assert not new_dir.exists()

    with patch("cache_manager.get_cache_directory", return_value=new_dir), \
         caplog.at_level(logging.DEBUG, logger="cache_manager"):
        result = ensure_cache_directory()

    assert result == new_dir
    assert new_dir.exists()
    # The debug message confirms lines 47-49 executed
    assert any("Cache directory ensured" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# service_checker — lines 85-92 (_error_response)
# Import at module level to avoid coverage-miss due to lazy import
# ---------------------------------------------------------------------------

from service_checker import (  # noqa: E402  (after sys.path insert)
    _error_response,
    _build_incident_metadata_and_severity,
    check_service_status,
)


def test_error_response_all_lines():
    """Call _error_response and assert every key so all body lines are hit."""
    result = _error_response("svc", "timeout", "Timeout", "detail", "err")
    assert result["status"] is None
    assert result["response_time"] == 0
    assert result["raw_status"] == "timeout"
    assert result["status_text"] == "Timeout"
    assert result["details"] == "detail"
    assert result["success"] is False
    assert result["error"] == "err"
    assert result["incident_metadata"] == []
    assert result["maintenance_metadata"] == []
    assert result["component_metadata"] == []


# ---------------------------------------------------------------------------
# service_checker — line 172 (duplicate incident logger.debug)
# ---------------------------------------------------------------------------

def test_duplicate_incident_debug_log(caplog, tmp_path):
    """Passing the same incident twice hits the else/logger.debug dedup branch."""
    import logging

    inc = {
        "id": "dup1",
        "name": "Dup Incident",
        "status": "investigating",
        "impact": "minor",
        "shortlink": "https://stspg.io/dup1",
        "started_at": "2025-05-01T12:00:00Z",
        "components": [],
    }
    with patch("cache_manager.get_cache_directory", return_value=tmp_path), \
         caplog.at_level(logging.DEBUG, logger="service_checker"):
        meta, desc, sev = _build_incident_metadata_and_severity(
            [inc, inc],  # duplicate triggers the else branch at line 172
            {"url": "https://status.example.com/api/v2/summary.json"},
            "svc",
        )

    assert len(meta) == 1
    assert any("duplicate incident" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# service_checker — lines 541-548 (generic 4xx via raise_for_status)
# Use passthrough_prefixes so responses doesn't intercept the retry adapter,
# then mock the session directly so raise_for_status() fires before retries
# exhaust.
# ---------------------------------------------------------------------------

def test_http_403_returns_auth_error(tmp_path):
    """403 hits the 401/403 auth-error branch inside the HTTPError handler."""
    from service_checker import check_status_page_service

    mock_response = MagicMock()
    mock_response.status_code = 403
    http_err = requests.exceptions.HTTPError(response=mock_response)
    mock_response.raise_for_status.side_effect = http_err

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch("cache_manager.get_cache_directory", return_value=tmp_path), \
         patch("service_checker.create_retry_session", return_value=mock_session):
        result = check_status_page_service(
            "example",
            {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"},
        )

    assert result["success"] is False
    assert result["raw_status"] == "http_auth_error"


def test_http_422_returns_4xx_error(tmp_path):
    """422 hits the generic 400-499 branch (lines 541-548)."""
    from service_checker import check_status_page_service

    mock_response = MagicMock()
    mock_response.status_code = 422
    http_err = requests.exceptions.HTTPError(response=mock_response)
    mock_response.raise_for_status.side_effect = http_err

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch("cache_manager.get_cache_directory", return_value=tmp_path), \
         patch("service_checker.create_retry_session", return_value=mock_session):
        result = check_status_page_service(
            "example",
            {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"},
        )

    assert result["success"] is False
    assert result["raw_status"] == "http_4xx_error"


def test_http_503_returns_5xx_error(tmp_path):
    """503 hits the 500-599 server-error branch."""
    from service_checker import check_status_page_service

    mock_response = MagicMock()
    mock_response.status_code = 503
    http_err = requests.exceptions.HTTPError(response=mock_response)
    mock_response.raise_for_status.side_effect = http_err

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch("cache_manager.get_cache_directory", return_value=tmp_path), \
         patch("service_checker.create_retry_session", return_value=mock_session):
        result = check_status_page_service(
            "example",
            {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"},
        )

    assert result["success"] is False
    assert result["raw_status"] == "http_5xx_error"


# ---------------------------------------------------------------------------
# service_checker — lines 588-590 (check_service_status dispatcher)
# Import at top level so coverage sees the function body executed
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_check_service_status_top_level_import(tmp_path):
    """Call check_service_status (top-level import) to cover dispatcher lines."""
    rsps_lib.add(
        rsps_lib.GET,
        "https://status.example.com/api/v2/summary.json",
        json={
            "status": {"indicator": "none", "description": "All good"},
            "incidents": [],
            "scheduled_maintenances": [],
            "components": [],
        },
        status=200,
    )
    with patch("cache_manager.get_cache_directory", return_value=tmp_path):
        result = check_service_status(
            "example",
            {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"},
        )
    assert result["success"] is True
    assert result["status"] == 1


# ---------------------------------------------------------------------------
# slack_notify — line 44 (_get_webhook_url) and lines 60-61 (_format_affected)
# Import at top level
# ---------------------------------------------------------------------------

from slack_notify import _get_webhook_url, _format_affected  # noqa: E402


def test_get_webhook_url_top_level(monkeypatch):
    """_get_webhook_url imported at top level — covers line 44."""
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/top")
    assert _get_webhook_url() == "https://hooks.slack.com/top"


def test_format_affected_string_branch():
    """affected_components is a non-empty string — hits the str() branch (lines 60-61)."""
    result = _format_affected({"affected_components": "Database"})
    assert result == "Database"


def test_format_affected_empty_string():
    """Empty string is falsy — hits the '—' fallback."""
    result = _format_affected({"affected_components": ""})
    assert result == "—"


# ---------------------------------------------------------------------------
# service_monitor — line 178 (no-cache after failure log)
# ---------------------------------------------------------------------------

def test_check_service_with_fallback_logs_no_cache(caplog, tmp_path):
    """After a failure with no cache, the 'no cached data' warning is logged (line 178)."""
    import logging
    from service_monitor import check_service_with_fallback

    with patch("service_monitor.check_service_status", return_value=_fail_result()), \
         patch("service_monitor.load_service_response", return_value=None), \
         caplog.at_level(logging.WARNING, logger="service_monitor"):
        item = check_service_with_fallback(
            "svc_a", {"name": "Service A", "url": "https://example.com"}
        )

    assert item["result"]["from_cache"] is False
    assert any("no cached data" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# service_monitor — lines 252-257 (normalize_timestamp regex)
# Import at top level
# ---------------------------------------------------------------------------

from service_monitor import normalize_timestamp  # noqa: E402


def test_normalize_timestamp_with_millis():
    assert normalize_timestamp("2025-11-04T13:25:38.181Z") == "2025-11-04T13:25:38Z"
    assert normalize_timestamp("2025-01-01T00:00:00.000Z") == "2025-01-01T00:00:00Z"


def test_normalize_timestamp_without_millis():
    assert normalize_timestamp("2025-11-04T13:25:38Z") == "2025-11-04T13:25:38Z"


def test_normalize_timestamp_none_and_sentinels():
    assert normalize_timestamp(None) is None
    assert normalize_timestamp("N/A") == "N/A"
    assert normalize_timestamp("unknown") == "unknown"
    assert normalize_timestamp("") == ""


# ---------------------------------------------------------------------------
# service_monitor — lines 353-358 (_update_status_and_app_timestamp)
# Import at top level
# ---------------------------------------------------------------------------

from service_monitor import (  # noqa: E402
    _update_status_and_app_timestamp,
    _update_active_incidents,
)


@_apply_gauge_patches
def test_update_status_and_app_timestamp_top_level(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    _update_status_and_app_timestamp("Svc", 0, 9999999999000)
    mock_status.labels.assert_called_with(service_name="Svc")
    mock_status.labels.return_value.set.assert_called_with(0)
    mock_app_ts.labels.assert_called_with(service_name="Svc")
    mock_app_ts.labels.return_value.set.assert_called_with(9999999999000)


# ---------------------------------------------------------------------------
# service_monitor — lines 417-428 (_update_active_incidents empty sentinel)
# ---------------------------------------------------------------------------

@_apply_gauge_patches
def test_update_active_incidents_empty_top_level(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    _update_active_incidents("Svc", [], False, {}, set())
    kwargs = mock_inc.labels.call_args[1]
    assert kwargs["incident_id"] == "none"
    assert kwargs["incident_name"] == "No Active Incidents"
    mock_inc.labels.return_value.set.assert_called_with(0)


# ---------------------------------------------------------------------------
# service_monitor — lines 529-533 (from_cache probe path) and 544-547 (notify resolved)
# These need monitor_services called with the right state
# ---------------------------------------------------------------------------

@patch("service_monitor.SERVICES", SERVICES_ONE)
@patch("service_monitor.check_service_status", return_value={**_ok_result(), "from_cache": True})
@patch("service_monitor.load_service_response", return_value=None)
@_apply_gauge_patches
def test_from_cache_true_sets_probe_to_one(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
    mock_load, mock_check,
):
    from service_monitor import monitor_services
    monitor_services(is_initial_run=False)
    # success=True and from_cache=True → probe_success = 1
    mock_probe.labels.return_value.set.assert_called_with(1)


@patch("service_monitor.SERVICES", SERVICES_ONE)
@patch("service_monitor.check_service_status", return_value=_ok_result(incident_metadata=[]))
@patch("service_monitor.load_service_response", return_value={
    "status": 0,
    "incident_metadata": [
        {
            "id": "old_inc",
            "name": "Old Outage",
            "impact": "major",
            "shortlink": "https://stspg.io/old",
            "started_at": "2025-05-01T12:00:00Z",
            "affected_components": ["API"],
        }
    ],
    "maintenance_metadata": [],
    "component_metadata": [],
})
@patch("service_monitor.notify_incident_resolved")
@patch("service_monitor.notify_incident_opened")
@_apply_gauge_patches
def test_resolved_incident_notify_called(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
    mock_opened, mock_resolved, mock_load, mock_check,
):
    from service_monitor import monitor_services
    monitor_services(is_initial_run=False)
    mock_resolved.assert_called_once()
    assert mock_resolved.call_args[0][0] == "Service A"
    assert mock_resolved.call_args[0][1]["id"] == "old_inc"