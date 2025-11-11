"""
Outreach Monitoring Service - Main Entry Point

This service monitors the operational status of Outreach by parsing their
HTML status page. Since Outreach doesn't expose a JSON API, this service
uses Selenium to render the JavaScript-rendered React/MUI page and extracts
component statuses and incident information.

Key Monitoring Areas:
    - Overall Outreach service status
    - Individual component statuses (Activity, Apps, Content, etc.)
    - Active incidents and outages
    - Scheduled maintenance events

Monitoring Schedule:
    - Status checks run every 20 minutes
    - Initial check executes on service startup
    - Uses APScheduler for reliable scheduling

The service exposes metrics via Prometheus on port 9001 (configurable via METRICS_PORT)
for Grafana visualization and alerting on Outreach service disruptions.

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
from outreach_monitor import monitor_outreach

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def schedule_tasks(scheduler):
    """
    Schedule monitoring tasks using APScheduler.
    
    Args:
        scheduler: APScheduler BlockingScheduler instance
    """
    # Schedule Outreach monitoring every 20 minutes
    scheduler.add_job(
        monitor_outreach,
        CronTrigger(minute='*/20'),
        id='monitor_outreach',
        replace_existing=True,
        max_instances=1
    )
    
    logger.info("Scheduled tasks:")
    logger.info("  - Outreach monitoring: Every 20 minutes")

def main():
    """
    Main entry point for the monitoring service.
    """
    logger.info("Starting Outreach Monitoring Service...")
    
    # Start Prometheus metrics server
    metrics_port = int(os.getenv('METRICS_PORT', 9001))
    start_http_server(metrics_port)
    logger.info(f"Prometheus metrics server started on port {metrics_port}")
    
    # Initialize scheduler
    scheduler = BlockingScheduler()
    
    # Schedule tasks
    schedule_tasks(scheduler)
    
    # Execute initial monitoring run
    logger.info("Executing initial monitoring run...")
    monitor_outreach()
    
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

