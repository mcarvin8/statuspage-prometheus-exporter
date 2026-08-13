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
    - Alternatively, RUN_MODE=once runs a single pass and exits, for callers
      that schedule this exporter themselves (e.g. a Cron job) instead of
      running it as a long-lived daemon

The exporter exposes metrics via Prometheus on port 9001 (configurable via METRICS_PORT)
for Grafana visualization and alerting on service disruptions. In RUN_MODE=once, metrics
are instead written to a Prometheus textfile (METRICS_TEXTFILE_PATH) for collection by
node_exporter's textfile collector or similar.

Service Configuration:
    - Service definitions are stored in services.json
    - Supports statuspage.io API format
    - Extensible to support additional service types

Environment Variables:
    - RUN_MODE: 'daemon' (default) runs continuously on a schedule; 'once' runs a
      single monitoring pass, writes a metrics textfile, and exits
    - METRICS_PORT: Prometheus metrics server port (default: 9001, daemon mode only)
    - METRICS_TEXTFILE_PATH: Output path for the Prometheus textfile
      (default: metrics/statuspage.prom, RUN_MODE=once only)
    - CHECK_INTERVAL_MINUTES: Interval in minutes between status checks (default: 20,
      daemon mode only)
    - DEBUG: Enable debug logging (set to 'true' to enable, default: false/INFO level)
    - CLEAR_CACHE: Clear all cache files on startup (set to 'true' to enable, default: false)
    - SLACK_WEBHOOK_URL: Optional Slack incoming webhook for incident opened/resolved posts

Functions:
    - schedule_tasks: Configures APScheduler jobs
    - run_once: Executes a single monitoring pass and writes a metrics textfile
    - main: Entry point that starts either the one-time run or the metrics server/scheduler
"""

import os
import logging
from prometheus_client import start_http_server, write_to_textfile, REGISTRY
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from .service_monitor import monitor_services
from .cache_manager import clear_cache
from .uptime_tracker import clear_uptime_history

# Configure logging based on DEBUG environment variable
debug_enabled = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes", "on")
log_level = logging.DEBUG if debug_enabled else logging.INFO
logging.basicConfig(
    level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
        CronTrigger(minute=f"*/{interval_minutes}"),
        id="monitor_services",
        replace_existing=True,
        max_instances=1,
    )

    logger.info("Scheduled tasks:")
    logger.info(
        f"  - Status page services monitoring: Every {interval_minutes} minutes"
    )


def _clear_cache_if_requested():
    """Clear all cache files if CLEAR_CACHE is set, per env var convention."""
    clear_cache_on_startup = os.getenv("CLEAR_CACHE", "false").lower() in (
        "true",
        "1",
        "yes",
        "on",
    )
    if clear_cache_on_startup:
        logger.info(
            "CLEAR_CACHE environment variable is set - clearing all cache files..."
        )
        clear_cache()
        clear_uptime_history()
    else:
        logger.debug("CLEAR_CACHE not set - preserving existing cache files")


def run_once():
    """
    Run a single monitoring pass and exit.

    Intended for callers (e.g. a Cron job) that want to run this exporter
    on their own schedule instead of running it as a long-lived daemon.
    Metrics are written to a Prometheus textfile for collection by
    node_exporter's textfile collector (or similar), since there is no
    running process for Prometheus to scrape once this exits.
    """
    logger.info("RUN_MODE=once - running a single monitoring pass...")

    _clear_cache_if_requested()

    # Pass is_initial_run=True since each one-time run starts from a clean gauge state
    monitor_services(is_initial_run=True)

    textfile_path = os.getenv("METRICS_TEXTFILE_PATH", "metrics/statuspage.prom")
    textfile_dir = os.path.dirname(textfile_path)
    if textfile_dir:
        os.makedirs(textfile_dir, exist_ok=True)
    write_to_textfile(textfile_path, REGISTRY)
    logger.info(f"Wrote metrics textfile to {textfile_path}")

    logger.info("One-time monitoring run complete, exiting.")


def run_daemon():
    """
    Run the exporter as a long-lived daemon: start the metrics HTTP server
    and schedule recurring monitoring runs.
    """
    # Start Prometheus metrics server
    metrics_port = int(os.getenv("METRICS_PORT", 9001))
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics server started on port {metrics_port}")

    # Get check interval from environment variable
    check_interval = int(os.getenv("CHECK_INTERVAL_MINUTES", 20))
    logger.info(f"Status check interval: {check_interval} minutes")

    # Initialize scheduler
    scheduler = BlockingScheduler()

    # Schedule tasks
    schedule_tasks(scheduler, check_interval)

    _clear_cache_if_requested()

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


def main():
    """
    Main entry point for the monitoring service.
    """
    logger.info("Starting Atlassian Status Page Prometheus Exporter...")

    # Log debug status
    debug_enabled = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes", "on")
    log_level_name = "DEBUG" if debug_enabled else "INFO"
    logger.info(f"Logging level: {log_level_name}")

    run_mode = os.getenv("RUN_MODE", "daemon").lower()
    if run_mode == "once":
        run_once()
    else:
        run_daemon()


if __name__ == "__main__":
    main()
