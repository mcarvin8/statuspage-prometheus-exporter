"""
Additional service_monitor tests to cover missing lines:
  167-178: check_service_with_fallback — failed check + cache hit path
  222    : failed check + no cache available log
  252-257: normalize_timestamp regex substitution
  325-334: _clear_gauges initial run (clear ALL gauges)
  353-358: _update_status_and_app_timestamp
  390-403: _clear_resolved_incidents
  417-428: _update_active_incidents empty → 'none' sentinel branch
  451-452: _clear_resolved_maintenance
  499-507: _clear_removed_components
  529-533: _update_gauges_for_service from_cache=True path
  544-547: resolved incident → notify_incident_resolved called
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# ── shared mock result builders ───────────────────────────────────────────────

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
    """Decorator: patch all gauges for a test function."""
    for p in reversed(_GAUGE_PATCHES):
        func = patch(p)(func)
    return func


# ── lines 252-257: normalize_timestamp ───────────────────────────────────────

def test_normalize_timestamp_strips_milliseconds():
    from service_monitor import normalize_timestamp
    assert normalize_timestamp("2025-11-04T13:25:38.181Z") == "2025-11-04T13:25:38Z"
    assert normalize_timestamp("2025-11-04T13:25:38.000Z") == "2025-11-04T13:25:38Z"
    assert normalize_timestamp("2025-11-04T13:25:38.123+00:00") == "2025-11-04T13:25:38+00:00"


def test_normalize_timestamp_passthrough():
    from service_monitor import normalize_timestamp
    assert normalize_timestamp("N/A") == "N/A"
    assert normalize_timestamp("unknown") == "unknown"
    assert normalize_timestamp("") == ""
    assert normalize_timestamp(None) is None
    # Already no milliseconds
    assert normalize_timestamp("2025-11-04T13:25:38Z") == "2025-11-04T13:25:38Z"


# ── lines 167-178: check_service_with_fallback — cache hit on failure ─────────

def test_check_service_with_fallback_uses_cache_on_failure():
    from service_monitor import check_service_with_fallback

    cached = _ok_result()
    cached.pop("from_cache", None)
    cached.pop("original_failure", None)

    with patch("service_monitor.check_service_status", return_value=_fail_result()), \
         patch("service_monitor.load_service_response", return_value=cached):
        item = check_service_with_fallback("svc_a", {"name": "Service A", "url": "https://example.com"})

    assert item["result"]["from_cache"] is True
    assert item["result"]["status"] == 1


# ── line 222: failed check + no cache ────────────────────────────────────────

def test_check_service_with_fallback_no_cache_on_failure():
    from service_monitor import check_service_with_fallback

    with patch("service_monitor.check_service_status", return_value=_fail_result()), \
         patch("service_monitor.load_service_response", return_value=None):
        item = check_service_with_fallback("svc_a", {"name": "Service A", "url": "https://example.com"})

    assert item["result"]["from_cache"] is False
    assert item["result"]["success"] is False


# ── lines 325-334: _clear_gauges initial run clears ALL ──────────────────────

@_apply_gauge_patches
def test_clear_gauges_initial_run_clears_all(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    from service_monitor import _clear_gauges
    _clear_gauges(is_initial_run=True)
    mock_status.clear.assert_called_once()
    mock_rt.clear.assert_called_once()
    mock_inc.clear.assert_called_once()
    mock_maint.clear.assert_called_once()
    mock_comp.clear.assert_called_once()
    mock_comp_ts.clear.assert_called_once()
    mock_probe.clear.assert_called_once()
    mock_app_ts.clear.assert_called_once()


# ── lines 353-358: _update_status_and_app_timestamp ─────────────────────────

@_apply_gauge_patches
def test_update_status_and_app_timestamp(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    from service_monitor import _update_status_and_app_timestamp
    _update_status_and_app_timestamp("Service A", 1, 1234567890000)
    mock_status.labels.assert_called_with(service_name="Service A")
    mock_status.labels.return_value.set.assert_called_with(1)
    mock_app_ts.labels.assert_called_with(service_name="Service A")
    mock_app_ts.labels.return_value.set.assert_called_with(1234567890000)


# ── lines 390-403: _clear_resolved_incidents ─────────────────────────────────

@_apply_gauge_patches
def test_clear_resolved_incidents(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    from service_monitor import _clear_resolved_incidents

    cached_by_id = {
        "inc1": {
            "id": "inc1",
            "name": "API Down",
            "impact": "major",
            "shortlink": "https://stspg.io/inc1",
            "started_at": "2025-05-01T12:00:00Z",
            "affected_components": ["API"],
        }
    }
    _clear_resolved_incidents("Service A", {"inc1"}, cached_by_id)
    mock_inc.labels.assert_called_once()
    mock_inc.labels.return_value.set.assert_called_with(0)


# ── lines 417-428: _update_active_incidents with empty list → 'none' ─────────

@_apply_gauge_patches
def test_update_active_incidents_empty_sets_none_sentinel(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    from service_monitor import _update_active_incidents
    _update_active_incidents("Service A", [], False, {}, set())
    mock_inc.labels.assert_called_once()
    call_kwargs = mock_inc.labels.call_args[1]
    assert call_kwargs["incident_id"] == "none"
    assert call_kwargs["incident_name"] == "No Active Incidents"
    mock_inc.labels.return_value.set.assert_called_with(0)


# ── lines 451-452: _clear_resolved_maintenance ───────────────────────────────

@_apply_gauge_patches
def test_clear_resolved_maintenance(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    from service_monitor import _clear_resolved_maintenance

    cached_by_id = {
        "maint1": {
            "id": "maint1",
            "name": "DB Upgrade",
            "scheduled_start": "2025-06-01T02:00:00Z",
            "scheduled_end": "2025-06-01T04:00:00Z",
            "shortlink": "https://stspg.io/maint1",
            "affected_components": ["DB"],
        }
    }
    _clear_resolved_maintenance("Service A", {"maint1"}, cached_by_id)
    mock_maint.labels.assert_called_once()
    mock_maint.labels.return_value.set.assert_called_with(0)


# ── lines 499-507: _clear_removed_components ─────────────────────────────────

@_apply_gauge_patches
def test_clear_removed_components(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
):
    from service_monitor import _clear_removed_components
    _clear_removed_components("Service A", {"Old Component"})
    mock_comp.labels.assert_called_with(service_name="Service A", component_name="Old Component")
    mock_comp.labels.return_value.set.assert_called_with(0)


# ── lines 529-533: from_cache=True path in _update_gauges_for_service ────────

@patch("service_monitor.SERVICES", SERVICES_ONE)
@patch("service_monitor.check_service_status", return_value={
    **_ok_result(), "success": True, "from_cache": True,  # success=True, from_cache=True
})
@patch("service_monitor.load_service_response", return_value=None)
@_apply_gauge_patches
def test_monitor_services_from_cache_probe_set_to_one(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
    mock_load, mock_check,
):
    from service_monitor import monitor_services
    monitor_services(is_initial_run=False)
    mock_probe.labels.return_value.set.assert_called_with(1)


@patch("service_monitor.SERVICES", SERVICES_ONE)
@patch("service_monitor.check_service_status", return_value=_ok_result(incident_metadata=[]))
@patch("service_monitor.load_service_response", return_value={   # moved from 'with' to decorator
    "status": 0,
    "incident_metadata": [
        {
            "id": "inc_old",
            "name": "Was Active",
            "impact": "major",
            "shortlink": "https://stspg.io/inc_old",
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
def test_resolved_incident_calls_notify(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp,
    mock_maint, mock_inc, mock_rt, mock_status,
    mock_opened, mock_resolved, mock_load, mock_check,  # now 12 args, matching 12 decorators
):
    from service_monitor import monitor_services
    monitor_services(is_initial_run=False)
    mock_resolved.assert_called_once()
    call_args = mock_resolved.call_args
    assert call_args[0][0] == "Service A"
    assert call_args[0][1]["id"] == "inc_old"