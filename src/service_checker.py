"""
Service Status Checking Module

This module provides functions for checking the operational status of external
SaaS services. It supports multiple service types
and status page formats.

Supported Service Types:
    - status_page: StatusPage.io format (Atlassian)
    - Extensible architecture for additional types (Pingdom, custom APIs, etc.)

Configuration:
    - Service definitions loaded from services.json
    - Each service includes: name, type, URL, and other type-specific config

Functions:
    - check_status_page_service: Checks StatusPage.io API format
    - check_service_status: Main dispatcher that routes to appropriate checker

Incident Handling:
    - Filters incidents to only ACTIVE ones (excludes resolved/completed/postmortem)
    - Checks resolved_at timestamp to ensure incident is still ongoing
    - When multiple active incidents exist, their messages are merged with affected components
    - The highest severity from all active incidents is applied to the gauge
    - Severity priority: critical > major > minor > none
    - Incident details include affected component names

Component Monitoring:
    - Checks all components for operational status
    - Non-operational components trigger alerts even without active incidents
    - Component names are included in alert details for better context
    - Partial outages (some components down) are detected and reported
    - Component-level status is tracked in separate Prometheus gauge (statuspage_component_status)
    - Each component status is mapped: operational=1, degraded_performance/outage=0

Status Mapping:
    StatusPage.io indicators mapped to numeric values:
    - 'none': 1 (All systems operational)
    - 'minor': 0 (Minor service outage)
    - 'major': 0 (Major service outage)
    - 'critical': 0 (Critical service outage)

Return Format:
    All check functions return a dictionary with:
    - status: Numeric status value (1=operational, 0=degraded/incident, None=check failed)
    - response_time: API response time in seconds
    - raw_status: Raw status indicator from API
    - status_text: Human-readable status text
    - details: Detailed status description (merged incident names with metadata)
    - success: Boolean indicating if check succeeded
    - error: Error message (if success=False)
    - incident_metadata: List of dicts with incident details (ID, shortlink, duration, etc.)
    - maintenance_metadata: List of dicts with maintenance details (ID, schedule, shortlink, etc.)
    - component_metadata: List of dicts with component details (name, status, status_value)

Error Handling:
    - Network errors (timeouts, connection failures) with automatic retry (3 attempts)
    - Exponential backoff between retries (0.5s base factor)
    - Retries on: read timeouts, connection timeouts, and 5xx HTTP status codes
    - Request failures (network, timeout, HTTP errors) return status=None (no gauge update)
    - JSON parsing errors return status=None (likely temporary API issue)
    - Configuration errors return status=None (not a service incident)
    - All errors are logged with descriptive error messages
"""

import json
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import time
from typing import Dict, Any
from cache_manager import save_service_response, load_service_response

logger = logging.getLogger(__name__)

# Allow services.json to be specified via environment variable (useful for Docker)
config_path = os.getenv(
    "SERVICES_JSON_PATH", os.path.join(os.path.dirname(__file__), "services.json")
)

if not os.path.exists(config_path):
    # Try services.json.example as fallback
    example_path = os.path.join(os.path.dirname(__file__), "services.json.example")
    if os.path.exists(example_path):
        logger.warning(
            f"services.json not found at {config_path}, using example file. Please mount your own services.json file."
        )
        config_path = example_path
    else:
        raise FileNotFoundError(
            f"services.json not found at {config_path}. "
            "Please create a services.json file with your service configurations, "
            "or mount it as a volume when running in Docker."
        )

with open(config_path, "r") as f:
    SERVICES = json.load(f)


