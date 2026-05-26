import json
import pytest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


@pytest.fixture()
def cache_dir(tmp_path):
    with patch("cache_manager.get_cache_directory", return_value=tmp_path):
        yield tmp_path


def test_save_and_load_roundtrip(cache_dir):
    from cache_manager import save_service_response, load_service_response
    data = {"status": 1, "incident_metadata": [], "component_metadata": []}
    assert save_service_response("svc_a", data) is True
    loaded = load_service_response("svc_a")
    assert loaded["status"] == 1


def test_load_missing_returns_none(cache_dir):
    from cache_manager import load_service_response
    assert load_service_response("does_not_exist") is None


def test_corrupted_cache_returns_none_and_deletes_file(cache_dir):
    from cache_manager import load_service_response
    bad = cache_dir / "broken.json"
    bad.write_text("{ not valid json }")
    result = load_service_response("broken")
    assert result is None
    assert not bad.exists()


def test_clear_specific_service(cache_dir):
    from cache_manager import save_service_response, clear_cache, load_service_response
    save_service_response("svc_x", {"status": 1, "incident_metadata": []})
    save_service_response("svc_y", {"status": 1, "incident_metadata": []})
    clear_cache("svc_x")
    assert load_service_response("svc_x") is None
    assert load_service_response("svc_y") is not None


def test_atomic_write_no_tmp_file_left(cache_dir):
    from cache_manager import save_service_response
    save_service_response("svc_z", {"status": 1, "incident_metadata": []})
    tmp_files = list(cache_dir.glob("*.tmp"))
    assert tmp_files == []