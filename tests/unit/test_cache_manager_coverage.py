"""
Additional cache_manager tests to cover missing lines:
  47-49  : ensure_cache_directory debug log (mkdir path)
  157-158: unlink failure inside JSONDecodeError handler
  197-199: clear_cache except branch
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


# ── fixture: redirect cache to tmp_path ──────────────────────────────────────
import pytest


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("cache_manager.get_cache_directory", lambda: tmp_path)
    return tmp_path


# ── lines 47-49: ensure_cache_directory creates dir and logs ─────────────────
def test_ensure_cache_directory_creates_and_returns(tmp_path):
    """ensure_cache_directory should create a new subdir and return its path."""
    from cache_manager import ensure_cache_directory

    new_dir = tmp_path / "new_cache"
    with patch("cache_manager.get_cache_directory", return_value=new_dir):
        result = ensure_cache_directory()

    assert result == new_dir
    assert new_dir.exists()


# ── lines 157-158: unlink raises inside JSONDecodeError cleanup ───────────────
def test_corrupted_cache_unlink_failure_is_swallowed(cache_dir):
    """If unlink raises after a bad JSON read, the error is caught silently."""
    from cache_manager import load_service_response

    bad = cache_dir / "broken2.json"
    bad.write_text("{ bad json }")

    # Make unlink raise so we hit the inner except at 157-158
    original_unlink = Path.unlink

    def raise_on_unlink(self, missing_ok=False):
        if self.name == "broken2.json":
            raise OSError("locked")
        return original_unlink(self, missing_ok=missing_ok)

    with patch.object(Path, "unlink", raise_on_unlink):
        result = load_service_response("broken2")

    assert result is None


# ── lines 197-199: clear_cache except branch ─────────────────────────────────
def test_clear_cache_returns_false_on_exception(cache_dir):
    """clear_cache should return False (not raise) when deletion fails."""
    from cache_manager import save_service_response, clear_cache

    save_service_response("svc_err", {"status": 1, "incident_metadata": []})

    original_unlink = Path.unlink

    def raise_on_unlink(self, missing_ok=False):
        raise OSError("cannot delete")

    with patch.object(Path, "unlink", raise_on_unlink):
        result = clear_cache()  # clear all — hits the glob loop

    assert result is False
