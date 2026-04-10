"""
APScheduler background jobs for auto-refreshing CMS rate data.
"""
from __future__ import annotations
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from config import settings

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _refresh_asp():
    logger.info("APScheduler: checking for new ASP quarterly release...")
    try:
        from cms_rates.asp_client import get_asp_dataframe
        df, label = get_asp_dataframe()
        if df is not None:
            logger.info(f"ASP data refreshed: {label}")
    except Exception as e:
        logger.error(f"ASP refresh failed: {e}")


def _refresh_pfs():
    current_year = datetime.now().year
    logger.info(f"APScheduler: refreshing PFS for year {current_year}...")
    try:
        from cms_rates.pfs_client import get_pfs_dataframe
        df = get_pfs_dataframe(year=current_year)
        if df is not None:
            logger.info(f"PFS data refreshed for {current_year}: {len(df)} codes")
    except Exception as e:
        logger.error(f"PFS refresh failed: {e}")


def start_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        return
    _scheduler = BackgroundScheduler(daemon=True)
    # Check for new ASP quarterly file weekly (Mondays at 3am)
    _scheduler.add_job(_refresh_asp, CronTrigger(day_of_week="mon", hour=3))
    # Refresh PFS annually in January
    _scheduler.add_job(_refresh_pfs, CronTrigger(month=1, day=15, hour=2))
    _scheduler.start()
    logger.info("CMS rate refresh scheduler started")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
