#!/usr/bin/env python3
"""
Quick start guide - run this script to set up and start the system.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

console = Console()

# Load environment
load_dotenv()

def main():
    console.print(Panel.fit(
        "[bold cyan]⚡ Ecotricity Consumption Tracker - Quick Start[/bold cyan]",
        border_style="cyan"
    ))
    
    # Check credentials
    console.print("\n[yellow]Step 1: Checking credentials...[/yellow]")
    login = os.environ.get("ECOTRICITY_LOGIN", "").strip()
    password = os.environ.get("ECOTRICITY_PASSWORD", "").strip()
    
    if not login or not password:
        console.print("[red]✗ Credentials not found[/red]")
        console.print("\nPlease set your credentials:")
        console.print("  Option A: Create a .env file:")
        console.print("    ECOTRICITY_LOGIN=your_account_number")
        console.print("    ECOTRICITY_PASSWORD=your_password")
        console.print("\n  Option B: Set environment variables:")
        console.print("    export ECOTRICITY_LOGIN='your_account_number'")
        console.print("    export ECOTRICITY_PASSWORD='your_password'")
        sys.exit(1)
    
    console.print(f"[green]✓ Credentials found (login: {login[:3]}...)[/green]")
    
    # Check database
    console.print("\n[yellow]Step 2: Checking database...[/yellow]")
    from database import init_db, get_data_range
    init_db()
    start, end = get_data_range()
    
    if start:
        console.print(f"[green]✓ Database ready (data from {start} to {end})[/green]")
    else:
        console.print("[yellow]⚠ Database is empty - fetching initial data...[/yellow]")
        
        from ecotricity import (
            create_session, init_consumption_page, init_data,
            fetch_data, parse_values, calculate_date_range, create_payload
        )
        from database import insert_consumption_data
        
        try:
            session = create_session(login, password)
            init_consumption_page(session)
            init_data(session)
            
            date_from, date_to = calculate_date_range("last 7 days")
            payload = create_payload(date_from, date_to)
            
            data = fetch_data(session, payload)
            rows = parse_values(data)
            
            if rows:
                insert_consumption_data(rows)
                console.print(f"[green]✓ Fetched and stored {len(rows)} records[/green]")
            else:
                console.print("[yellow]⚠ No data returned from API[/yellow]")
        except Exception as e:
            console.print(f"[red]✗ Error: {e}[/red]")
            sys.exit(1)
    
    # Choose what to run
    console.print("\n[yellow]Step 3: Choose what to run:[/yellow]")
    console.print("\n[cyan]Options:[/cyan]")
    console.print("  1. [bold]Dashboard only[/bold] (view data) - python run.py web")
    console.print("  2. [bold]Scheduler only[/bold] (auto-fetch) - python run.py scheduler")
    console.print("  3. [bold]Everything[/bold] (dashboard + scheduler) - python run.py all")
    
    try:
        choice = input("\nEnter your choice (1-3) or press Ctrl+C to exit: ").strip()
        
        if choice == "1":
            console.print("\n[green]Starting dashboard at http://127.0.0.1:5000[/green]")
            os.system("python run.py web")
        elif choice == "2":
            console.print("\n[green]Starting scheduler (will fetch daily at 23:00)[/green]")
            os.system("python run.py scheduler")
        elif choice == "3":
            console.print("\n[green]Starting scheduler + dashboard[/green]")
            console.print("Dashboard will be available at http://127.0.0.1:5000")
            os.system("python run.py all")
        else:
            console.print("[red]Invalid choice[/red]")
            sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
