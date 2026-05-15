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

import json
import os
import sys

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

# ⚠️  IMPORTANT: Update these dates to match data available in your Ecotricity account!
# If you get "No metering data available" (503), these dates likely have no data.
# Check your account in the Ecotricity portal to see what date ranges contain data.
DATE_FROM = "2026-05-04T00:00:00.000+02:00"
DATE_TO = "2026-05-13T00:00:00.000+02:00"

PAYLOAD = {
    "dateType": "MONTH",
    "indicatorValueRequests": [
        {
            "valueRange": {DATE_FROM: DATE_TO},
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


# ── Fetch ─────────────────────────────────────────────────────────────────────


def fetch_data(session: requests.Session) -> dict:
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
    console.print(json.dumps(PAYLOAD, indent=2), style="dim")
    
    resp = session.post(
        DATA_URL,
        json=PAYLOAD,
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
    # Load environment variables from .env file
    load_dotenv()
    
    login, password = get_credentials()

    print("\n🔐 Logging in...")
    session = create_session(login, password)

    init_consumption_page(session)

    print("\n📊 Fetching data...")
    data = fetch_data(session)
    print("  ✓ Data fetched successfully.")

    rows = parse_values(data)
    display_table(rows)


if __name__ == "__main__":
    main()