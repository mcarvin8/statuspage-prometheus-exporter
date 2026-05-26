"""
Integration tests that hit real StatusPage.io endpoints from services.json.
Run with: pytest tests/integration/ -v --timeout=30

These validate that the live API responses parse correctly through the full
check_status_page_service pipeline.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


def pytest_generate_tests(metafunc):
    """Parametrize over every non-comment service in services.json."""
    if "service_item" in metafunc.fixturenames:
        from conftest import SERVICES_PATH
        import json
        services = json.loads(SERVICES_PATH.read_text())
        params = [
            pytest.param((k, v), id=k)
            for k, v in services.items()
            if not k.startswith("_")
        ]
        metafunc.parametrize("service_item", params)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path):
    from unittest.mock import patch
    with patch("cache_manager.get_cache_directory", return_value=tmp_path):
        yield


def test_live_service_returns_valid_schema(service_item):
    """Every live service must return a parseable response with the expected keys."""
    service_key, service_config = service_item
    from service_checker import check_status_page_service

    result = check_status_page_service(service_key, service_config)

    # Schema assertions — always present regardless of success/failure
    assert "success" in result
    assert "status" in result
    assert "raw_status" in result
    assert "incident_metadata" in result
    assert "component_metadata" in result
    assert "maintenance_metadata" in result
    assert isinstance(result["incident_metadata"], list)
    assert isinstance(result["component_metadata"], list)


def test_live_service_successful_response(service_item):
    """Live services should actually respond (not be timing out or 404ing)."""
    service_key, service_config = service_item
    from service_checker import check_status_page_service

    result = check_status_page_service(service_key, service_config)

    assert result["success"] is True, (
        f"{service_config['name']} check failed: "
        f"{result.get('raw_status')} — {result.get('error')}"
    )
    assert result["status"] in (0, 1), \
        f"status must be 0 or 1, got {result['status']!r}"
    assert result["response_time"] > 0


def test_live_service_incident_metadata_shape(service_item):
    """If incidents are present, each must have required fields."""
    service_key, service_config = service_item
    from service_checker import check_status_page_service

    result = check_status_page_service(service_key, service_config)
    if not result["success"]:
        pytest.skip(f"{service_config['name']} unavailable")

    for inc in result["incident_metadata"]:
        assert "id" in inc
        assert "name" in inc
        assert "impact" in inc
        assert "affected_components" in inc
        assert isinstance(inc["affected_components"], list)


def test_live_service_component_metadata_shape(service_item):
    """Every component must have name, status, and a binary status_value."""
    service_key, service_config = service_item
    from service_checker import check_status_page_service

    result = check_status_page_service(service_key, service_config)
    if not result["success"]:
        pytest.skip(f"{service_config['name']} unavailable")

    for comp in result["component_metadata"]:
        assert "name" in comp
        assert "status" in comp
        assert comp.get("status_value") in (0, 1), \
            f"component {comp['name']!r} has invalid status_value"