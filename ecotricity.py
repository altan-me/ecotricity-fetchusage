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
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Optional

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

# ── Config ───────────────────────────────────────────────────────────────────

BASE_URL = "https://portal.ecotricity.co.nz/powercommerce/eco/fo/portal"
PORTAL_ORIGIN = "https://portal.ecotricity.co.nz"
LOGIN_URL = f"{BASE_URL}/loginProcess"
DATA_URL = f"{BASE_URL}/analysis/valueRequest"

INDICATOR_ID = "470f2d40-42ca-11f1-9ba3-020017005c7e"

# ⚠️  IMPORTANT API DETAILS:
# The Ecotricity API supports three dateTypes for consumption queries:
#   - "DAY": Single day only, returns HALF_HOUR granularity (30-minute intervals)
#   - "WEEK": 1-7 day ranges, returns DAY granularity
#   - "MONTH": Any date range, returns DAY granularity
# This code uses WEEK for short ranges and MONTH for longer ranges.
# DAY type is available for fetching single-day data with higher time resolution.
# See create_payload() for the official payload structure with full documentation.

# ⚠️  IMPORTANT: If you get "No metering data available" (503), the date range likely has no data.
# Check your account in the Ecotricity portal to see what date ranges contain data.

# ── Timezone ──────────────────────────────────────────────────────────────────
# The container almost always runs in UTC, so we never trust the host clock's
# local offset. Every date sent to the portal is rendered in the customer's
# timezone with the correct offset for that specific date (NZST/NZDT aware).
PORTAL_TIMEZONE_NAME = os.environ.get("ECOTRICITY_TIMEZONE", "Pacific/Auckland")


class EcotricityError(Exception):
    """Base class for errors raised by the Ecotricity client."""


class EcotricityAuthError(EcotricityError):
    """Login failed or the session was rejected (HTTP 401/403)."""


class EcotricityNoDataError(EcotricityError):
    """The account has no metering data for the requested range."""


class EcotricityServiceUnavailableError(EcotricityError):
    """The portal/WAF was unavailable after exhausting retries."""


def _init_timezone():
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(PORTAL_TIMEZONE_NAME)
    except (KeyError, ValueError, OSError):
        Console().print(
            f"[yellow]⚠ Unknown timezone '{PORTAL_TIMEZONE_NAME}', falling back to UTC[/yellow]"
        )
        return timezone.utc


PORTAL_TIMEZONE = _init_timezone()


# ── HTTP behaviour ───────────────────────────────────────────────────────────
# These mirror the browser traffic the portal is built for and make the client
# resilient to the transient 429/5xx responses its WAF occasionally emits.
REQUEST_TIMEOUT = float(os.environ.get("ECOTRICITY_TIMEOUT", "30"))
MAX_ATTEMPTS = max(1, int(os.environ.get("ECOTRICITY_MAX_ATTEMPTS", "4")))
BACKOFF_BASE = float(os.environ.get("ECOTRICITY_BACKOFF_BASE", "2.0"))
BACKOFF_CAP = float(os.environ.get("ECOTRICITY_BACKOFF_CAP", "30"))
# Polite pause between consecutive API calls (e.g. during a backfill) so we do
# not trip the portal's rate limiting, which surfaces as an HTTP 503.
BATCH_DELAY = float(os.environ.get("ECOTRICITY_BATCH_DELAY", "1.5"))

# Statuses that are worth retrying because they are transient at the portal/WAF.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

CHROME_FULL_VERSION = "146.0.0.0"
CHROME_MAJOR_VERSION = "146"

# Session-wide headers a real Chrome sends on every request to this host.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{CHROME_FULL_VERSION} Safari/537.36"
    ),
    "Accept-Language": "en-NZ,en-US;q=0.9,en;q=0.8",
    "sec-ch-ua": (
        f'"Chromium";v="{CHROME_MAJOR_VERSION}", '
        f'"Google Chrome";v="{CHROME_MAJOR_VERSION}", '
        '"Not-A.Brand";v="99"'
    ),
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "DNT": "1",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# Extra headers for top-level page navigations (the "document" requests).
NAV_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Upgrade-Insecure-Requests": "1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
}

# Extra headers for the portal's Ajax/XHR endpoints.
XHR_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": PORTAL_ORIGIN,
    "Content-Type": "application/json",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}


