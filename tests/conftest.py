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
