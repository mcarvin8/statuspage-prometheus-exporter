import json
import pytest
from pathlib import Path

SERVICES_PATH = Path(__file__).parent.parent / "src" / "services.json"

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