def portal_now() -> datetime:
    """Current wall-clock time in the portal's timezone (naive datetime)."""
    if PORTAL_TIMEZONE is not None:
        return datetime.now(PORTAL_TIMEZONE).replace(tzinfo=None)
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_portal_datetime(dt: datetime) -> str:
    """Render a datetime as ISO with the correct offset for the portal timezone.

    e.g. "2026-09-27T00:00:00.000+12:00" (NZST) or "...+13:00" (NZDT). This keeps
    the requested date range correct no matter what timezone the container uses.
    """
    tz = PORTAL_TIMEZONE or timezone.utc
    aware = dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
    offset = aware.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return (
        f"{dt.strftime('%Y-%m-%dT%H:%M:%S.000')}"
        f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"
    )


def _retry_after_seconds(resp: requests.Response) -> Optional[float]:
    """Parse a Retry-After header (seconds or HTTP-date) into a delay."""
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


def _looks_like_no_data(resp: requests.Response) -> bool:
    """True when a 503 is the portal's business 'no metering data' response.

    That is not a transient outage, so retrying it would only waste time.
    """
    if "json" not in resp.headers.get("content-type", "").lower():
        return False
    try:
        body = resp.json()
    except ValueError:
        return False
    return "no metering data" in json.dumps(body).lower()


def _sleep_before_retry(attempt: int, resp: Optional[requests.Response] = None) -> None:
    """Back off before the next attempt, honouring Retry-After when present."""
    if resp is not None:
        retry_after = _retry_after_seconds(resp)
        if retry_after is not None:
            time.sleep(min(retry_after, BACKOFF_CAP))
            return
    delay = min(BACKOFF_CAP, BACKOFF_BASE ** attempt)
    time.sleep(delay * (0.5 + random.random() / 2))  # exponential backoff + jitter


def _request(
    session: requests.Session,
    method: str,
    url: str,
    *,
    headers: Optional[dict] = None,
    is_retryable: Optional[Callable[[requests.Response], bool]] = None,
    max_attempts: Optional[int] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> requests.Response:
    """Issue an HTTP request, retrying transient failures with backoff.

    A reverse-engineered client sees occasional 429/5xx responses from the
    portal's edge (more so from a datacenter IP than a home connection). Rather
    than treating the first one as fatal, retry it the way a browser/operator
    would before giving up.
    """
    console = Console()
    attempts = max_attempts or MAX_ATTEMPTS
    request_timeout = timeout or REQUEST_TIMEOUT
    retry_check = is_retryable or (lambda r: r.status_code in RETRY_STATUSES)

    for attempt in range(1, attempts + 1):
        try:
            resp = session.request(
                method, url, headers=headers, timeout=request_timeout, **kwargs
            )
        except requests.exceptions.RequestException as exc:
            if attempt >= attempts:
                raise EcotricityError(f"{method} {url} failed: {exc}") from exc
            console.print(
                f"  [yellow]⚠ {method} {url} error ({exc.__class__.__name__}); "
                f"retrying ({attempt}/{attempts - 1})...[/yellow]"
            )
            _sleep_before_retry(attempt)
            continue

        if retry_check(resp) and attempt < attempts:
            console.print(
                f"  [yellow]⚠ {method} {url} returned {resp.status_code}; "
                f"retrying ({attempt}/{attempts - 1})...[/yellow]"
            )
            _sleep_before_retry(attempt, resp)
            continue

        return resp

    raise EcotricityError(f"{method} {url} failed after {attempts} attempts")


# ── Date Range ────────────────────────────────────────────────────────────────


def calculate_date_range(preset: str) -> tuple[str, str, str]:
    """Calculate date range and appropriate dateType from a preset string.
    
    The Ecotricity API supports three dateTypes:
      - DAY: Single day only, returns HALF_HOUR granularity data
      - WEEK: 1-7 day ranges, returns DAY granularity data
      - MONTH: Any range, returns DAY granularity data
    
    Presets:
      - 'last 2 days': Last 2 calendar days (dateType: WEEK, DAY granularity)
      - 'last 7 days': Last 7 calendar days (dateType: WEEK, DAY granularity)
      - 'last 30 days': Last 30 calendar days (dateType: MONTH, DAY granularity)
      - 'last month': All of last calendar month (dateType: MONTH, DAY granularity)
      - 'last 3 months': Last 3 calendar months (dateType: MONTH, DAY granularity)
    
    Returns:
        tuple: (date_from, date_to, dateType)
    """
    console = Console()
    now = portal_now()
    
    if preset == "last 2 days":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=2)
        date_type = "WEEK"
    elif preset == "last 7 days":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=7)
        date_type = "WEEK"
    elif preset == "last 30 days":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=30)
        date_type = "MONTH"
    elif preset == "last month":
        # First day of current month
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # First day of last month
        start = first_of_this_month - timedelta(days=1)
        start = start.replace(day=1)
        # Last day of last month (day before first of this month)
        end = first_of_this_month
        date_type = "MONTH"
    elif preset == "last 3 months":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Go back 3 months
        month = now.month - 3
        year = now.year
        while month < 1:
            month += 12
            year -= 1
        start = now.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
        date_type = "MONTH"
    else:
        console.print(f"[red]Unknown preset: {preset}[/red]", style="red")
        console.print("Valid presets: 'last 2 days', 'last 7 days', 'last 30 days', 'last month', 'last 3 months'")
        sys.exit(1)
    
    # Format as ISO with the correct offset for the portal timezone
    date_from = format_portal_datetime(start)
    date_to = format_portal_datetime(end)
    
    console.print(f"\n  📅 Date Range: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')} (dateType: {date_type})")
    
    return date_from, date_to, date_type


