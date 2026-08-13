"""
Final round of tests to close remaining coverage gaps:

cache_manager.py
  49     : get_cache_directory() real return value (not mocked away)

service_checker.py
  88-95  : module-level services.json fallback to services.json.example / raise
  179    : _extract_components else branch (unknown/unrecognized component status)
  554-555: check_status_page_service HTTPError generic else branch (unmapped status code)
  595-597: check_status_page_service generic Exception handler

service_monitor.py
  178    : check_service_with_fallback — cached data missing response_time key
  252-257: _run_checks_parallel — future.result() raises unexpected exception
  353-358: _update_active_incidents — cached-label branch (incident already known)
  417-428: _update_active_maintenance — non-empty maintenance loop
  529-533: _update_gauges_for_service — resolved maintenance branch
  544-547: _update_gauges_for_service — removed component branch

slack_notify.py
  44     : _post_webhook_async — no webhook URL configured, early return
  60-61  : _post_webhook_async._send — requests.post raises, exception logged
"""

import importlib
import os
from unittest.mock import patch

import pytest
import requests


# ── cache_manager.py:49 ───────────────────────────────────────────────────────

def test_get_cache_directory_returns_cwd_slash_cache():
    from statuspage_prometheus_exporter.cache_manager import get_cache_directory

    result = get_cache_directory()
    assert result == __import__("pathlib").Path.cwd() / "cache"


# ── service_checker.py:88-95 (module import-time fallback) ───────────────────

def test_service_checker_falls_back_to_example_when_services_json_missing(tmp_path):
    import statuspage_prometheus_exporter.service_checker as sc_module

    original_env = os.environ.get("SERVICES_JSON_PATH")
    os.environ["SERVICES_JSON_PATH"] = str(tmp_path / "nope.json")
    try:
        importlib.reload(sc_module)
        assert sc_module.config_path.endswith("services.json.example")
    finally:
        if original_env is not None:
            os.environ["SERVICES_JSON_PATH"] = original_env
        else:
            os.environ.pop("SERVICES_JSON_PATH", None)
        importlib.reload(sc_module)


def test_service_checker_raises_when_no_config_and_no_example(tmp_path):
    import statuspage_prometheus_exporter.service_checker as sc_module

    original_env = os.environ.get("SERVICES_JSON_PATH")
    os.environ["SERVICES_JSON_PATH"] = str(tmp_path / "nope.json")
    try:
        with patch("os.path.exists", return_value=False):
            with pytest.raises(FileNotFoundError):
                importlib.reload(sc_module)
    finally:
        if original_env is not None:
            os.environ["SERVICES_JSON_PATH"] = original_env
        else:
            os.environ.pop("SERVICES_JSON_PATH", None)
        importlib.reload(sc_module)


# ── service_checker.py:179 (unrecognized component status) ───────────────────

def test_extract_components_unrecognized_status_defaults_to_zero():
    from statuspage_prometheus_exporter.service_checker import _extract_components

    data = {"components": [{"name": "Weird", "status": "some_other_status"}]}
    component_metadata, _ = _extract_components(data, "svc")
    assert component_metadata[0]["status_value"] == 0


# ── service_checker.py:554-555 (HTTPError, unmapped status code) ─────────────

