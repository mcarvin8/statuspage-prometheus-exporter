import pytest
import responses as rsps_lib
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Minimal valid StatusPage.io response
OPERATIONAL_PAYLOAD = {
    "status": {"indicator": "none", "description": "All Systems Operational"},
    "incidents": [],
    "scheduled_maintenances": [],
    "components": [
        {"name": "API", "status": "operational"},
        {"name": "Web", "status": "operational"},
    ],
}

INCIDENT_PAYLOAD = {
    "status": {"indicator": "major", "description": "Major outage"},
    "incidents": [
        {
            "id": "abc123",
            "name": "API Degradation",
            "status": "investigating",
            "impact": "major",
            "shortlink": "https://stspg.io/abc123",
            "started_at": "2025-05-01T12:00:00Z",
            "resolved_at": None,
            "components": [{"name": "API"}],
        }
    ],
    "scheduled_maintenances": [],
    "components": [
        {"name": "API", "status": "major_outage"},
        {"name": "Web", "status": "operational"},
    ],
}


@pytest.fixture(autouse=True)
def no_cache(tmp_path, monkeypatch):
    """Redirect cache to a temp directory so unit tests are isolated."""
    monkeypatch.setenv("SERVICES_JSON_PATH", 
        str(Path(__file__).parent.parent.parent / "src" / "services.json"))
    with patch("cache_manager.get_cache_directory", return_value=tmp_path):
        yield


@rsps_lib.activate
def test_operational_response_returns_status_1():
    from service_checker import check_status_page_service
    rsps_lib.add(rsps_lib.GET, "https://status.example.com/api/v2/summary.json",
                 json=OPERATIONAL_PAYLOAD, status=200)
    result = check_status_page_service(
        "example", {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"}
    )
    assert result["success"] is True
    assert result["status"] == 1
    assert result["raw_status"] == "none"
    assert result["incident_metadata"] == []


@rsps_lib.activate
def test_active_incident_returns_status_0():
    from service_checker import check_status_page_service
    rsps_lib.add(rsps_lib.GET, "https://status.example.com/api/v2/summary.json",
                 json=INCIDENT_PAYLOAD, status=200)
    result = check_status_page_service(
        "example", {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"}
    )
    assert result["status"] == 0
    assert len(result["incident_metadata"]) == 1
    assert result["incident_metadata"][0]["id"] == "abc123"
    assert result["incident_metadata"][0]["impact"] == "major"


@rsps_lib.activate
def test_resolved_incident_excluded():
    """resolved_at set → incident should be filtered out."""
    from service_checker import check_status_page_service
    payload = dict(INCIDENT_PAYLOAD)
    payload["incidents"] = [
        {**INCIDENT_PAYLOAD["incidents"][0], "resolved_at": "2025-05-01T13:00:00Z"}
    ]
    rsps_lib.add(rsps_lib.GET, "https://status.example.com/api/v2/summary.json",
                 json=payload, status=200)
    result = check_status_page_service(
        "example", {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"}
    )
    assert result["incident_metadata"] == []


@rsps_lib.activate
def test_non_operational_component_without_incident_sets_minor():
    from service_checker import check_status_page_service
    payload = {
        **OPERATIONAL_PAYLOAD,
        "components": [
            {"name": "API", "status": "degraded_performance"},
            {"name": "Web", "status": "operational"},
        ],
    }
    rsps_lib.add(rsps_lib.GET, "https://status.example.com/api/v2/summary.json",
                 json=payload, status=200)
    result = check_status_page_service(
        "example", {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"}
    )
    assert result["status"] == 0
    assert result["raw_status"] == "minor"


@rsps_lib.activate
def test_http_404_returns_none_status():
    from service_checker import check_status_page_service
    rsps_lib.add(rsps_lib.GET, "https://status.example.com/api/v2/summary.json", status=404)
    result = check_status_page_service(
        "example", {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"}
    )
    assert result["success"] is False
    assert result["status"] is None
    assert result["raw_status"] == "http_404_not_found"


@rsps_lib.activate
def test_network_timeout_returns_none_status():
    from requests.exceptions import ConnectTimeout  # remove "import responses" line
    from service_checker import check_status_page_service
    rsps_lib.add(rsps_lib.GET, "https://status.example.com/api/v2/summary.json",
                 body=ConnectTimeout())
    result = check_status_page_service(
        "example", {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"}
    )
    assert result["success"] is False
    assert result["status"] is None