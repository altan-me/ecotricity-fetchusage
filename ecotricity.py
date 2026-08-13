#!/usr/bin/env python3
"""
Ecotricity power consumption fetcher with automatic login.

Usage:
  python ecotricity.py

  Credentials can be provided via:
  1. .env file (copy .env.example to .env and fill in your credentials)
  2. Environment variables:
     ECOTRICITY_LOGIN=usrname ECOTRICITY_PASSWORD=yourpassword python ecotricity.py
  3. Interactive prompts (if credentials not found in .env or env vars)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box

# ── Config ───────────────────────────────────────────────────────────────────

BASE_URL = "https://portal.ecotricity.co.nz/powercommerce/eco/fo/portal"
LOGIN_URL = f"{BASE_URL}/loginProcess"
DATA_URL = f"{BASE_URL}/analysis/valueRequest"

INDICATOR_ID = "470f2d40-42ca-11f1-9ba3-020017005c7e"
TIMEZONE_OFFSET = "+02:00"  # Adjust for your timezone (e.g., +00:00 for UTC, +13:00 for NZDT)

# ⚠️  IMPORTANT: If you get "No metering data available" (503), the date range likely has no data.
# Check your account in the Ecotricity portal to see what date ranges contain data.

# ── Date Range ────────────────────────────────────────────────────────────────


def calculate_date_range(preset: str) -> tuple[str, str]:
    """Calculate date range from a preset string.
    
    Presets:
      - 'last 2 days': Last 2 calendar days
      - 'last 7 days': Last 7 calendar days
      - 'last 30 days': Last 30 calendar days
      - 'last month': All of last calendar month
      - 'last 3 months': Last 3 calendar months
    """
    console = Console()
    now = datetime.now()
    
    if preset == "last 2 days":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=2)
    elif preset == "last 7 days":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=7)
    elif preset == "last 30 days":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=30)
    elif preset == "last month":
        # First day of current month
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # First day of last month
        start = first_of_this_month - timedelta(days=1)
        start = start.replace(day=1)
        # Last day of last month (day before first of this month)
        end = first_of_this_month
    elif preset == "last 3 months":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Go back 3 months
        month = now.month - 3
        year = now.year
        while month < 1:
            month += 12
            year -= 1
        start = now.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        console.print(f"[red]Unknown preset: {preset}[/red]", style="red")
        console.print("Valid presets: 'last 2 days', 'last 7 days', 'last 30 days', 'last month', 'last 3 months'")
        sys.exit(1)
    
    # Format as ISO with timezone
    date_from = start.strftime("%Y-%m-%dT00:00:00.000") + TIMEZONE_OFFSET
    date_to = end.strftime("%Y-%m-%dT00:00:00.000") + TIMEZONE_OFFSET
    
    console.print(f"\n  📅 Date Range: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
    
    return date_from, date_to


def create_payload(date_from: str, date_to: str) -> dict:
    """Create the API payload with the given date range."""
    return {
        "dateType": "MONTH",
        "indicatorValueRequests": [
            {
                "valueRange": {date_from: date_to},
                "indicatorID": INDICATOR_ID,
                "indicatorType": "INDICATOR_GROUP",
                "index": 0,
                "featureValueRequests": [
                    {
                        "featureID": "POWER_ACTIVE_PURCHASE_CONSUMPTION",
                        "granularityType": "DAY",
                        "filterByIndicatorAttributesMap": {},
                        "aggregationType": "SUM",
                    }
                ],
            }
        ],
        "userTimeZone": "Pacific/Auckland",
    }


# ── Auth ──────────────────────────────────────────────────────────────────────


def get_credentials() -> tuple[str, str]:
    login = os.environ.get("ECOTRICITY_LOGIN", "").strip()
    password = os.environ.get("ECOTRICITY_PASSWORD", "").strip()

    if not login:
        login = input("Ecotricity login (account number): ").strip()
    if not password:
        import getpass
        password = getpass.getpass("Password: ")

    if not login or not password:
        print("Error: login and password are required.", file=sys.stderr)
        sys.exit(1)

    return login, password


def create_session(login: str, password: str) -> requests.Session:
    console = Console()
    session = requests.Session()

    # Set browser-like headers for the session
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            "accept-language": "en-US,en;q=0.9",
        }
    )

    console.print(f"\n  [DEBUG] Attempting login...")
    console.print(f"  [DEBUG] URL: {LOGIN_URL}")
    console.print(f"  [DEBUG] Login username: {login}")

    # POST login — session will automatically store any cookies from the response
    resp = session.post(
        LOGIN_URL,
        data={"login": login, "password": password},
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "referer": f"{BASE_URL}/start",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
        },
        allow_redirects=True,
        timeout=30,
    )

    # Log response details for debugging
    console.print(f"\n  [DEBUG] Response Status Code: {resp.status_code}")
    console.print(f"  [DEBUG] Response URL (after redirects): {resp.url}")
    console.print(f"  [DEBUG] Response Headers:", style="dim")
    for key, value in dict(resp.headers).items():
        console.print(f"    {key}: {value}", style="dim")
    console.print(f"  [DEBUG] Response Content Length: {len(resp.content)} bytes", style="dim")
    console.print(f"  [DEBUG] Session Cookies: {dict(session.cookies)}", style="dim")
    console.print(f"  [DEBUG] Response Set-Cookie Headers: {resp.headers.get('set-cookie', 'None')}", style="dim")
    
    # Check we didn't land back on the login page (failed auth)
    if "loginProcess" in resp.url or "start" in resp.url:
        console.print(
            "\n  ❌ Login failed — ended up back at login page. Check your credentials.",
            style="red",
        )
        sys.exit(1)

    if resp.status_code not in (200, 302):
        console.print(f"\n  ❌ Unexpected login response: {resp.status_code}", style="red")
        sys.exit(1)

    if not session.cookies:
        console.print("\n  ⚠️  WARNING: No cookies set after login! This may indicate failed authentication.", style="yellow")
    else:
        console.print(f"\n  ✓ Logged in successfully. Session cookies: {list(session.cookies.keys())}")
    
    return session


# ── Initialize ────────────────────────────────────────────────────────────────


def init_consumption_page(session: requests.Session) -> None:
    """Visit the consumption details page to establish page state/CSRF tokens."""
    console = Console()
    consumption_url = f"{BASE_URL}/consumptionDetails"
    console.print(f"\n  [DEBUG] Initializing consumption page: {consumption_url}")
    
    resp = session.get(
        consumption_url,
        headers={
            "referer": f"{BASE_URL}/home",
        },
        timeout=30,
    )
    
    console.print(f"  [DEBUG] Consumption page status: {resp.status_code}", style="dim")
    console.print(f"  [DEBUG] Consumption page content length: {len(resp.content)} bytes", style="dim")
    
    if resp.status_code >= 400:
        console.print(f"  ⚠️  Warning: Got status {resp.status_code} fetching consumption page", style="yellow")
    else:
        console.print(f"  ✓ Consumption page loaded.")


def init_data(session: requests.Session) -> None:
    """Initialize data by calling the initData endpoint."""
    console = Console()
    init_data_url = f"{BASE_URL}/analysis/initData"
    init_payload = {
        "fetchCurrentIndicator": True,
        "fetchInstallation": False,
        "fetchLastImport": True,
        "fetchEnergyPerformanceIndicator": True,
        "fetchImsysFeatures": False,
    }
    
    console.print(f"\n  [DEBUG] Initializing data: {init_data_url}")
    console.print(f"  [DEBUG] Init data payload: {json.dumps(init_payload, indent=2)}", style="dim")
    
    resp = session.post(
        init_data_url,
        json=init_payload,
        headers={
            "accept": "application/json, text/javascript, */*; q=0.01",
            "content-type": "application/json",
            "origin": "https://portal.ecotricity.co.nz",
            "x-requested-with": "XMLHttpRequest",
            "referer": f"{BASE_URL}/consumptionDetails",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        },
        timeout=30,
    )
    
    console.print(f"  [DEBUG] Init data response status: {resp.status_code}", style="dim")
    
    if resp.status_code >= 400:
        console.print(f"  ⚠️  Warning: Got status {resp.status_code} on init data", style="yellow")
    else:
        console.print(f"  ✓ Data initialized.")


# ── Fetch ─────────────────────────────────────────────────────────────────────


def fetch_data(session: requests.Session, payload: dict) -> dict:
    console = Console()
    
    console.print(f"\n  [DEBUG] Fetching data with cookies: {dict(session.cookies)}")
    console.print(f"  [DEBUG] Data fetch URL: {DATA_URL}")
    
    request_headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/json",
        "origin": "https://portal.ecotricity.co.nz",
        "x-requested-with": "XMLHttpRequest",
        "referer": f"{BASE_URL}/consumptionDetails",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    
    console.print("\n  [DEBUG] Request Headers:")
    for key, value in request_headers.items():
        console.print(f"    {key}: {value}", style="dim")
    
    console.print("\n  [DEBUG] Request Payload:")
    console.print(json.dumps(payload, indent=2), style="dim")
    
    resp = session.post(
        DATA_URL,
        json=payload,
        headers=request_headers,
        timeout=30,
    )

    console.print(f"\n  [DEBUG] Data fetch response status: {resp.status_code}")
    console.print(f"  [DEBUG] Data fetch response headers:")
    for key, value in dict(resp.headers).items():
        console.print(f"    {key}: {value}", style="dim")
    
    console.print(f"\n  [DEBUG] Data fetch response body:", style="dim")
    try:
        response_json = resp.json()
        console.print(json.dumps(response_json, indent=2), style="dim")
    except:
        console.print(f"{resp.text[:800]}", style="dim")

    if resp.status_code in (401, 403):
        console.print(f"\n  ❌ Auth error ({resp.status_code}) on data fetch. Session may have expired or cookies not being sent.", style="red")
        sys.exit(1)
    
    if resp.status_code == 503:
        console.print(f"\n  ❌ Service Unavailable (503). The API returned:", style="red")
        try:
            console.print(json.dumps(resp.json(), indent=2), style="red")
        except:
            console.print(resp.text, style="red")
        console.print("     This could be: temporary maintenance, no data for this period, or account issue.", style="yellow")
        sys.exit(1)
    
    if resp.status_code >= 400:
        console.print(f"\n  ❌ HTTP Error ({resp.status_code}). Response:", style="red")
        try:
            console.print(json.dumps(resp.json(), indent=2), style="red")
        except:
            console.print(resp.text[:500], style="red")
        sys.exit(1)

    resp.raise_for_status()
    return resp.json()


# ── Parse ─────────────────────────────────────────────────────────────────────


def parse_values(data: dict) -> list[dict]:
    rows = []
    for indicator in data.get("indicatorValueResponses", []):
        for feature in indicator.get("featureValueResponses", []):
            for entry in feature.get("values", []):
                value = entry["value"]
                period = entry["measuringPeriod"]
                start_str = next(iter(period.keys()))
                try:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(start_str)
                    date_label = start_dt.strftime("%Y-%m-%d")
                    weekday = start_dt.strftime("%a")
                except ValueError:
                    date_label = start_str
                    weekday = "?"
                rows.append(
                    {"date": date_label, "weekday": weekday, "value": value}
                )
    return rows


# ── Display ───────────────────────────────────────────────────────────────────

BAR_MAX_WIDTH = 25


def make_bar(value: float, max_value: float) -> str:
    if max_value == 0:
        return ""
    return "█" * round((value / max_value) * BAR_MAX_WIDTH)


def display_table(rows: list[dict]) -> None:
    console = Console()

    if not rows:
        console.print("[yellow]No data returned.[/yellow]")
        return

    max_value = max(r["value"] for r in rows)
    total = sum(r["value"] for r in rows)
    avg = total / len(rows)

    table = Table(
        title="⚡ Ecotricity Power Consumption",
        box=box.ROUNDED,
        show_footer=True,
        footer_style="bold",
    )
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Day", style="dim", no_wrap=True)
    table.add_column(
        "Usage (kWh)",
        justify="right",
        footer=f"{total:.2f} kWh",
        no_wrap=True,
    )
    table.add_column("Bar", footer=f"avg {avg:.2f} kWh")

    for r in rows:
        v = r["value"]
        style = "green" if v < avg * 0.75 else "yellow" if v < avg * 1.25 else "red"
        table.add_row(
            r["date"],
            r["weekday"],
            f"[{style}]{v:.2f}[/{style}]",
            f"[{style}]{make_bar(v, max_value)}[/{style}]",
        )

    console.print()
    console.print(table)
    console.print()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Fetch power consumption data from Ecotricity portal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Date Presets:
  last 2 days   - Last 2 calendar days
  last 7 days   - Last 7 calendar days
  last 30 days  - Last 30 calendar days
  last month    - All of last calendar month
  last 3 months - Last 3 calendar months

Examples:
  python ecotricity.py --dates 'last 7 days'
  python ecotricity.py --dates 'last month'
        """
    )
    parser.add_argument(
        "--dates",
        type=str,
        default="last 7 days",
        help="Date range preset (default: 'last 7 days')"
    )
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Calculate date range
    date_from, date_to = calculate_date_range(args.dates)
    payload = create_payload(date_from, date_to)
    
    login, password = get_credentials()

    print("\n🔐 Logging in...")
    session = create_session(login, password)

    init_consumption_page(session)
    init_data(session)

    print("\n📊 Fetching data...")
    data = fetch_data(session, payload)
    print("  ✓ Data fetched successfully.")

    rows = parse_values(data)
    display_table(rows)


if __name__ == "__main__":
    main()