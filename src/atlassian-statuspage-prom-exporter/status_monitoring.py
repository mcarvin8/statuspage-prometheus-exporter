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
    - Status checks run every 20 minutes
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def schedule_tasks(scheduler):
    """
    Schedule monitoring tasks using APScheduler.
    
    Args:
        scheduler: APScheduler BlockingScheduler instance
    """
    # Schedule status page monitoring every 20 minutes
    scheduler.add_job(
        monitor_services,
        CronTrigger(minute='*/20'),
        id='monitor_services',
        replace_existing=True,
        max_instances=1
    )
    
    logger.info("Scheduled tasks:")
    logger.info("  - Status page services monitoring: Every 20 minutes")

def main():
    """
    Main entry point for the monitoring service.
    """
    logger.info("Starting Atlassian Status Page Prometheus Exporter...")
    
    # Start Prometheus metrics server
    metrics_port = int(os.getenv('METRICS_PORT', 9001))
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics server started on port {metrics_port}")
    
    # Initialize scheduler
    scheduler = BlockingScheduler()
    
    # Schedule tasks
    schedule_tasks(scheduler)
    
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
