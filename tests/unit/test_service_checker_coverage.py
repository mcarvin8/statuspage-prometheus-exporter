"""
Additional service_checker tests to cover missing lines:
  85-92  : _error_response keys (maintenance_metadata, component_metadata)
  172    : duplicate incident dedup log
  227    : _get_active_maintenances completed/cancelled filter
  241-244: _build_incident_metadata_and_severity system-metadata skip
  248    : base_url construction from service URL
  274    : shortlink fallback (no shortlink in incident, but base_url present)
  297    : incident detail with no affected components
  323-368: _build_maintenance_metadata full path
  379-403: _preserve_labels_from_cache
  514,523: cache update/preserve log branches
  538-548: HTTP 4xx generic branch (e.g. 429)
  588-590: check_service_status dispatcher
  613    : bottom of check_service_status
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import responses as rsps_lib

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


OPERATIONAL_PAYLOAD = {
    "status": {"indicator": "none", "description": "All Systems Operational"},
    "incidents": [],
    "scheduled_maintenances": [],
    "components": [{"name": "API", "status": "operational"}],
}


@pytest.fixture(autouse=True)
def no_cache(tmp_path):
    with patch("cache_manager.get_cache_directory", return_value=tmp_path):
        yield


# ── lines 85-92: _error_response returns all expected keys ───────────────────
def test_error_response_has_all_keys():
    from service_checker import _error_response

    result = _error_response("svc", "timeout", "Timeout", "details", "err msg")
    assert result["status"] is None
    assert result["success"] is False
    assert result["incident_metadata"] == []
    assert result["maintenance_metadata"] == []
    assert result["component_metadata"] == []
    assert result["response_time"] == 0


# ── line 172: duplicate incident is skipped ──────────────────────────────────
def test_duplicate_incident_deduped():
    from service_checker import _build_incident_metadata_and_severity

    dup_incident = {
        "id": "inc1",
        "name": "API Down",
        "status": "investigating",
        "impact": "major",
        "shortlink": "https://stspg.io/inc1",
        "started_at": "2025-05-01T12:00:00Z",
        "components": [{"name": "API"}],
    }
    metadata, desc, severity = _build_incident_metadata_and_severity(
        [dup_incident, dup_incident],  # same incident twice
        {"url": "https://status.example.com/api/v2/summary.json"},
        "svc",
    )
    assert len(metadata) == 1


# ── line 227: completed maintenance is excluded ──────────────────────────────
def test_completed_maintenance_excluded():
    from service_checker import _get_active_maintenances

    data = {
        "scheduled_maintenances": [
            {"id": "m1", "status": "completed", "resolved_at": None},
            {"id": "m2", "status": "scheduled", "resolved_at": None},
            {"id": "m3", "status": "cancelled", "resolved_at": None},
        ]
    }
    result = _get_active_maintenances(data)
    assert len(result) == 1
    assert result[0]["id"] == "m2"


# ── lines 241-244: system metadata incident is skipped ───────────────────────
def test_system_metadata_incident_skipped():
    from service_checker import _build_incident_metadata_and_severity

    system_inc = {
        "id": "sys1",
        "name": "_system_metadata: internal test incident with a very long name here",
        "status": "investigating",
        "impact": "none",
        "shortlink": "",
        "started_at": "2025-05-01T12:00:00Z",
        "components": [],
    }
    metadata, desc, severity = _build_incident_metadata_and_severity(
        [system_inc],
        {"url": "https://status.example.com/api/v2/summary.json"},
        "svc",
    )
    assert metadata == []
    assert desc == ""
    assert severity is None


# ── lines 248, 274: shortlink fallback built from base_url ───────────────────
def test_shortlink_fallback_from_base_url():
    from service_checker import _build_incident_metadata_and_severity

    inc_no_shortlink = {
        "id": "inc99",
        "name": "Outage",
        "status": "investigating",
        "impact": "minor",
        "shortlink": "",  # no shortlink
        "started_at": "2025-05-01T12:00:00Z",
        "components": [],
    }
    metadata, desc, severity = _build_incident_metadata_and_severity(
        [inc_no_shortlink],
        {"url": "https://status.example.com/api/v2/summary.json"},
        "svc",
    )
    assert len(metadata) == 1
    assert "inc99" in metadata[0]["shortlink"]
    assert "status.example.com" in metadata[0]["shortlink"]


# ── line 297: incident with no affected components ───────────────────────────
def test_incident_no_affected_components_in_description():
    from service_checker import _build_incident_metadata_and_severity

    inc = {
        "id": "inc100",
        "name": "Database Slowness",
        "status": "identified",
        "impact": "minor",
        "shortlink": "https://stspg.io/inc100",
        "started_at": "2025-05-01T12:00:00Z",
        "components": [],  # no components
    }
    metadata, desc, severity = _build_incident_metadata_and_severity(
        [inc],
        {"url": "https://status.example.com/api/v2/summary.json"},
        "svc",
    )
    assert "affects:" not in desc
    assert "Database Slowness" in desc


# ── lines 323-368: _build_maintenance_metadata full path ─────────────────────
def test_build_maintenance_metadata_full():
    from service_checker import _build_maintenance_metadata

    maintenances = [
        {
            "id": "maint1",
            "name": "DB Upgrade",
            "status": "scheduled",
            "scheduled_for": "2025-06-01T02:00:00Z",
            "scheduled_until": "2025-06-01T04:00:00Z",
            "shortlink": "https://stspg.io/maint1",
            "components": [{"name": "Database"}, {"name": "API"}],
        },
        {
            "id": "maint1",  # duplicate — should be deduped
            "name": "DB Upgrade",
            "status": "scheduled",
            "scheduled_for": "2025-06-01T02:00:00Z",
            "scheduled_until": "2025-06-01T04:00:00Z",
            "shortlink": "https://stspg.io/maint1",
            "components": [{"name": "Database"}],
        },
        {
            "id": "maint2",
            "name": "Network Maintenance",
            "status": "in_progress",
            "scheduled_for": "",
            "scheduled_until": "",
            "shortlink": "",
            "created_at": "2025-06-02T00:00:00Z",
            "components": [],
        },
    ]
    result = _build_maintenance_metadata(maintenances, "svc")
    assert len(result) == 2
    assert result[0]["id"] == "maint1"
    assert "Database" in result[0]["affected_components"]
    assert result[1]["id"] == "maint2"


# ── lines 379-403: _preserve_labels_from_cache ───────────────────────────────
def test_preserve_labels_from_cache_overwrites_labels():
    from service_checker import _preserve_labels_from_cache

    result = {
        "incident_metadata": [
            {
                "id": "inc1",
                "name": "New name",
                "impact": "minor",
                "shortlink": "",
                "started_at": "2025-05-01T12:00:01Z",
                "affected_components": [],
            }
        ],
        "maintenance_metadata": [
            {
                "id": "maint1",
                "name": "New maint name",
                "scheduled_start": "2025-06-01T02:00:01Z",
                "scheduled_end": "2025-06-01T04:00:01Z",
                "shortlink": "",
                "affected_components": [],
            }
        ],
    }
    existing_cache = {
        "incident_metadata": [
            {
                "id": "inc1",
                "name": "Original name",
                "impact": "major",
                "shortlink": "https://stspg.io/inc1",
                "started_at": "2025-05-01T12:00:00Z",
                "affected_components": ["API"],
            }
        ],
        "maintenance_metadata": [
            {
                "id": "maint1",
                "name": "Original maint",
                "scheduled_start": "2025-06-01T02:00:00Z",
                "scheduled_end": "2025-06-01T04:00:00Z",
                "shortlink": "https://stspg.io/maint1",
                "affected_components": ["DB"],
            }
        ],
    }
    _preserve_labels_from_cache(result, existing_cache, "svc")

    # Labels should be preserved from cache
    assert result["incident_metadata"][0]["name"] == "Original name"
    assert result["incident_metadata"][0]["impact"] == "major"
    assert result["incident_metadata"][0]["shortlink"] == "https://stspg.io/inc1"
    assert result["maintenance_metadata"][0]["name"] == "Original maint"
    assert result["maintenance_metadata"][0]["shortlink"] == "https://stspg.io/maint1"


# ── lines 514, 523: cache update vs preserve log branches ────────────────────
@rsps_lib.activate
def test_cache_not_updated_when_unchanged(tmp_path):
    """When response matches cache, the 'preserving existing cache' branch is hit."""
    from service_checker import check_status_page_service

    rsps_lib.add(
        rsps_lib.GET,
        "https://status.example.com/api/v2/summary.json",
        json=OPERATIONAL_PAYLOAD,
        status=200,
    )

    existing_cache = {
        "status": 1,
        "raw_status": "none",
        "incident_metadata": [],
        "maintenance_metadata": [],
        "component_metadata": [{"name": "API", "status": "operational", "status_value": 1}],
    }

    with patch("service_checker.load_service_response", return_value=existing_cache), \
         patch("service_checker.save_service_response") as mock_save:
        result = check_status_page_service(
            "example",
            {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"},
        )

    # No meaningful change → save should NOT be called
    mock_save.assert_not_called()
    assert result["success"] is True


# ── lines 538-548: HTTP 4xx generic branch (e.g. 429) ────────────────────────
@rsps_lib.activate
def test_http_429_returns_4xx_error():
    from service_checker import check_status_page_service

    rsps_lib.add(
        rsps_lib.GET,
        "https://status.example.com/api/v2/summary.json",
        status=429,
    )
    result = check_status_page_service(
        "example",
        {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"},
    )
    assert result["success"] is False
    assert result["raw_status"] == "http_4xx_error"


# ── lines 588-590, 613: check_service_status dispatcher ─────────────────────
@rsps_lib.activate
def test_check_service_status_dispatches_correctly():
    """check_service_status routes to check_status_page_service and returns valid result."""
    from service_checker import check_service_status

    rsps_lib.add(
        rsps_lib.GET,
        "https://status.example.com/api/v2/summary.json",
        json=OPERATIONAL_PAYLOAD,
        status=200,
    )
    result = check_service_status(
        "example",
        {"url": "https://status.example.com/api/v2/summary.json", "name": "Example"},
    )
    assert result["success"] is True
    assert result["status"] == 1
