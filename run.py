#!/usr/bin/env python3
"""
Helper script to easily run the scheduler and web UI.
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console

console = Console()

# Load environment
load_dotenv()


def check_credentials() -> bool:
    """Check if credentials are available."""
    login = os.environ.get("ECOTRICITY_LOGIN", "").strip()
    password = os.environ.get("ECOTRICITY_PASSWORD", "").strip()
    
    if not login or not password:
        console.print(
            "[red]Error: Credentials not found![/red]\n"
            "Please set ECOTRICITY_LOGIN and ECOTRICITY_PASSWORD environment variables or create a .env file\n"
            "Example .env:\n"
            "  ECOTRICITY_LOGIN=your_account_number\n"
            "  ECOTRICITY_PASSWORD=your_password"
        )
        return False
    return True


def run_scheduler(hour: int = 23, minute: int = 0) -> None:
    """Run the background scheduler."""
    console.print("[cyan]Starting consumption data scheduler...[/cyan]")
    
    if not check_credentials():
        sys.exit(1)
    
    try:
        from scheduler import ConsumptionScheduler
        scheduler = ConsumptionScheduler(hour=hour, minute=minute)
        scheduler.run()
    except ImportError:
        console.print("[red]Error: scheduler module not found[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def run_web_ui(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    """Run the Flask web UI."""
    console.print(f"[cyan]Starting web UI at http://{host}:{port}[/cyan]")
    
    try:
        from app import app
        app.run(host=host, port=port, debug=debug)
    except ImportError:
        console.print("[red]Error: Flask app not found[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def run_combined(hour: int = 23, minute: int = 0, host: str = "127.0.0.1", port: int = 5000) -> None:
    """Run both scheduler and web UI in separate processes."""
    import subprocess
    from threading import Thread
    from time import sleep
    
    console.print("[cyan]Starting Ecotricity system (scheduler + web UI)...[/cyan]\n")
    
    if not check_credentials():
        sys.exit(1)
    
    # Start scheduler in a separate process
    console.print(f"[green]✓ Scheduler will fetch data daily at {hour:02d}:{minute:02d}[/green]")
    console.print(f"[green]✓ Scheduler will backfill missing data every Monday[/green]")
    console.print(f"[green]✓ Web UI will be available at http://{host}:{port}[/green]\n")
    
    def run_scheduler_thread():
        try:
            run_scheduler(hour, minute)
        except KeyboardInterrupt:
            pass
    
    def run_web_thread():
        try:
            run_web_ui(host, port, debug=False)
        except KeyboardInterrupt:
            pass
    
    # Start both in threads
    scheduler_thread = Thread(target=run_scheduler_thread, daemon=True)
    web_thread = Thread(target=run_web_thread, daemon=True)
    
    scheduler_thread.start()
    sleep(1)  # Let scheduler start first
    web_thread.start()
    
    try:
        # Keep main thread alive
        while True:
            sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        sys.exit(0)


def backfill_once(start_date: str = None, end_date: str = None, max_attempts: int = 5) -> None:
    """Run backfill to fill in missing data."""
    console.print("[cyan]Starting data backfill...[/cyan]")
    
    if not check_credentials():
        sys.exit(1)
    
    try:
        from scheduler import ConsumptionScheduler
        
        scheduler = ConsumptionScheduler()
        scheduler.backfill_consumption(start_date, end_date, max_attempts)
        console.print("[green]✓ Backfill complete[/green]")
    
    except ImportError:
        console.print("[red]Error: scheduler module not found[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def fetch_once(date_preset: str = "last 7 days") -> None:
    """Run a one-time fetch and store data."""
    console.print(f"[cyan]Fetching consumption data ({date_preset})...[/cyan]")
    
    if not check_credentials():
        sys.exit(1)
    
    try:
        from ecotricity import (
            get_credentials,
            create_session,
            init_consumption_page,
            init_data,
            fetch_data,
            parse_values,
            calculate_date_range,
            create_payload,
        )
        from database import init_db, insert_consumption_data
        
        init_db()
        
        login, password = get_credentials()
        session = create_session(login, password)
        
        init_consumption_page(session)
        init_data(session)
        
        date_from, date_to = calculate_date_range(date_preset)
        payload = create_payload(date_from, date_to)
        
        data = fetch_data(session, payload)
        rows = parse_values(data)
        
        if rows:
            insert_consumption_data(rows)
            console.print(f"[green]✓ Stored {len(rows)} records in database[/green]")
        else:
            console.print("[yellow]⚠ No data returned from API[/yellow]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Ecotricity consumption tracker - scheduler and web UI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py fetch                    # Fetch data once
  python run.py fetch --dates 'last month'  # Fetch specific date range
  python run.py scheduler                # Run scheduler only
  python run.py scheduler --hour 22      # Schedule at 22:00
  python run.py web                      # Run web UI only
  python run.py web --port 8000          # Run web UI on different port
  python run.py all                      # Run both scheduler and web UI
  python run.py backfill                 # Backfill missing data (last 90 days)
  python run.py backfill --start 2026-01-01 --end 2026-03-31  # Backfill specific range
  python run.py backfill --max 10        # Backfill up to 10 date ranges
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Fetch command
    fetch_parser = subparsers.add_parser('fetch', help='Fetch consumption data once')
    fetch_parser.add_argument('--dates', default='last 7 days', 
                            help='Date range preset (default: last 7 days)')
    
    # Scheduler command
    scheduler_parser = subparsers.add_parser('scheduler', help='Run the background scheduler')
    scheduler_parser.add_argument('--hour', type=int, default=23, 
                                 help='Hour to run daily fetch (0-23, default 23)')
    scheduler_parser.add_argument('--minute', type=int, default=0, 
                                 help='Minute to run daily fetch (0-59, default 0)')
    
    # Web command
    web_parser = subparsers.add_parser('web', help='Run the web UI')
    web_parser.add_argument('--host', default='127.0.0.1', 
                           help='Host to bind to (default: 127.0.0.1)')
    web_parser.add_argument('--port', type=int, default=5000, 
                           help='Port to bind to (default: 5000)')
    web_parser.add_argument('--debug', action='store_true', 
                           help='Run in debug mode')
    
    # Combined command
    combined_parser = subparsers.add_parser('all', help='Run scheduler and web UI together')
    combined_parser.add_argument('--hour', type=int, default=23, 
                                help='Hour to run daily fetch (0-23, default 23)')
    combined_parser.add_argument('--minute', type=int, default=0, 
                                help='Minute to run daily fetch (0-59, default 0)')
    combined_parser.add_argument('--host', default='127.0.0.1', 
                                help='Web UI host (default: 127.0.0.1)')
    combined_parser.add_argument('--port', type=int, default=5000, 
                                help='Web UI port (default: 5000)')
    
    # Backfill command
    backfill_parser = subparsers.add_parser('backfill', help='Backfill missing consumption data')
    backfill_parser.add_argument('--start', type=str, default=None,
                                help='Start date (YYYY-MM-DD). Default: 90 days ago')
    backfill_parser.add_argument('--end', type=str, default=None,
                                help='End date (YYYY-MM-DD). Default: today')
    backfill_parser.add_argument('--max', type=int, default=5,
                                help='Max date ranges to process (default: 5)')
    
    args = parser.parse_args()
    
    if args.command == 'fetch':
        fetch_once(args.dates)
    elif args.command == 'scheduler':
        run_scheduler(args.hour, args.minute)
    elif args.command == 'web':
        run_web_ui(args.host, args.port, args.debug)
    elif args.command == 'all':
        run_combined(args.hour, args.minute, args.host, args.port)
    elif args.command == 'backfill':
        backfill_once(args.start, args.end, args.max)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
