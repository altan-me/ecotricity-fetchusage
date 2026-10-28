"""
Scheduler module for running periodic data fetches.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from rich.console import Console
import random
import sys
import os
import threading
import time
from dotenv import load_dotenv

# Import from main script
from ecotricity import (
    get_credentials,
    create_session,
    init_consumption_page,
    init_data,
    fetch_data,
    parse_values,
    calculate_date_range,
    create_payload,
    format_portal_datetime,
    EcotricityError,
    EcotricityNoDataError,
    BATCH_DELAY,
)
from database import init_db, insert_consumption_data, record_fetch_attempt, get_missing_date_ranges, get_last_backfill_date, record_sync_start, record_sync_complete, update_sync_info

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConsumptionScheduler:
    """Manages scheduled fetching of consumption data."""
    
    def __init__(self, login: str = None, password: str = None, hour: int = 23, minute: int = 0):
        """
        Initialize the scheduler.
        
        Args:
            login: Ecotricity account login (uses env var if not provided)
            password: Ecotricity password (uses env var if not provided)
            hour: Hour to run daily fetch (24-hour format, default 23)
            minute: Minute to run daily fetch (default 0)
        """
        self.console = Console()
        self.login = login or os.environ.get("ECOTRICITY_LOGIN", "").strip()
        self.password = password or os.environ.get("ECOTRICITY_PASSWORD", "").strip()
        self.hour = hour
        self.minute = minute
        self.scheduler = BackgroundScheduler()
        self._session = None
        # One fetch at a time: two logins on one requests.Session is unsafe and
        # two writers on the SQLite file can collide.
        self._fetch_lock = threading.Lock()
        
        # Initialize database
        init_db()
    
    def _get_session(self) -> object:
        """Get or create a session."""
        if self._session is None:
            if not self.login or not self.password:
                raise ValueError("Login and password must be provided or set as environment variables")
            self._session = create_session(self.login, self.password)
        return self._session

    def _fetch_rows(self, date_range: str) -> list:
        """Perform one full fetch cycle and return the parsed rows."""
        session = self._get_session()

        init_consumption_page(session)
        init_data(session)

        date_from, date_to, date_type = calculate_date_range(date_range)
        payload = create_payload(date_from, date_to, date_type)

        data = fetch_data(session, payload)
        return parse_values(data)

    def is_fetching(self) -> bool:
        """True while a fetch or backfill is running."""
        return self._fetch_lock.locked()

    def fetch_and_store(self, date_range: str = "last 30 days") -> bool:
        """Fetch consumption data and store it in the database.

        Returns True only when rows were stored, so callers can tell a real
        sync from a failed one.

        Args:
            date_range: Date range to fetch (default: "last 30 days")
                       Examples: "last 7 days", "last 14 days", "last 30 days", "last 3 months"
        """
        if not self._fetch_lock.acquire(blocking=False):
            self.console.print("[yellow]⚠ Another fetch is running; skipping[/yellow]")
            return False
        try:
            return self._fetch_and_store(date_range)
        finally:
            self._fetch_lock.release()

    def _fetch_and_store(self, date_range: str) -> bool:
        try:
            record_sync_start()
            self.console.print(f"\n[cyan][{datetime.now().isoformat()}] Starting scheduled fetch ({date_range})...[/cyan]")

            rows = []
            # Retry once with a brand new session: a stale cookie or a transient
            # portal/WAF 503 is the most common cause of a scheduled failure.
            for attempt in (1, 2):
                try:
                    rows = self._fetch_rows(date_range)
                    break
                except EcotricityNoDataError as exc:
                    self.console.print(f"[yellow]⚠ {exc}[/yellow]")
                    rows = []
                    break
                except EcotricityError as exc:
                    self.console.print(
                        f"[yellow]⚠ Fetch attempt {attempt}/2 failed: {exc}[/yellow]"
                    )
                    # Drop the session so the retry performs a fresh login.
                    self._session = None
                    if attempt == 2:
                        raise
                    time.sleep(2 + random.random())

            if rows:
                insert_consumption_data(rows)
                self.console.print(f"[green]✓ Fetched and stored {len(rows)} records[/green]")
                # Record successful fetch
                for row in rows:
                    record_fetch_attempt(row["date"], success=True)
                record_sync_complete()
                return True

            # No data is not a successful sync: leave last_sync alone.
            self.console.print("[yellow]⚠ No data returned from API[/yellow]")
            update_sync_info(sync_status='idle')
            return False

        except Exception as e:
            self.console.print(f"[red]✗ Scheduled fetch failed: {e}[/red]")
            logger.exception("Scheduled fetch failed")
            # Try to reset session on error
            self._session = None
            # Record sync error but still mark it as no longer syncing
            update_sync_info(sync_status='idle')
            return False

    def backfill_consumption(self, start_date: str = None, end_date: str = None, max_attempts: int = 5) -> None:
        """
        Backfill missing consumption data.
        
        Args:
            start_date: Start date for backfill (YYYY-MM-DD). If None, defaults to 90 days ago.
            end_date: End date for backfill (YYYY-MM-DD). If None, defaults to yesterday.
            max_attempts: Maximum number of date ranges to attempt per backfill run.
        """
        if not self._fetch_lock.acquire(blocking=False):
            self.console.print("[yellow]⚠ Another fetch is running; skipping backfill[/yellow]")
            return
        try:
            self._backfill_consumption(start_date, end_date, max_attempts)
        finally:
            self._fetch_lock.release()

    def _backfill_consumption(self, start_date: str = None, end_date: str = None, max_attempts: int = 5) -> None:
        from datetime import datetime, timedelta
        
        try:
            self.console.print(f"\n[cyan][{datetime.now().isoformat()}] Starting backfill...[/cyan]")
            
            # Get missing date ranges
            missing_ranges = get_missing_date_ranges(start_date, end_date)
            
            if not missing_ranges:
                self.console.print("[green]✓ No missing data found[/green]")
                return
            
            self.console.print(f"[yellow]Found {len(missing_ranges)} date range(s) with missing data[/yellow]")
            
            session = self._get_session()
            init_consumption_page(session)
            init_data(session)
            
            # Process up to max_attempts ranges
            for i, (range_start, range_end) in enumerate(missing_ranges[:max_attempts]):
                # Space out requests so we don't trip the portal's rate limiting.
                if i > 0:
                    time.sleep(BATCH_DELAY + random.random())

                self.console.print(f"\n[cyan]Backfilling {i+1}/{min(len(missing_ranges), max_attempts)}: {range_start} to {range_end}[/cyan]")
                
                try:
                    # Create custom date range payload
                    start_dt = datetime.strptime(range_start, "%Y-%m-%d")
                    end_dt = datetime.strptime(range_end, "%Y-%m-%d")
                    
                    # Format dates for API (correct offset for the portal timezone)
                    date_from = format_portal_datetime(start_dt)
                    date_to = format_portal_datetime(end_dt)
                    
                    # Use MONTH dateType for backfill ranges (works for any date range)
                    payload = create_payload(date_from, date_to, "MONTH")
                    
                    # Fetch data
                    data = fetch_data(session, payload)
                    rows = parse_values(data)
                    
                    if rows:
                        insert_consumption_data(rows)
                        self.console.print(f"[green]✓ Backfilled {len(rows)} records for {range_start} to {range_end}[/green]")
                        for row in rows:
                            record_fetch_attempt(row["date"], success=True)
                    else:
                        self.console.print(f"[yellow]⚠ No data for {range_start} to {range_end} (may not be available yet)[/yellow]")
                        # Record failed attempt so we don't retry immediately
                        record_fetch_attempt(range_end, success=False, error_message="No data available")
                
                except Exception as e:
                    self.console.print(f"[red]✗ Backfill failed for {range_start} to {range_end}: {e}[/red]")
                    logger.exception(f"Backfill failed for range {range_start} to {range_end}")
                    record_fetch_attempt(range_end, success=False, error_message=str(e))
                    # Reset session so the next range re-authenticates
                    self._session = None
            
            if len(missing_ranges) > max_attempts:
                self.console.print(f"[yellow]⚠ {len(missing_ranges) - max_attempts} more date ranges need backfilling (will retry later)[/yellow]")
        
        except Exception as e:
            self.console.print(f"[red]✗ Backfill initialization failed: {e}[/red]")
            logger.exception("Backfill failed")
    
    def start(self) -> None:
        """Start the scheduler."""
        self.console.print(f"\n[cyan]Starting scheduler...[/cyan]")
        
        # First, try to backfill any missing data
        self.backfill_consumption()
        
        # Add job to run daily at specified time
        self.scheduler.add_job(
            self.fetch_and_store,
            CronTrigger(hour=self.hour, minute=self.minute),
            id='daily_fetch',
            name='Daily consumption fetch',
            replace_existing=True
        )
        
        # Add a weekly backfill job (every Monday at 2 AM)
        self.scheduler.add_job(
            lambda: self.backfill_consumption(),
            CronTrigger(day_of_week='mon', hour=2, minute=0),
            id='weekly_backfill',
            name='Weekly backfill of missing data',
            replace_existing=True
        )
        
        # Start the scheduler
        self.scheduler.start()
        self.console.print(f"[green]✓ Scheduler started[/green]")
        self.console.print(f"  - Daily fetch at {self.hour:02d}:{self.minute:02d}")
        self.console.print(f"  - Weekly backfill on Mondays at 02:00")
    
    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            self.console.print("[green]Scheduler stopped[/green]")
    
    def run(self) -> None:
        """Run the scheduler (blocking)."""
        try:
            self.start()
            # Keep the scheduler running
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Received interrupt signal[/yellow]")
            self.stop()
        except Exception as e:
            self.console.print(f"[red]Scheduler error: {e}[/red]")
            logger.exception("Scheduler error")
            self.stop()
            sys.exit(1)


def run_scheduler(hour: int = 23, minute: int = 0) -> None:
    """
    Run the scheduler (blocking operation).
    
    Args:
        hour: Hour to run daily fetch (24-hour format)
        minute: Minute to run daily fetch
    """
    load_dotenv()
    
    login = os.environ.get("ECOTRICITY_LOGIN", "").strip()
    password = os.environ.get("ECOTRICITY_PASSWORD", "").strip()
    
    if not login or not password:
        console = Console()
        console.print("[red]Error: ECOTRICITY_LOGIN and ECOTRICITY_PASSWORD environment variables must be set[/red]")
        sys.exit(1)
    
    scheduler = ConsumptionScheduler(login, password, hour, minute)
    scheduler.run()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run the consumption data scheduler")
    parser.add_argument("--hour", type=int, default=23, help="Hour to run fetch (0-23, default 23)")
    parser.add_argument("--minute", type=int, default=0, help="Minute to run fetch (0-59, default 0)")
    args = parser.parse_args()
    
    run_scheduler(args.hour, args.minute)
