# tests/unit/test_gauges.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

def test_gauges_import():
    from gauges import (
        statuspage_status_gauge,
        statuspage_response_time_gauge,
        statuspage_incident_info,
        statuspage_maintenance_info,
        statuspage_component_status,
        statuspage_component_timestamp,
        statuspage_probe_check,
        statuspage_application_timestamp,
    )
    assert statuspage_status_gauge._labelnames == ("service_name",)
    assert "incident_id" in statuspage_incident_info._labelnames
    assert "maintenance_id" in statuspage_maintenance_info._labelnames
    assert "component_name" in statuspage_component_status._labelnames
