"""
Service Monitoring Orchestration Module

This module orchestrates the monitoring of all configured services
by iterating through the service definitions, checking their status, and updating
Prometheus metrics with the results.

Functions:
    - monitor_services: Main orchestration function that coordinates
      status checks for all services and updates Prometheus gauges

Process Flow:
    1. Load previous cache for all services (sequential, fast file I/O)
    2. Check all services in parallel using ThreadPoolExecutor (up to 10 concurrent requests)
    3. For failed requests, attempt to load cached response data as fallback
    4. Clear existing Prometheus gauge labels:
       - On initial run: Clear ALL gauges to remove stale data from previous pod instances
       - On subsequent runs: Only clear response_time gauge (others updated selectively)
    5. Update all gauges with collected results
    6. For incident, maintenance, status, and component gauges: Always update to keep metrics fresh
    7. Response time gauge always updates (dynamic metric for trending)
    8. Failed checks are logged (check logs for failure details)

    Incident Gauge Strategy:
    - Incident gauge is cleared on initial run only (to remove stale data from previous pods)
    - On subsequent runs, incident gauge is NOT cleared globally
    - For each service, always update incident gauge to keep metrics fresh in Prometheus
    - Clear resolved incidents by setting them to 0 (using cached metadata to match labels)
    - Always update active incidents (even if unchanged) to ensure Prometheus knows they're still active
    - This keeps metrics fresh in Grafana dashboards and prevents stale data, while using cached labels for existing incidents to prevent duplicate alerts

    Maintenance Gauge Strategy:
    - Maintenance gauge is cleared on initial run only (to remove stale data from previous pods)
    - On subsequent runs, maintenance gauge is NOT cleared globally
    - For each service, always update maintenance gauge to keep metrics fresh in Prometheus
    - Clear resolved maintenance by setting them to 0 (using cached metadata to match labels)
    - Always update active maintenance (even if unchanged) to ensure Prometheus knows they're still active
    - This keeps metrics fresh in Grafana dashboards and prevents stale data, while using cached labels for existing maintenance to prevent duplicate alerts

    Status Gauge Strategy:
    - Status gauge is cleared on initial run only (to remove stale data from previous pods)
    - On subsequent runs, status gauge is NOT cleared globally (unlike response_time gauge)
    - For each service, always update status gauge to keep metrics fresh in Prometheus
    - Always update status gauge (even if unchanged) to ensure Prometheus knows the metric is still active
    - This keeps metrics fresh in Grafana dashboards and prevents stale data

    Component Status Gauge Strategy:
    - Component status gauge is cleared on initial run only (to remove stale data from previous pods)
    - On subsequent runs, component status gauge is NOT cleared globally (unlike response_time gauge)
    - For each service, always update component gauge to keep metrics fresh in Prometheus
    - Clear removed components by setting them to 0
    - Always update component status (even if unchanged) to ensure Prometheus knows the metric is still active
    - This keeps metrics fresh in Grafana dashboards and prevents stale data

    Response Time Gauge Strategy:
    - Response time gauge is cleared and updated every run
    - Response times are dynamic and should be tracked continuously for performance trending
    - This metric is not used for alerts, so frequent updates are acceptable

    Probe Check Gauge Strategy:
    - Probe check gauge is cleared and updated every run (like response_time)
    - Indicates whether the current probe query succeeded (1=success, 0=failed)
    - Updated even when using cached data (shows 0 if current probe failed, even with cache)
    - This is a dynamic metric that should reflect the current probe status

    Application Timestamp Gauge Strategy:
    - Application timestamp gauge is cleared on initial run only
    - On subsequent runs, NOT cleared globally (like statuspage_status_gauge)
    - Only updated when application status changes
    - Tracks when the overall application status was last updated
    - Stored in Unix epoch milliseconds for better Grafana compatibility

    Component Timestamp Gauge Strategy:
    - Component timestamp gauge is cleared on initial run only
    - On subsequent runs, NOT cleared globally (like statuspage_component_status)
    - Only updated when components change (added, removed, or status changed)
    - Set to 0 when components are removed
    - Tracks when each component was last updated
    - Stored in Unix epoch milliseconds for better Grafana compatibility

    Cache Fallback Strategy:
    - When an API request fails, the service attempts to load the last successful
      response from cache
    - If cached data exists, it's used to update metrics, preventing alerts from
      clearing and re-firing due to transient network issues
    - This ensures continuity of monitoring even when individual requests fail

Metrics Updated:
    - statuspage_status_gauge: Service health status (1=operational, 0=degraded/incident)
        Simplified to just service_name and status value - incident details in statuspage_incident_info
        Only updated when status changes per service to prevent unnecessary updates
    - statuspage_response_time_gauge: API response time in seconds
        Always updated every run (dynamic metric for performance trending)
    - statuspage_incident_info: Active incident metadata (ID, name, impact, shortlink, etc.)
        Only updated when incidents change per service to prevent unnecessary updates
    - statuspage_maintenance_info: Active maintenance metadata (ID, name, schedule, shortlink, etc.)
        Only updated when maintenance changes per service to prevent unnecessary updates
    - statuspage_component_status: Individual component status (1=operational, 0=degraded_performance/outage)
        Only updated when components change per service to prevent unnecessary updates
    - statuspage_component_timestamp: Last update timestamp of component in Unix epoch milliseconds
        Only updated when components change per service to prevent unnecessary updates
        Set to 0 when components are removed
        Milliseconds format provides better Grafana compatibility
    - statuspage_probe_check: Whether the current probe query was successful (1=success, 0=failed)
        Always updated and cleared every run (dynamic metric like response_time)
        Shows current probe status even when using cached data for other metrics
    - statuspage_application_timestamp: Timestamp of last update of overall application status in Unix epoch milliseconds
        Only updated when application status changes per service to prevent unnecessary updates
        Milliseconds format provides better Grafana compatibility

The orchestration ensures consistent metric labels and handles both successful
and failed status checks gracefully. Failed checks fall back to cached data when
available, preventing alert churn from transient failures.
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from service_checker import SERVICES, check_service_status
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
from cache_manager import load_service_response

logger = logging.getLogger(__name__)


def check_service_with_fallback(service_key, service_config):
    """
    Check a single service status with cache fallback on failure.

    Args:
        service_key: Service identifier key
        service_config: Service configuration dictionary

    Returns:
        Dictionary with service_key, service_config, and result
    """
    logger.info(f"Checking {service_config['name']} ({service_key})...")

    result = check_service_status(service_key, service_config)
    original_failure = None

    # If request failed, try to load cached response as fallback
    if not result["success"]:
        # Store original failure info for tracking
        original_failure = {
            "raw_status": result.get("raw_status", "unknown"),
            "error": result.get("error", "Unknown error"),
        }

        logger.warning(
            f"{service_config['name']}: Check failed ({original_failure['raw_status']}), attempting to load cached response..."
        )
        cached_result = load_service_response(service_key)

        if cached_result:
            logger.info(
                f"{service_config['name']}: Using cached response data (from previous successful check)"
            )
            # Mark that this is cached data (for logging/metrics)
            result = cached_result.copy()
            result["from_cache"] = True
            result["original_failure"] = (
                original_failure  # Preserve failure info for logging
            )
            # response_time is not cached (not used for alerts), set to 0 for cached data
            if "response_time" not in result:
                result["response_time"] = 0.0
        else:
            logger.warning(
                f"{service_config['name']}: No cached data available, will skip gauge update - {original_failure['error']}"
            )
            result["from_cache"] = False
            result["original_failure"] = original_failure
    else:
        # Successful request - cache will be saved by service_checker
        result["from_cache"] = False
        result["original_failure"] = None

    # Log result immediately
    cache_note = " (from cache)" if result.get("from_cache", False) else ""
    if result["success"] or result.get("from_cache", False):
        response_time = result.get("response_time", 0.0)
        logger.info(
            f"{service_config['name']}: {result['raw_status']} "
            f"(response time: {response_time:.2f}s){cache_note}"
        )
    else:
        logger.warning(
            f"{service_config['name']}: Check failed ({result.get('raw_status', 'unknown')}), no cached data available - {result.get('error', 'Unknown error')}"
        )

    return {
        "service_key": service_key,
        "service_config": service_config,
        "result": result,
    }


def normalize_timestamp(timestamp_str):
    """
    Normalize ISO 8601 timestamp to seconds precision (remove milliseconds).
    This prevents duplicate gauge entries due to timestamp precision differences.

    Args:
        timestamp_str: ISO 8601 timestamp string (e.g., '2025-11-04T13:25:38.181Z' or '2025-11-04T13:25:38.000Z')

    Returns:
        Normalized timestamp string with seconds precision (e.g., '2025-11-04T13:25:38Z')
    """
    if not timestamp_str or timestamp_str == "N/A" or timestamp_str == "unknown":
        return timestamp_str

    # Remove milliseconds by replacing .XXX pattern before Z or timezone offset
    # Matches patterns like: .181Z, .000Z, .123+00:00, etc.
    normalized = re.sub(r"\.\d{3}(?=[Z\+\-])", "", timestamp_str)
    return normalized


def _load_previous_caches():
    """Load cache for each service (before running checks)."""
    return {key: load_service_response(key) for key in SERVICES.keys()}


def _run_checks_parallel():
    """Run all service checks in parallel; return list of result items."""
    max_workers = min(10, len(SERVICES))
    logger.info(
        f"Checking {len(SERVICES)} services with up to {max_workers} parallel requests..."
    )
    start_time = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_service = {
            executor.submit(check_service_with_fallback, sk, sc): (sk, sc)
            for sk, sc in SERVICES.items()
        }
        for future in as_completed(future_to_service):
            service_key, service_config = future_to_service[future]
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(
                    f"Unexpected error checking {service_config['name']} ({service_key}): {e}",
                    exc_info=True,
                )
                results.append(
                    {
                        "service_key": service_key,
                        "service_config": service_config,
                        "result": {
                            "success": False,
                            "status": None,
                            "raw_status": "unexpected_error",
                            "status_text": "Unexpected Error",
                            "details": f"Unexpected error: {str(e)}",
                            "response_time": 0.0,
                            "error": str(e),
                            "from_cache": False,
                            "original_failure": None,
                            "incident_metadata": [],
                            "maintenance_metadata": [],
                            "component_metadata": [],
                        },
                    }
                )
    elapsed = time.time() - start_time
    logger.info(
        f"Completed all service checks in {elapsed:.2f}s ({len(SERVICES)} services)"
    )
    return results


def _clear_gauges(is_initial_run):
    """Clear gauge labels (all on initial run, only dynamic gauges otherwise)."""
    if is_initial_run:
        logger.info(
            "Initial run detected - clearing all gauges to remove stale data from previous pod instances"
        )
        statuspage_status_gauge.clear()
        statuspage_response_time_gauge.clear()
        statuspage_incident_info.clear()
        statuspage_maintenance_info.clear()
        statuspage_component_status.clear()
        statuspage_component_timestamp.clear()
        statuspage_probe_check.clear()
        statuspage_application_timestamp.clear()
    else:
        logger.debug("Clearing existing gauge labels before updating with new data...")
        statuspage_response_time_gauge.clear()
        statuspage_component_timestamp.clear()
        statuspage_probe_check.clear()
        statuspage_application_timestamp.clear()


def _update_probe_and_response_time(service_name, result, from_cache):
    """Update probe_check and response_time gauges."""
    probe_success = 1 if (result.get("success", False) or from_cache) else 0
    statuspage_probe_check.labels(service_name=service_name).set(probe_success)
    statuspage_response_time_gauge.labels(service_name=service_name).set(
        result["response_time"]
    )


def _update_status_and_app_timestamp(service_name, status_value, current_timestamp_ms):
    """Update main status gauge and application timestamp."""
    statuspage_status_gauge.labels(service_name=service_name).set(status_value)
    statuspage_application_timestamp.labels(service_name=service_name).set(
        current_timestamp_ms
    )


def _clear_resolved_incidents(service_name, resolved_ids, cached_by_id):
    """Set incident_info gauge to 0 for resolved incident IDs using cached labels."""
    for resolved_id in resolved_ids:
        resolved_inc = cached_by_id.get(resolved_id, {})
        resolved_name = resolved_inc.get("name", "Unknown")[:100]
        resolved_affected = ", ".join(resolved_inc.get("affected_components", []))[:150]
        resolved_impact = resolved_inc.get("impact", "unknown")
        resolved_shortlink = resolved_inc.get("shortlink", "N/A")
        resolved_started = normalize_timestamp(
            resolved_inc.get("started_at", "unknown")
        )
        statuspage_incident_info.labels(
            service_name=service_name,
            incident_id=resolved_id,
            incident_name=resolved_name,
            impact=resolved_impact,
            shortlink=resolved_shortlink,
            started_at=resolved_started,
            affected_components=resolved_affected,
        ).set(0)


def _update_active_incidents(
    service_name, incident_metadata, has_cache, cached_by_id, cached_ids
):
    """Update incident_info gauge for active incidents (and set 'none' when empty)."""
    if incident_metadata:
        for incident in incident_metadata:
            incident_id = incident.get("id", "unknown")
            if has_cache and incident_id in cached_ids:
                cached_inc = cached_by_id.get(incident_id, {})
                incident_name = cached_inc.get("name", "Unknown")[:100]
                affected = ", ".join(cached_inc.get("affected_components", []))[:150]
                impact = cached_inc.get("impact", "unknown")
                shortlink = cached_inc.get("shortlink", "N/A")
                started_at = normalize_timestamp(
                    cached_inc.get("started_at", "unknown")
                )
            else:
                incident_name = incident.get("name", "Unknown")[:100]
                affected = ", ".join(incident.get("affected_components", []))[:150]
                impact = incident.get("impact", "unknown")
                shortlink = incident.get("shortlink", "N/A")
                started_at = normalize_timestamp(incident.get("started_at", "unknown"))
            statuspage_incident_info.labels(
                service_name=service_name,
                incident_id=incident_id,
                incident_name=incident_name,
                impact=impact,
                shortlink=shortlink,
                started_at=started_at,
                affected_components=affected,
            ).set(1)
    else:
        statuspage_incident_info.labels(
            service_name=service_name,
            incident_id="none",
            incident_name="No Active Incidents",
            impact="none",
            shortlink="N/A",
            started_at="N/A",
            affected_components="N/A",
        ).set(0)


def _clear_resolved_maintenance(service_name, resolved_ids, cached_by_id):
    """Set maintenance_info gauge to 0 for resolved maintenance IDs using cached labels."""
    for resolved_id in resolved_ids:
        resolved_maint = cached_by_id.get(resolved_id, {})
        resolved_name = resolved_maint.get("name", "Unknown")[:100]
        resolved_affected = ", ".join(resolved_maint.get("affected_components", []))[
            :150
        ]
        resolved_scheduled_start = normalize_timestamp(
            resolved_maint.get("scheduled_start", "unknown")
        )
        resolved_scheduled_end = normalize_timestamp(
            resolved_maint.get("scheduled_end", "unknown")
        )
        resolved_shortlink = resolved_maint.get("shortlink", "N/A")
        statuspage_maintenance_info.labels(
            service_name=service_name,
            maintenance_id=resolved_id,
            maintenance_name=resolved_name,
            scheduled_start=resolved_scheduled_start,
            scheduled_end=resolved_scheduled_end,
            shortlink=resolved_shortlink,
            affected_components=resolved_affected,
        ).set(0)


def _update_active_maintenance(service_name, maintenance_metadata):
    """Update maintenance_info gauge for active maintenance (and set 'none' when empty)."""
    if maintenance_metadata:
        for maintenance in maintenance_metadata:
            maintenance_name = maintenance.get("name", "Unknown")[:100]
            affected = ", ".join(maintenance.get("affected_components", []))[:150]
            maintenance_id = maintenance.get("id", "unknown")
            scheduled_start = normalize_timestamp(
                maintenance.get("scheduled_start", "unknown")
            )
            scheduled_end = normalize_timestamp(
                maintenance.get("scheduled_end", "unknown")
            )
            shortlink = maintenance.get("shortlink", "N/A")
            statuspage_maintenance_info.labels(
                service_name=service_name,
                maintenance_id=maintenance_id,
                maintenance_name=maintenance_name,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                shortlink=shortlink,
                affected_components=affected,
            ).set(1)
    else:
        statuspage_maintenance_info.labels(
            service_name=service_name,
            maintenance_id="none",
            maintenance_name="No Active Maintenance",
            scheduled_start="N/A",
            scheduled_end="N/A",
            shortlink="N/A",
            affected_components="N/A",
        ).set(0)


def _clear_removed_components(service_name, removed_names):
    """Set component_status to 0 for removed component names."""
    for removed_name in removed_names:
        statuspage_component_status.labels(
            service_name=service_name, component_name=removed_name
        ).set(0)


def _update_component_gauges(service_name, component_metadata):
    """Update component_status and component_timestamp for each component."""
    for component in component_metadata:
        component_name = component.get("name", "Unknown")
        component_status_value = component.get("status_value", 0)
        statuspage_component_status.labels(
            service_name=service_name, component_name=component_name
        ).set(component_status_value)
        component_timestamp_ms = int(time.time() * 1000)
        statuspage_component_timestamp.labels(
            service_name=service_name, component_name=component_name
        ).set(component_timestamp_ms)


def _update_gauges_for_service(item, previous_caches):
    """Update all gauges for one service result."""
    service_key = item["service_key"]
    service_config = item["service_config"]
    result = item["result"]
    service_name = service_config["name"]
    status_value = result.get("status")
    from_cache = result.get("from_cache", False)

    _update_probe_and_response_time(service_name, result, from_cache)

    if status_value is None:
        return

    current_timestamp_ms = int(time.time() * 1000)
    cached_data = previous_caches.get(service_key)
    has_cache = cached_data is not None

    _update_status_and_app_timestamp(service_name, status_value, current_timestamp_ms)

    incident_metadata = result.get("incident_metadata", [])
    cached_incidents = (cached_data or {}).get("incident_metadata", [])
    current_by_id = {inc.get("id", "unknown"): inc for inc in incident_metadata}
    cached_by_id = {inc.get("id", "unknown"): inc for inc in cached_incidents}
    current_ids = {inc.get("id", "unknown") for inc in incident_metadata}
    cached_ids = {inc.get("id", "unknown") for inc in cached_incidents}

    if has_cache and (cached_ids - current_ids):
        resolved_ids = cached_ids - current_ids
        logger.info(
            f"{service_name}: Clearing {len(resolved_ids)} resolved incident(s): {resolved_ids}"
        )
        _clear_resolved_incidents(service_name, resolved_ids, cached_by_id)
    _update_active_incidents(
        service_name, incident_metadata, has_cache, cached_by_id, cached_ids
    )

    maintenance_metadata = result.get("maintenance_metadata", [])
    cached_maintenance = (cached_data or {}).get("maintenance_metadata", [])
    current_maint_by_id = {m.get("id", "unknown"): m for m in maintenance_metadata}
    cached_maint_by_id = {m.get("id", "unknown"): m for m in cached_maintenance}
    current_maint_ids = {m.get("id", "unknown") for m in maintenance_metadata}
    cached_maint_ids = {m.get("id", "unknown") for m in cached_maintenance}

    if has_cache and (cached_maint_ids - current_maint_ids):
        resolved_maint_ids = cached_maint_ids - current_maint_ids
        logger.info(
            f"{service_name}: Clearing {len(resolved_maint_ids)} resolved maintenance event(s): {resolved_maint_ids}"
        )
        _clear_resolved_maintenance(
            service_name, resolved_maint_ids, cached_maint_by_id
        )
    _update_active_maintenance(service_name, maintenance_metadata)

    component_metadata = result.get("component_metadata", [])
    cached_components = (cached_data or {}).get("component_metadata", [])
    current_names = {comp.get("name", "Unknown") for comp in component_metadata}
    cached_names = {comp.get("name", "Unknown") for comp in cached_components}
    removed_names = cached_names - current_names
    if has_cache and removed_names:
        logger.info(
            f"{service_name}: Clearing {len(removed_names)} removed component(s): {removed_names}"
        )
        _clear_removed_components(service_name, removed_names)
    _update_component_gauges(service_name, component_metadata)


def monitor_services(is_initial_run=False):
    """
    Monitor all configured services and update Prometheus metrics.

    Args:
        is_initial_run: If True, clears all gauges to remove stale data from previous pod instances.
                       If False, only clears response_time gauge (others updated selectively).

    Process Flow:
    1. Collect status check results for all services first
    2. Clear existing Prometheus gauge labels to remove stale metrics
    3. Immediately update all gauges with collected results

    This minimizes the window where Prometheus might scrape empty gauges
    by collecting all data before clearing and updating.
    """
    logger.info("Starting status page services monitoring...")
    previous_caches = _load_previous_caches()
    results = _run_checks_parallel()
    _clear_gauges(is_initial_run)
    for item in results:
        _update_gauges_for_service(item, previous_caches)
    logger.info("Status page monitoring completed")