def test_check_status_page_service_http_error_unmapped_status_code():
    from statuspage_prometheus_exporter.service_checker import check_status_page_service

    mock_response = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_response.status_code = 999
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=mock_response
    )
    mock_session = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_session.get.return_value = mock_response

    with patch(
        "statuspage_prometheus_exporter.service_checker.create_retry_session",
        return_value=mock_session,
    ):
        result = check_status_page_service(
            "example", {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"}
        )

    assert result["success"] is False
    assert result["raw_status"] == "http_error"


# ── service_checker.py:595-597 (generic Exception handler) ───────────────────

def test_check_status_page_service_generic_exception():
    from statuspage_prometheus_exporter.service_checker import check_status_page_service

    mock_response = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = ["unexpected", "list", "not", "a", "dict"]
    mock_session = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_session.get.return_value = mock_response

    with patch(
        "statuspage_prometheus_exporter.service_checker.create_retry_session",
        return_value=mock_session,
    ):
        result = check_status_page_service(
            "example", {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"}
        )

    assert result["success"] is False
    assert result["raw_status"] == "unknown_error"


# ── service_monitor.py fixtures/helpers ───────────────────────────────────────

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
        "component_metadata": [],
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


SERVICES_ONE = {"svc_a": {"name": "Service A", "url": "https://example.com"}}

_GAUGE_PATCHES = [
    "statuspage_prometheus_exporter.service_monitor.statuspage_status_gauge",
    "statuspage_prometheus_exporter.service_monitor.statuspage_response_time_gauge",
    "statuspage_prometheus_exporter.service_monitor.statuspage_incident_info",
    "statuspage_prometheus_exporter.service_monitor.statuspage_maintenance_info",
    "statuspage_prometheus_exporter.service_monitor.statuspage_component_status",
    "statuspage_prometheus_exporter.service_monitor.statuspage_component_timestamp",
    "statuspage_prometheus_exporter.service_monitor.statuspage_probe_check",
    "statuspage_prometheus_exporter.service_monitor.statuspage_application_timestamp",
]


def _apply_gauge_patches(func):
    for p in reversed(_GAUGE_PATCHES):
        func = patch(p)(func)
    return func


# ── service_monitor.py:178 (cached data missing response_time) ───────────────

def test_check_service_with_fallback_cache_missing_response_time():
    from statuspage_prometheus_exporter.service_monitor import check_service_with_fallback

    cached = _ok_result()
    cached.pop("from_cache", None)
    cached.pop("original_failure", None)
    cached.pop("response_time", None)

    with patch(
        "statuspage_prometheus_exporter.service_monitor.check_service_status",
        return_value=_fail_result(),
    ), patch(
        "statuspage_prometheus_exporter.service_monitor.load_service_response",
        return_value=cached,
    ):
        item = check_service_with_fallback(
            "svc_a", {"name": "Service A", "url": "https://example.com"}
        )

    assert item["result"]["response_time"] == 0.0


# ── service_monitor.py:252-257 (unexpected exception in a worker future) ─────

@patch("statuspage_prometheus_exporter.service_monitor.SERVICES", SERVICES_ONE)
@patch(
    "statuspage_prometheus_exporter.service_monitor.check_service_with_fallback",
    side_effect=RuntimeError("boom"),
)
def test_run_checks_parallel_handles_unexpected_exception(mock_fallback):
    from statuspage_prometheus_exporter.service_monitor import _run_checks_parallel

    results = _run_checks_parallel()

    assert len(results) == 1
    assert results[0]["service_key"] == "svc_a"
    assert results[0]["result"]["success"] is False
    assert results[0]["result"]["raw_status"] == "unexpected_error"
    assert "boom" in results[0]["result"]["error"]


# ── service_monitor.py:353-358 (cached-label branch for known incident) ──────

@_apply_gauge_patches
def test_update_active_incidents_uses_cached_labels_for_known_incident(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    from statuspage_prometheus_exporter.service_monitor import _update_active_incidents

    cached_by_id = {
        "inc1": {
            "name": "Cached Name",
            "affected_components": ["API"],
            "impact": "major",
            "shortlink": "https://stspg.io/inc1",
            "started_at": "2025-05-01T12:00:00Z",
        }
    }
    incident_metadata = [
        {
            "id": "inc1",
            "name": "Live Name",
            "affected_components": ["Other"],
            "impact": "minor",
            "shortlink": "https://stspg.io/live",
            "started_at": "2025-05-02T12:00:00Z",
        }
    ]
    _update_active_incidents("Service A", incident_metadata, True, cached_by_id, {"inc1"})

    call_kwargs = mock_inc.labels.call_args[1]
    assert call_kwargs["incident_name"] == "Cached Name"
    assert call_kwargs["impact"] == "major"
    assert call_kwargs["shortlink"] == "https://stspg.io/inc1"


# ── service_monitor.py:417-428 (non-empty active maintenance loop) ───────────

@_apply_gauge_patches
def test_update_active_maintenance_nonempty(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    from statuspage_prometheus_exporter.service_monitor import _update_active_maintenance

    maintenance_metadata = [
        {
            "id": "maint1",
            "name": "DB Upgrade",
            "affected_components": ["DB"],
            "scheduled_start": "2025-06-01T02:00:00Z",
            "scheduled_end": "2025-06-01T04:00:00Z",
            "shortlink": "https://stspg.io/maint1",
        }
    ]
    _update_active_maintenance("Service A", maintenance_metadata)

    mock_maint.labels.assert_called_with(
        service_name="Service A",
        maintenance_id="maint1",
        maintenance_name="DB Upgrade",
        scheduled_start="2025-06-01T02:00:00Z",
        scheduled_end="2025-06-01T04:00:00Z",
        shortlink="https://stspg.io/maint1",
        affected_components="DB",
    )
    mock_maint.labels.return_value.set.assert_called_with(1)


# ── service_monitor.py:529-533, 544-547 (resolved maintenance + removed component) ──

@_apply_gauge_patches
def test_update_gauges_for_service_clears_resolved_maintenance_and_removed_component(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    from statuspage_prometheus_exporter.service_monitor import _update_gauges_for_service

    item = {
        "service_key": "svc_a",
        "service_config": {"name": "Service A"},
        "result": {
            "status": 1,
            "from_cache": False,
            "response_time": 0.5,
            "success": True,
            "incident_metadata": [],
            "maintenance_metadata": [],
            "component_metadata": [],
        },
    }
    previous_caches = {
        "svc_a": {
            "incident_metadata": [],
            "maintenance_metadata": [
                {
                    "id": "maint_old",
                    "name": "Old Maintenance",
                    "affected_components": ["DB"],
                    "scheduled_start": "2025-06-01T02:00:00Z",
                    "scheduled_end": "2025-06-01T04:00:00Z",
                    "shortlink": "https://stspg.io/maint_old",
                }
            ],
            "component_metadata": [
                {"name": "OldComponent", "status": "operational", "status_value": 1}
            ],
        }
    }

    _update_gauges_for_service(item, previous_caches)

    maint_calls = [c for c in mock_maint.labels.call_args_list if c.kwargs.get("maintenance_id") == "maint_old"]
    assert maint_calls
    mock_maint.labels.return_value.set.assert_any_call(0)

    mock_comp.labels.assert_any_call(service_name="Service A", component_name="OldComponent")
    mock_comp.labels.return_value.set.assert_any_call(0)


# ── slack_notify.py:44 (no webhook URL configured) ────────────────────────────

def test_post_webhook_async_no_url_returns_early(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    from statuspage_prometheus_exporter.slack_notify import _post_webhook_async

    with patch("statuspage_prometheus_exporter.slack_notify.requests.post") as mock_post:
        _post_webhook_async({"blocks": []})
        mock_post.assert_not_called()


# ── slack_notify.py:60-61 (requests.post raises inside worker thread) ────────

class _ImmediateThread:
    """Runs the target synchronously so the test can assert without waiting on a real thread."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


def test_post_webhook_async_request_exception_is_logged(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    from statuspage_prometheus_exporter.slack_notify import _post_webhook_async

    with patch(
        "statuspage_prometheus_exporter.slack_notify.requests.post",
        side_effect=RuntimeError("network boom"),
    ), patch(
        "statuspage_prometheus_exporter.slack_notify.threading.Thread", _ImmediateThread
    ):
        # Should not raise — the exception is caught and logged inside _send.
        _post_webhook_async({"blocks": []})
