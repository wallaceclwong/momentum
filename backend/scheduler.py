"""
APScheduler configuration for S&P 500 Momentum Screener.
"""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.engine.screener import run_momentum_screener, get_screener_summary
from backend.engine.portfolio import allocate_portfolio, get_portfolio_summary
from backend.db.crud import (
    save_screener_run,
    save_portfolio_snapshot,
    save_performance_log,
    get_latest_portfolio
)
from backend.db.models import Base
from backend.db.session import engine, SessionLocal

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def setup_scheduler():
    """Configure and start the scheduler."""
    # Create database tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    # Monthly screener job (last Friday of each month at 22:00 UTC)
    scheduler.add_job(
        func=run_monthly_screener,
        trigger=CronTrigger(
            day="last",
            day_of_week="fri",  # Last Friday
            hour="22",
            minute="0",
            timezone="UTC"
        ),
        id="monthly_screener",
        name="Monthly Momentum Screener",
        replace_existing=True,
    )
    
    # Daily performance snapshot (every day at 22:00 UTC)
    scheduler.add_job(
        func=run_daily_snapshot,
        trigger=CronTrigger(
            hour="22",
            minute="0",
            timezone="UTC"
        ),
        id="daily_snapshot",
        name="Daily Performance Snapshot",
        replace_existing=True,
    )
    
    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started with 2 jobs configured")


async def run_monthly_screener():
    """Run the monthly momentum screener and save results."""
    logger.info("Running monthly momentum screener...")
    
    try:
        # Run screener
        screener_results = run_momentum_screener()
        screener_summary = get_screener_summary(screener_results)
        
        # Allocate portfolio
        portfolio = allocate_portfolio(screener_results)
        portfolio_summary = get_portfolio_summary(portfolio)
        
        # Save to database
        db = SessionLocal()
        try:
            # Save screener run
            save_screener_run(db, screener_results, screener_summary)
            
            # Save portfolio snapshot
            save_portfolio_snapshot(db, portfolio, portfolio_summary)
            
            # Save performance log
            save_performance_log(db, portfolio_summary)
            
            db.commit()
            logger.info(f"Monthly screener completed: {portfolio_summary.get('total_positions', 0)} positions")
        except Exception as e:
            db.rollback()
            logger.error(f"Database error during monthly screener: {e}")
            raise
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Monthly screener failed: {e}", exc_info=True)


async def run_daily_snapshot():
    """Run daily performance snapshot."""
    logger.info("Running daily performance snapshot...")
    
    try:
        # Get latest portfolio from database
        db = SessionLocal()
        try:
            latest_portfolio = get_latest_portfolio(db)
            if not latest_portfolio:
                logger.warning("No existing portfolio found, skipping daily snapshot")
                return
            
            # Calculate current performance
            portfolio_summary = get_portfolio_summary(latest_portfolio)
            
            # Save performance log
            save_performance_log(db, portfolio_summary)
            
            db.commit()
            logger.info("Daily snapshot completed")
        except Exception as e:
            db.rollback()
            logger.error(f"Database error during daily snapshot: {e}")
            raise
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Daily snapshot failed: {e}", exc_info=True)


def get_scheduler_status():
    """Get current scheduler status and job info."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
    
    return {
        "running": scheduler.running,
        "jobs": jobs
    }
