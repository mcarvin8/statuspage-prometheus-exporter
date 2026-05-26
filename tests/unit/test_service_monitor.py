# tests/unit/test_service_monitor.py
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

MOCK_RESULT = {
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

MOCK_INCIDENT_RESULT = {
    **MOCK_RESULT,
    "status": 0,
    "raw_status": "major",
    "incident_metadata": [
        {
            "id": "inc1",
            "name": "API Down",
            "impact": "major",
            "shortlink": "https://stspg.io/inc1",
            "started_at": "2025-05-01T12:00:00Z",
            "affected_components": ["API"],
        }
    ],
}


@patch("service_monitor.SERVICES", {"svc_a": {"name": "Service A", "url": "https://example.com"}})
@patch("service_monitor.check_service_status", return_value=MOCK_RESULT)
@patch("service_monitor.load_service_response", return_value=None)
@patch("service_monitor.statuspage_status_gauge")
@patch("service_monitor.statuspage_response_time_gauge")
@patch("service_monitor.statuspage_incident_info")
@patch("service_monitor.statuspage_maintenance_info")
@patch("service_monitor.statuspage_component_status")
@patch("service_monitor.statuspage_component_timestamp")
@patch("service_monitor.statuspage_probe_check")
@patch("service_monitor.statuspage_application_timestamp")
def test_monitor_services_operational(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp, mock_maint,
    mock_inc, mock_rt, mock_status, mock_load, mock_check
):
    from service_monitor import monitor_services
    monitor_services(is_initial_run=True)
    mock_status.labels.assert_called()
    mock_probe.labels.assert_called()


@patch("service_monitor.SERVICES", {"svc_a": {"name": "Service A", "url": "https://example.com"}})
@patch("service_monitor.check_service_status", return_value=MOCK_INCIDENT_RESULT)
@patch("service_monitor.load_service_response", return_value=None)
@patch("service_monitor.notify_incident_opened")
@patch("service_monitor.statuspage_status_gauge")
@patch("service_monitor.statuspage_response_time_gauge")
@patch("service_monitor.statuspage_incident_info")
@patch("service_monitor.statuspage_maintenance_info")
@patch("service_monitor.statuspage_component_status")
@patch("service_monitor.statuspage_component_timestamp")
@patch("service_monitor.statuspage_probe_check")
@patch("service_monitor.statuspage_application_timestamp")
def test_monitor_services_notifies_new_incident(
    mock_app_ts, mock_probe, mock_comp_ts, mock_comp, mock_maint,
    mock_inc, mock_rt, mock_status, mock_notify, mock_load, mock_check
):
    from service_monitor import monitor_services
    monitor_services(is_initial_run=False)
    mock_notify.assert_called_once()


@patch("service_monitor.SERVICES", {"svc_a": {"name": "Service A", "url": "https://example.com"}})
@patch("service_monitor.check_service_status", return_value={**MOCK_RESULT, "success": False, "status": None})
@patch("service_monitor.load_service_response", return_value=None)
@patch("service_monitor.statuspage_probe_check")
@patch("service_monitor.statuspage_response_time_gauge")
@patch("service_monitor.statuspage_status_gauge")
@patch("service_monitor.statuspage_incident_info")
@patch("service_monitor.statuspage_maintenance_info")
@patch("service_monitor.statuspage_component_status")
@patch("service_monitor.statuspage_component_timestamp")
@patch("service_monitor.statuspage_application_timestamp")
def test_monitor_services_failed_check_skips_gauge(
    mock_app_ts, mock_comp_ts, mock_comp, mock_maint, mock_inc,
    mock_status, mock_rt, mock_probe, mock_load, mock_check
):
    from service_monitor import monitor_services
    monitor_services(is_initial_run=False)
    # status gauge should not be set when status is None
    mock_status.labels.return_value.set.assert_not_called()