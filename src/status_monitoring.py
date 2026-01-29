"""
Atlassian Status Page Prometheus Exporter - Main Entry Point

This exporter monitors the operational status of services using Atlassian Status Page.io
status pages. It periodically checks status page APIs to track service health, outages,
and maintenance windows.

Key Features:
    - Monitors any service using Atlassian Status Page.io format
    - Tracks service health, incidents, and maintenance windows
    - Records response times and latency metrics
    - Exposes Prometheus metrics for integration with monitoring stacks

Monitoring Schedule:
    - Status checks run on a configurable interval (default: 20 minutes)
    - Initial check executes on service startup
    - Uses APScheduler for reliable scheduling

The exporter exposes metrics via Prometheus on port 9001 (configurable via METRICS_PORT)
for Grafana visualization and alerting on service disruptions.

Service Configuration:
    - Service definitions are stored in services.json
    - Supports statuspage.io API format
    - Extensible to support additional service types

Environment Variables:
    - METRICS_PORT: Prometheus metrics server port (default: 9001)
    - CHECK_INTERVAL_MINUTES: Interval in minutes between status checks (default: 20)
    - DEBUG: Enable debug logging (set to 'true' to enable, default: false/INFO level)
    - CLEAR_CACHE: Clear all cache files on startup (set to 'true' to enable, default: false)

Functions:
    - schedule_tasks: Configures APScheduler jobs
    - main: Entry point that starts metrics server and scheduler
"""
import os
import logging
from prometheus_client import start_http_server
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from service_monitor import monitor_services
from cache_manager import clear_cache

# Configure logging based on DEBUG environment variable
debug_enabled = os.getenv('DEBUG', 'false').lower() in ('true', '1', 'yes', 'on')
log_level = logging.DEBUG if debug_enabled else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def schedule_tasks(scheduler, interval_minutes=20):
    """
    Schedule monitoring tasks using APScheduler.
    
    Args:
        scheduler: APScheduler BlockingScheduler instance
        interval_minutes: Interval in minutes between status checks (default: 20)
    """
    # Schedule status page monitoring at the specified interval
    scheduler.add_job(
        monitor_services,
        CronTrigger(minute=f'*/{interval_minutes}'),
        id='monitor_services',
        replace_existing=True,
        max_instances=1
    )
    
    logger.info("Scheduled tasks:")
    logger.info(f"  - Status page services monitoring: Every {interval_minutes} minutes")

def main():
    """
    Main entry point for the monitoring service.
    """
    logger.info("Starting Atlassian Status Page Prometheus Exporter...")
    
    # Log debug status
    debug_enabled = os.getenv('DEBUG', 'false').lower() in ('true', '1', 'yes', 'on')
    log_level_name = "DEBUG" if debug_enabled else "INFO"
    logger.info(f"Logging level: {log_level_name}")
    
    # Start Prometheus metrics server
    metrics_port = int(os.getenv('METRICS_PORT', 9001))
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics server started on port {metrics_port}")
    
    # Get check interval from environment variable
    check_interval = int(os.getenv('CHECK_INTERVAL_MINUTES', 20))
    logger.info(f"Status check interval: {check_interval} minutes")
    
    # Initialize scheduler
    scheduler = BlockingScheduler()
    
    # Schedule tasks
    schedule_tasks(scheduler, check_interval)
    
    # Check if cache should be cleared on startup
    clear_cache_on_startup = os.getenv('CLEAR_CACHE', 'false').lower() in ('true', '1', 'yes', 'on')
    if clear_cache_on_startup:
        logger.info("CLEAR_CACHE environment variable is set - clearing all cache files...")
        clear_cache()
    else:
        logger.debug("CLEAR_CACHE not set - preserving existing cache files")
    
    # Execute initial monitoring run
    # Pass is_initial_run=True to clear all gauges and remove stale data from previous pod instances
    logger.info("Executing initial monitoring run...")
    monitor_services(is_initial_run=True)
    
    # Start scheduler
    logger.info("Starting scheduler...")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
        scheduler.shutdown()
        logger.info("Scheduler stopped")

if __name__ == "__main__":
    main()
