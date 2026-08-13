import json
import os
import pytest
from pathlib import Path

SERVICES_PATH = Path(__file__).parent.parent / "src" / "services.json"

# service_checker loads SERVICES.json at import time, defaulting to the current
# working directory (see src/statuspage_prometheus_exporter/service_checker.py).
# pytest's cwd is the repo root, not src/, so point it at the real config
# explicitly rather than relying on the default resolving there by accident.
os.environ.setdefault("SERVICES_JSON_PATH", str(SERVICES_PATH))


@pytest.fixture(scope="session")
def services():
    with open(SERVICES_PATH) as f:
        return json.load(f)

@pytest.fixture(scope="session")
def first_service(services):
    key, config = next(
        (k, v) for k, v in services.items()
        if not k.startswith("_")
    )
    return key, config


@pytest.fixture(autouse=True)
def _isolate_uptime_history(tmp_path, monkeypatch):
    """
    Uptime history I/O (uptime_tracker.py) isn't mocked out by the per-test
    gauge/cache patches most service_monitor tests already use, so without
    this it would write real *_uptime.jsonl files into the repo's cache/
    directory on every test run. Redirect it to a throwaway tmp_path instead.
    Tests that want to control this directory themselves (e.g. test_uptime_tracker.py)
    can still patch these same targets locally - the more specific patch wins.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "statuspage_prometheus_exporter.uptime_tracker.get_cache_directory",
        lambda: cache_dir,
    )
    monkeypatch.setattr(
        "statuspage_prometheus_exporter.uptime_tracker.ensure_cache_directory",
        lambda: cache_dir,
    )