def create_retry_session(
    retries=3, backoff_factor=0.5, status_forcelist=(500, 502, 503, 504)
):
    """
    Create a requests session with retry logic.

    Args:
        retries: Number of retry attempts (default: 3)
        backoff_factor: Backoff factor for exponential delay between retries (default: 0.5)
        status_forcelist: HTTP status codes to retry on (default: 500, 502, 503, 504)

    Returns:
        requests.Session object configured with retry adapter
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        read=retries,  # Retry on read timeouts
        connect=retries,  # Retry on connection timeouts
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "HEAD", "OPTIONS"],  # Safe methods to retry
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _error_response(
    service_key: str,
    raw_status: str,
    status_text: str,
    details: str,
    error: str,
) -> Dict[str, Any]:
    """Build a failed-check response dict."""
    return {
        "status": None,
        "response_time": 0,
        "raw_status": raw_status,
        "status_text": status_text,
        "details": details,
        "success": False,
        "error": error,
        "incident_metadata": [],
        "maintenance_metadata": [],
        "component_metadata": [],
    }


def _extract_components(data: Dict[str, Any], service_key: str):
    """Extract component_metadata and non_operational_components from API data."""
    components = data.get("components", [])
    non_operational_components = [
        c for c in components if c.get("status", "").lower() != "operational"
    ]
    component_metadata = []
    for comp in components:
        component_name = comp.get("name", "Unknown")
        component_status = comp.get("status", "unknown").lower()
        if component_status == "operational":
            status_value = 1
        elif component_status in (
            "degraded_performance",
            "partial_outage",
            "major_outage",
        ):
            status_value = 0
        else:
            status_value = 0
        component_metadata.append(
            {
                "name": component_name,
                "status": component_status,
                "status_value": status_value,
            }
        )
        logger.debug(
            f"Status page service {service_key}: Component '{component_name}': {component_status} (value: {status_value})"
        )
    logger.debug(
        f"Status page service {service_key}: Extracted {len(component_metadata)} component(s)"
    )
    return component_metadata, non_operational_components


def _get_active_incidents(data: Dict[str, Any]) -> list:
    """Filter incidents to only ACTIVE (exclude resolved/completed/postmortem)."""
    terminal_statuses = {"resolved", "completed", "postmortem"}
    all_incidents = data.get("incidents", [])
    return [
        inc
        for inc in all_incidents
        if inc.get("status", "").lower() not in terminal_statuses
        and not inc.get("resolved_at")
    ]


def _get_active_maintenances(data: Dict[str, Any]) -> list:
    """Filter scheduled_maintenances to only active (exclude completed/cancelled)."""
    scheduled = data.get("scheduled_maintenances", [])
    return [
        m
        for m in scheduled
        if m.get("status", "").lower() not in {"completed", "cancelled"}
        and not m.get("resolved_at")
    ]


def _build_incident_metadata_and_severity(
    active_incidents: list,
    service_config: Dict[str, Any],
    service_key: str,
) -> tuple:
    """Build incident_metadata list, description string, and override indicator by severity."""
    incident_metadata = []
    seen_ids = set()
    unique_incidents = []
    for inc in active_incidents:
        inc_id = inc.get("id", "unknown")
        if inc_id not in seen_ids:
            seen_ids.add(inc_id)
            unique_incidents.append(inc)
        else:
            logger.debug(
                f"Status page service {service_key}: Skipping duplicate incident {inc_id}"
            )

    service_url = service_config.get("url", "")
    base_url = (
        service_url.replace("/api/v2/summary.json", "").rstrip("/")
        if service_url
        else ""
    )
    incident_details = []
    for inc in unique_incidents:
        name = inc.get("name", "Unnamed incident")
        if name.startswith("_system_metadata:"):
            logger.debug(
                f"Status page service {service_key}: Skipping system metadata test incident: {inc.get('id')} ({name[:50]}...)"
            )
            continue
        incident_id = inc.get("id", "unknown")
        shortlink = inc.get("shortlink", "")
        if not shortlink and base_url and incident_id != "unknown":
            shortlink = f"{base_url}/incidents/{incident_id}"
        affected_comps = [c.get("name", "") for c in inc.get("components", [])]
        detail = (
            f"{name} (affects: {', '.join(affected_comps)})" if affected_comps else name
        )
        if shortlink:
            detail = f"{detail} - {shortlink}"
        incident_details.append(detail)
        incident_metadata.append(
            {
                "id": incident_id,
                "name": name,
                "status": inc.get("status", "unknown"),
                "impact": inc.get("impact", "unknown"),
                "started_at": inc.get("started_at") or inc.get("created_at", ""),
                "updated_at": inc.get("updated_at", ""),
                "shortlink": shortlink,
                "affected_components": affected_comps,
            }
        )
    description = "; ".join(incident_details) if incident_details else ""
    severity_priority = {"critical": 3, "major": 2, "minor": 1, "none": 0}
    highest_severity = "none"
    highest_priority = 0
    for inc in active_incidents:
        if inc.get("name", "").startswith("_system_metadata:"):
            continue
        inc_impact = inc.get("impact", "none").lower()
        pri = severity_priority.get(inc_impact, 0)
        if pri > highest_priority:
            highest_priority = pri
            highest_severity = inc_impact
    return (
        incident_metadata,
        description,
        highest_severity if highest_severity != "none" else None,
    )


def _build_maintenance_metadata(active_maintenances: list, service_key: str) -> list:
    """Build maintenance_metadata list from active maintenances."""
    seen_ids = set()
    unique_maintenances = []
    for maint in active_maintenances:
        mid = maint.get("id", "unknown")
        if mid not in seen_ids:
            seen_ids.add(mid)
            unique_maintenances.append(maint)
        else:
            logger.debug(
                f"Status page service {service_key}: Skipping duplicate maintenance {mid}"
            )
    maintenance_metadata = []
    for maint in unique_maintenances:
        affected = [c.get("name", "") for c in maint.get("components", [])]
        maintenance_metadata.append(
            {
                "id": maint.get("id", "unknown"),
                "name": maint.get("name", "Unnamed maintenance"),
                "status": maint.get("status", "unknown"),
                "scheduled_start": maint.get("scheduled_for", "")
                or maint.get("created_at", ""),
                "scheduled_end": maint.get("scheduled_until", "")
                or maint.get("scheduled_for", ""),
                "shortlink": maint.get("shortlink", ""),
                "affected_components": affected,
            }
        )
    return maintenance_metadata


def _preserve_labels_from_cache(
    result: Dict[str, Any], existing_cache: Dict[str, Any], service_key: str
) -> None:
    """Preserve labels from existing cache in result to prevent duplicate alerts."""
    existing_incidents = {
        inc.get("id", "unknown"): inc
        for inc in existing_cache.get("incident_metadata", [])
    }
    existing_maintenance = {
        m.get("id", "unknown"): m
        for m in existing_cache.get("maintenance_metadata", [])
    }
    existing_components = {
        c.get("name", "Unknown"): c
        for c in existing_cache.get("component_metadata", [])
    }
    for incident in result.get("incident_metadata", []):
        inc_id = incident.get("id", "unknown")
        if inc_id in existing_incidents:
            existing_inc = existing_incidents[inc_id]
            incident["name"] = existing_inc.get("name", incident.get("name", "Unknown"))
            incident["affected_components"] = existing_inc.get(
                "affected_components", incident.get("affected_components", [])
            )
            incident["impact"] = existing_inc.get(
                "impact", incident.get("impact", "unknown")
            )
            incident["shortlink"] = existing_inc.get(
                "shortlink", incident.get("shortlink", "N/A")
            )
            incident["started_at"] = existing_inc.get(
                "started_at", incident.get("started_at", "")
            )
    for maintenance in result.get("maintenance_metadata", []):
        mid = maintenance.get("id", "unknown")
        if mid in existing_maintenance:
            existing_maint = existing_maintenance[mid]
            maintenance["name"] = existing_maint.get(
                "name", maintenance.get("name", "Unknown")
            )
            maintenance["affected_components"] = existing_maint.get(
                "affected_components", maintenance.get("affected_components", [])
            )
            maintenance["scheduled_start"] = existing_maint.get(
                "scheduled_start", maintenance.get("scheduled_start", "")
            )
            maintenance["scheduled_end"] = existing_maint.get(
                "scheduled_end", maintenance.get("scheduled_end", "")
            )
            maintenance["shortlink"] = existing_maint.get(
                "shortlink", maintenance.get("shortlink", "N/A")
            )


def _should_update_cache(
    result: Dict[str, Any], existing_cache: Dict[str, Any]
) -> bool:
    """Return True if cache should be updated (meaningful change detected)."""
    if not existing_cache:
        return True
    current_incident_ids = {
        inc.get("id", "unknown") for inc in result.get("incident_metadata", [])
    }
    cached_incident_ids = {
        inc.get("id", "unknown") for inc in existing_cache.get("incident_metadata", [])
    }
    current_maintenance_ids = {
        m.get("id", "unknown") for m in result.get("maintenance_metadata", [])
    }
    cached_maintenance_ids = {
        m.get("id", "unknown") for m in existing_cache.get("maintenance_metadata", [])
    }
    current_components = {
        (c.get("name", "Unknown"), c.get("status_value", 0))
        for c in result.get("component_metadata", [])
    }
    cached_components = {
        (c.get("name", "Unknown"), c.get("status_value", 0))
        for c in existing_cache.get("component_metadata", [])
    }
    status_changed = existing_cache.get("status") != result.get("status")
    incidents_changed = current_incident_ids != cached_incident_ids
    maintenance_changed = current_maintenance_ids != cached_maintenance_ids
    components_changed = current_components != cached_components
    return (
        status_changed or incidents_changed or maintenance_changed or components_changed
    )


def check_status_page_service(
    service_key: str, service_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Check status page service using statuspage.io API format.

    Args:
        service_key: Key identifier for the service
        service_config: Service configuration dictionary

    Returns:
        Dictionary with status information
    """
    try:
        logger.debug(
            f"Status page service {service_key}: Checking {service_config['url']}"
        )
        session = create_retry_session(retries=3, backoff_factor=0.5)
        start_time = time.time()
        response = session.get(
            service_config["url"],
            timeout=15,
            headers={"User-Agent": "AtlassianStatusPageExporter/1.0"},
        )
        response.raise_for_status()
        response_time = time.time() - start_time
        logger.debug(
            f"Status page service {service_key}: API responded in {response_time:.2f}s"
        )
        data = response.json()

        status = data.get("status", {})
        indicator = status.get("indicator", "unknown")
        description = status.get("description", "No description available")

        component_metadata, non_operational_components = _extract_components(
            data, service_key
        )
        active_incidents = _get_active_incidents(data)
        active_maintenances = _get_active_maintenances(data)
        logger.debug(
            f"Status page service {service_key}: Total incidents: {len(data.get('incidents', []))}, Active: {len(active_incidents)}, Non-operational components: {len(non_operational_components)}"
        )
        logger.debug(
            f"Status page service {service_key}: Total maintenances: {len(data.get('scheduled_maintenances', []))}, Active: {len(active_maintenances)}"
        )

        if active_incidents:
            (
                incident_metadata,
                inc_description,
                severity_override,
            ) = _build_incident_metadata_and_severity(
                active_incidents, service_config, service_key
            )
            if inc_description:
                description = inc_description
            if severity_override:
                indicator = severity_override
                logger.debug(
                    f"Status page service {service_key}: Overriding indicator to '{indicator}' based on highest incident severity"
                )
        else:
            incident_metadata = []

        if non_operational_components and not active_incidents:
            component_names = [
                c.get("name", "Unknown") for c in non_operational_components
            ]
            description = f"Non-operational components: {'; '.join(component_names)}"
            indicator = "minor"
            logger.warning(
                f"Status page service {service_key}: {len(non_operational_components)} components non-operational but no active incidents"
            )

        maintenance_metadata = (
            _build_maintenance_metadata(active_maintenances, service_key)
            if active_maintenances
            else []
        )

        status_mapping = {"none": 1, "minor": 0, "major": 0, "critical": 0}
        status_text_mapping = {
            "none": "Operational",
            "minor": "Minor Outage",
            "major": "Major Outage",
            "critical": "Critical Outage",
        }
        ind_lower = indicator.lower()
        status_value = status_mapping.get(ind_lower, 0)
        status_text = status_text_mapping.get(ind_lower, "Unknown")

        result = {
            "status": status_value,
            "response_time": response_time,
            "raw_status": indicator,
            "status_text": status_text,
            "details": description,
            "success": True,
            "incident_metadata": incident_metadata,
            "maintenance_metadata": maintenance_metadata,
            "component_metadata": component_metadata,
        }

        existing_cache = load_service_response(service_key)
        if existing_cache:
            _preserve_labels_from_cache(result, existing_cache, service_key)
        if _should_update_cache(result, existing_cache or {}):
            cache_result = result.copy()
            cache_result.pop("response_time", None)
            save_service_response(service_key, cache_result)
            logger.debug(
                f"Status page service {service_key}: Cache updated with new data"
            )
        else:
            logger.debug(
                f"Status page service {service_key}: Cache unchanged, preserving existing cache"
            )
        return result

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 0
        if status_code == 404:
            logger.error(
                f"Configuration error for {service_key}: 404 Not Found - Check URL in services.json"
            )
            raw_status = "http_404_not_found"
        elif status_code in (401, 403):
            logger.error(f"Authentication error for {service_key}: {status_code}")
            raw_status = "http_auth_error"
        elif 400 <= status_code < 500:
            logger.error(f"Client error for {service_key}: {status_code} - {e}")
            raw_status = "http_4xx_error"
        elif 500 <= status_code < 600:
            logger.warning(
                f"Server error for {service_key}: {status_code} - Status page API may be down"
            )
            raw_status = "http_5xx_error"
        else:
            logger.error(f"HTTP error for {service_key}: {e}")
            raw_status = "http_error"
        return _error_response(
            service_key,
            raw_status,
            "HTTP Error",
            f"HTTP {status_code}: {str(e)}",
            str(e),
        )
    except requests.exceptions.Timeout as e:
        logger.warning(f"Timeout error for {service_key}: {e}")
        return _error_response(
            service_key, "timeout", "Timeout", f"Request timeout: {str(e)}", str(e)
        )
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Connection error for {service_key}: {e}")
        return _error_response(
            service_key,
            "connection_error",
            "Connection Error",
            f"Connection failed: {str(e)}",
            str(e),
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for {service_key}: {e}")
        return _error_response(
            service_key,
            "request_error",
            "Request Error",
            f"Request failed: {str(e)}",
            str(e),
        )
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {service_key}: {e}")
        return _error_response(
            service_key,
            "json_error",
            "Parse Error",
            f"Invalid JSON response: {str(e)}",
            str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error for {service_key}: {e}")
        return _error_response(
            service_key,
            "unknown_error",
            "Unknown Error",
            f"Unexpected error: {str(e)}",
            str(e),
        )


def check_service_status(
    service_key: str, service_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Check the status of a single service.

    Args:
        service_key: Key identifier for the service
        service_config: Service configuration dictionary

    Returns:
        Dictionary with status information
    """
    # All services are status_page type
    return check_status_page_service(service_key, service_config)
