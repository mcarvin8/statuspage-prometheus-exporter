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

def test_save_fails_gracefully_on_bad_path(monkeypatch, cache_dir):
    """If writing fails, save returns False without raising."""
    from cache_manager import save_service_response
    monkeypatch.setattr("builtins.open", lambda *a, **kw: (_ for _ in ()).throw(OSError("permission denied")))
    result = save_service_response("svc", {"status": 1, "incident_metadata": []})
    assert result is False

def test_load_missing_response_data_key(cache_dir):
    """Cache entry missing 'response_data' key returns None."""
    import json
    from cache_manager import load_service_response
    bad = cache_dir / "bad_structure.json"
    bad.write_text(json.dumps({"service_key": "bad_structure", "timestamp": "2025-01-01"}))
    result = load_service_response("bad_structure")
    assert result is None

def test_clear_all_cache(cache_dir):
    from cache_manager import save_service_response, clear_cache, load_service_response
    save_service_response("svc_a", {"status": 1, "incident_metadata": []})
    save_service_response("svc_b", {"status": 1, "incident_metadata": []})
    clear_cache()  # no argument = clear all
    assert load_service_response("svc_a") is None
    assert load_service_response("svc_b") is None

def test_clear_nonexistent_service_is_noop(cache_dir):
    from cache_manager import clear_cache
    assert clear_cache("does_not_exist") is True

def test_load_generic_exception_returns_none(cache_dir, monkeypatch):
    """Non-JSON errors (e.g. permission error) return None without raising."""
    from cache_manager import save_service_response, load_service_response
    save_service_response("svc", {"status": 1, "incident_metadata": []})
    monkeypatch.setattr("builtins.open", lambda *a, **kw: (_ for _ in ()).throw(OSError("permission denied")))
    result = load_service_response("svc")
    assert result is None