def create_payload(date_from: str, date_to: str, date_type: str = "MONTH") -> dict:
    """Create the official Ecotricity API payload for consumption data.
    
    This payload follows the Ecotricity portal's API format for fetching power
    consumption data. The dateType is set based on the requested date range:
      - WEEK: For 1-7 day ranges (DAY granularity)
      - MONTH: For any range (DAY granularity)
      - DAY: For single day only (HALF_HOUR granularity)
    
    Args:
        date_from: Start date in ISO format with timezone (e.g., "2026-08-01T00:00:00.000+12:00")
        date_to: End date in ISO format with timezone (e.g., "2026-09-01T00:00:00.000+12:00")
        date_type: API dateType to use - "DAY" (single day only), "WEEK" (1-7 days), or "MONTH" (any range)
    
    Returns:
        dict: API payload with the following structure:
        - dateType: "DAY", "WEEK", or "MONTH" - Aggregation type based on date range
        - indicatorValueRequests: Array containing indicator configuration
          - valueRange: Dict mapping date_from to date_to (period to fetch)
          - indicatorID: Unique ID for the metering point
          - indicatorType: "INDICATOR_GROUP" - Fetches data for the meter group
          - featureValueRequests: Array specifying consumption metric
            - featureID: "POWER_ACTIVE_PURCHASE_CONSUMPTION" - Active power purchase (consumption)
            - granularityType: "HALF_HOUR" (DAY type) or "DAY" (WEEK/MONTH types)
            - aggregationType: "SUM" - Aggregate consumption over each period
        - userTimeZone: "Pacific/Auckland" - Timezone for date interpretation
    """
    # Select granularityType based on dateType
    # DAY type returns HALF_HOUR granularity, WEEK/MONTH return DAY granularity
    granularity = "HALF_HOUR" if date_type == "DAY" else "DAY"
    return {
        "dateType": date_type,  # DAY (single day), WEEK (1-7 days), or MONTH (any range)
        "indicatorValueRequests": [
            {
                # valueRange: Period to fetch (keys and values are ISO dates with timezone)
                # DAY type: must be a single day (e.g., 2026-08-30 to 2026-08-31)
                # WEEK type: 1-7 day range
                # MONTH type: any range
                "valueRange": {date_from: date_to},
                # Unique identifier for this metering installation point
                "indicatorID": INDICATOR_ID,
                # INDICATOR_GROUP fetches data for the entire meter group
                "indicatorType": "INDICATOR_GROUP",
                # Index 0 for primary request
                "index": 0,
                # Feature configuration: what metric to fetch and how to aggregate it
                "featureValueRequests": [
                    {
                        # POWER_ACTIVE_PURCHASE_CONSUMPTION: the electricity consumption metric
                        "featureID": "POWER_ACTIVE_PURCHASE_CONSUMPTION",
                        # Granularity varies by dateType:
                        # - DAY type: HALF_HOUR (detailed 30-minute intervals)
                        # - WEEK/MONTH types: DAY (daily data)
                        "granularityType": granularity,
                        # No attribute filters needed for basic consumption data
                        "filterByIndicatorAttributesMap": {},
                        # SUM: aggregate consumption for each period
                        "aggregationType": "SUM",
                    }
                ],
            }
        ],
        # Timezone context for all dates in the payload
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

    # Browser-like headers used as defaults for every request on this session.
    session.headers.update(BROWSER_HEADERS)

    # Warm up the session the way a browser does: load the portal entry page
    # first so it can hand out its session cookie before we POST credentials.
    # Jumping straight to the credential POST is a bot signal that the edge
    # treats far more harshly from a datacenter/container IP.
    console.print("\n  [DEBUG] Warming up session...")
    try:
        warmup = _request(
            session,
            "GET",
            f"{BASE_URL}/start",
            headers={**NAV_HEADERS, "Referer": f"{BASE_URL}/start"},
            max_attempts=2,
        )
        console.print(f"  [DEBUG] Warm-up status: {warmup.status_code}", style="dim")
    except EcotricityError as exc:
        console.print(f"  [yellow]⚠ Session warm-up failed ({exc}); continuing[/yellow]")

    console.print("\n  [DEBUG] Attempting login...")
    console.print(f"  [DEBUG] URL: {LOGIN_URL}")

    # POST login — session will automatically store any cookies from the response
    resp = _request(
        session,
        "POST",
        LOGIN_URL,
        data={"login": login, "password": password},
        headers={
            **NAV_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": PORTAL_ORIGIN,
            "Referer": f"{BASE_URL}/start",
        },
        allow_redirects=True,
    )

    # Log response details for debugging
    console.print(f"\n  [DEBUG] Response Status Code: {resp.status_code}")
    console.print(f"  [DEBUG] Response URL (after redirects): {resp.url}")
    console.print(f"  [DEBUG] Response Content Length: {len(resp.content)} bytes", style="dim")
    
    # Check we didn't land back on the login page (failed auth)
    if "loginProcess" in resp.url or "start" in resp.url:
        raise EcotricityAuthError(
            "Login failed — ended up back at the login page. Check your credentials."
        )

    if resp.status_code not in (200, 302):
        raise EcotricityAuthError(f"Unexpected login response: {resp.status_code}")

    if not session.cookies:
        console.print(
            "\n  [yellow]⚠  WARNING: No cookies set after login! "
            "This may indicate failed authentication.[/yellow]"
        )
    else:
        console.print("\n  ✓ Logged in successfully.")
    
    return session


# ── Initialize ────────────────────────────────────────────────────────────────


def _warmup_page(session: requests.Session, url: str, referer: str) -> None:
    """Best-effort navigation to set up page state, mirroring a real browser."""
    console = Console()
    try:
        resp = _request(
            session,
            "GET",
            url,
            headers={**NAV_HEADERS, "Referer": referer},
            max_attempts=2,
        )
        console.print(f"  [DEBUG] {url} -> {resp.status_code}", style="dim")
    except EcotricityError as exc:
        console.print(f"  [yellow]⚠ Could not load {url}: {exc}[/yellow]")


def init_consumption_page(session: requests.Session) -> None:
    """Visit the consumption details page to establish page state/CSRF tokens."""
    console = Console()
    consumption_url = f"{BASE_URL}/consumptionDetails"
    console.print(f"\n  [DEBUG] Initializing consumption page: {consumption_url}")

    # Load the landing page first so the referer chain matches the real UI
    # (start -> login -> home -> consumptionDetails).
    _warmup_page(session, f"{BASE_URL}/home", f"{BASE_URL}/start")

    resp = _request(
        session,
        "GET",
        consumption_url,
        headers={**NAV_HEADERS, "Referer": f"{BASE_URL}/home"},
    )
    
    console.print(f"  [DEBUG] Consumption page status: {resp.status_code}", style="dim")
    console.print(f"  [DEBUG] Consumption page content length: {len(resp.content)} bytes", style="dim")
    
    if resp.status_code >= 400:
        console.print(f"  ⚠️  Warning: Got status {resp.status_code} fetching consumption page", style="yellow")
    else:
        console.print("  ✓ Consumption page loaded.")


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
    
    resp = _request(
        session,
        "POST",
        init_data_url,
        json=init_payload,
        headers={**XHR_HEADERS, "Referer": f"{BASE_URL}/consumptionDetails"},
    )
    
    console.print(f"  [DEBUG] Init data response status: {resp.status_code}", style="dim")
    
    if resp.status_code >= 400:
        console.print(f"  ⚠️  Warning: Got status {resp.status_code} on init data", style="yellow")
    else:
        console.print("  ✓ Data initialized.")


# ── Fetch ─────────────────────────────────────────────────────────────────────


def fetch_consumption(session: requests.Session, date_range: str) -> list[dict]:
    """Run one full fetch cycle (page state, init, fetch, parse)."""
    init_consumption_page(session)
    init_data(session)
    date_from, date_to, date_type = calculate_date_range(date_range)
    payload = create_payload(date_from, date_to, date_type)
    data = fetch_data(session, payload)
    return parse_values(data)


def fetch_data(session: requests.Session, payload: dict) -> dict:
    """Fetch consumption data from Ecotricity API using the official payload format.
    
    The payload follows the Ecotricity API format with three supported dateTypes:
    - dateType: "DAY" (single day, HALF_HOUR granularity), "WEEK" (1-7 days, DAY granularity), or "MONTH" (any range, DAY granularity)
    - indicatorValueRequests: Contains the date range, meter ID, and feature config
    - featureValueRequests: Specifies POWER_ACTIVE_PURCHASE_CONSUMPTION with granularity based on dateType
    - userTimeZone: Pacific/Auckland for date interpretation
    """
    console = Console()
    
    console.print(f"\n  [DEBUG] Data fetch URL: {DATA_URL}")
    console.print(f"  [DEBUG] Payload dateType: {payload.get('dateType', 'UNKNOWN')}")
    console.print(f"  [DEBUG] Payload userTimeZone: {payload.get('userTimeZone', 'UNKNOWN')}")
    
    request_headers = {**XHR_HEADERS, "Referer": f"{BASE_URL}/consumptionDetails"}
    
    console.print("\n  [DEBUG] Request Payload:")
    console.print(json.dumps(payload, indent=2), style="dim")
    
    # A 503 carrying the portal's "no metering data" JSON is a business answer,
    # not a transient outage — retrying it would only burn time and hit rate
    # limits, so exclude it from the retry set.
    resp = _request(
        session,
        "POST",
        DATA_URL,
        json=payload,
        headers=request_headers,
        is_retryable=lambda r: r.status_code in RETRY_STATUSES and not _looks_like_no_data(r),
    )

    console.print(f"\n  [DEBUG] Data fetch response status: {resp.status_code}")
    
    console.print("\n  [DEBUG] Data fetch response body:", style="dim")
    response_json = None
    try:
        response_json = resp.json()
        console.print(json.dumps(response_json, indent=2), style="dim")
    except ValueError:
        console.print(f"{resp.text[:800]}", style="dim")

    if resp.status_code in (401, 403):
        raise EcotricityAuthError(
            f"Auth error ({resp.status_code}) on data fetch. "
            "Session may have expired or cookies not being sent."
        )
    
    if resp.status_code == 503:
        if _looks_like_no_data(resp):
            raise EcotricityNoDataError(
                "No metering data available for the requested date range. "
                "Try a different range (check the portal for available dates)."
            )
        raise EcotricityServiceUnavailableError(
            "Portal returned 503 after retries "
            "(temporary maintenance or rate limiting)."
        )
    
    if resp.status_code >= 400:
        raise EcotricityError(
            f"HTTP Error ({resp.status_code}) fetching consumption data from {DATA_URL}."
        )

    if response_json is not None:
        return response_json
    return resp.json()


# ── Parse ─────────────────────────────────────────────────────────────────────


WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


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
                    # Fixed names: strftime("%a") depends on the process locale.
                    weekday = WEEKDAY_NAMES[start_dt.weekday()]
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
    
    login, password = get_credentials()

    console = Console()
    print("\n🔐 Logging in...")

    try:
        session = create_session(login, password)

        print("\n📊 Fetching data...")
        rows = fetch_consumption(session, args.dates)
        print("  ✓ Data fetched successfully.")
    except EcotricityNoDataError as exc:
        console.print(f"\n  [yellow]⚠ {exc}[/yellow]")
        sys.exit(1)
    except EcotricityError as exc:
        console.print(f"\n  [red]❌ {exc}[/red]")
        sys.exit(1)

    display_table(rows)


if __name__ == "__main__":
    main()