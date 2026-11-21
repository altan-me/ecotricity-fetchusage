"""
Database module for storing and retrieving power consumption data.
"""

import sqlite3
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Create data directory for persistent storage
DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "consumption.db"

# Default pricing. The active values are persisted in the pricing_settings
# table and can be changed from the web UI.
COST_PER_KWH = 0.2125  # default $/kWh before GST
DAILY_FIXED_RATE = 0.0  # default daily fixed charge before GST
GST_RATE = 0.15  # 15% GST (fixed)
TOTAL_COST_PER_KWH = COST_PER_KWH * (1 + GST_RATE)  # default incl. GST, for compatibility


def init_db() -> None:
    """Initialize the database with required tables."""
    # Ensure parent directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create consumption table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS consumption (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            weekday TEXT NOT NULL,
            value REAL NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create index for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_date ON consumption(date)
    """)
    
    # Create fetch attempts table to track backfill progress
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fetch_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_requested TEXT NOT NULL,
            attempt_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success BOOLEAN NOT NULL,
            error_message TEXT
        )
    """)
    
    # Create sync_info table to track sync status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            last_sync_timestamp TIMESTAMP,
            next_scheduled_sync TIMESTAMP,
            sync_status TEXT DEFAULT 'idle'
        )
    """)
    
    # Ensure we have at least one row in sync_info
    cursor.execute("SELECT COUNT(*) FROM sync_info")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO sync_info (sync_status)
            VALUES ('idle')
        """)

    # Legacy single-row table, kept so existing databases upgrade cleanly.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pricing_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cost_per_kwh REAL NOT NULL,
            daily_fixed_rate REAL NOT NULL,
            gst_rate REAL NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tiered pricing: each row applies from its effective date onwards.
    # A NULL effective_date is the baseline that applies to all data.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pricing_tiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cost_per_kwh REAL NOT NULL,
            daily_fixed_rate REAL NOT NULL,
            gst_rate REAL NOT NULL,
            effective_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM pricing_tiers")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            SELECT cost_per_kwh, daily_fixed_rate, gst_rate
            FROM pricing_settings LIMIT 1
        """)
        legacy = cursor.fetchone()
        if legacy:
            cursor.execute("""
                INSERT INTO pricing_tiers (cost_per_kwh, daily_fixed_rate, gst_rate, effective_date)
                VALUES (?, ?, ?, NULL)
            """, legacy)
        else:
            cursor.execute("""
                INSERT INTO pricing_tiers (cost_per_kwh, daily_fixed_rate, gst_rate, effective_date)
                VALUES (?, ?, ?, NULL)
            """, (COST_PER_KWH, DAILY_FIXED_RATE, GST_RATE))

    conn.commit()
    conn.close()


def insert_consumption_data(rows: List[Dict]) -> None:
    """Insert or update consumption data from a fetch."""
    if not rows:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.executemany("""
        INSERT OR REPLACE INTO consumption (date, weekday, value, fetched_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, [(row["date"], row["weekday"], row["value"]) for row in rows])
    
    conn.commit()
    conn.close()


def get_all_consumption() -> List[Dict]:
    """Get all consumption data ordered by date."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT date, weekday, value, fetched_at FROM consumption 
        ORDER BY date ASC
    """)
    
    rows = []
    for row in cursor.fetchall():
        rows.append({
            "date": row[0],
            "weekday": row[1],
            "value": row[2],
            "fetched_at": row[3]
        })
    
    conn.close()
    return rows


def get_consumption_by_range(days: Optional[int] = 30) -> List[Dict]:
    """Get consumption data for the last N days (None means all data)."""
    if days is None:
        return get_all_consumption()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    cursor.execute("""
        SELECT date, weekday, value, fetched_at FROM consumption 
        WHERE date >= ?
        ORDER BY date ASC
    """, (cutoff_date,))
    
    rows = []
    for row in cursor.fetchall():
        rows.append({
            "date": row[0],
            "weekday": row[1],
            "value": row[2],
            "fetched_at": row[3]
        })
    
    conn.close()
    return rows


def get_statistics(days: Optional[int] = 30) -> Dict:
    """Calculate statistics for the last N days (None means all time)."""
    rows = get_consumption_by_range(days)
    
    if not rows:
        return {
            "count": 0,
            "total": 0.0,
            "average": 0.0,
            "min": 0.0,
            "max": 0.0,
            "std_dev": 0.0
        }
    
    values = [r["value"] for r in rows]
    
    # Calculate mean
    mean = sum(values) / len(values)
    
    # Calculate standard deviation
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std_dev = variance ** 0.5
    
    return {
        "count": len(values),
        "total": sum(values),
        "average": mean,
        "min": min(values),
        "max": max(values),
        "std_dev": std_dev,
        "days": days
    }


def get_daily_stats() -> Dict:
    """Get average consumption by day of week."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT weekday, AVG(value) as avg_value, COUNT(*) as count, 
               MIN(value) as min_value, MAX(value) as max_value
        FROM consumption
        GROUP BY weekday
        ORDER BY 
            CASE weekday
                WHEN 'Mon' THEN 1
                WHEN 'Tue' THEN 2
                WHEN 'Wed' THEN 3
                WHEN 'Thu' THEN 4
                WHEN 'Fri' THEN 5
                WHEN 'Sat' THEN 6
                WHEN 'Sun' THEN 7
            END
    """)
    
    daily_stats = {}
    for row in cursor.fetchall():
        daily_stats[row[0]] = {
            "average": row[1],
            "count": row[2],
            "min": row[3],
            "max": row[4]
        }
    
    conn.close()
    return daily_stats


def get_last_fetch_date() -> Optional[str]:
    """Get the date of the most recent data fetch."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT MAX(date) FROM consumption")
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result[0] else None


def get_data_range() -> Tuple[Optional[str], Optional[str]]:
    """Get the date range of available data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT MIN(date), MAX(date) FROM consumption")
    result = cursor.fetchone()
    conn.close()
    
    return (result[0], result[1]) if result[0] else (None, None)


def record_fetch_attempts(dates: List[str], success: bool, error_message: str = None) -> None:
    """Record one attempt per date, in a single transaction."""
    if not dates:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.executemany("""
        INSERT INTO fetch_attempts (date_requested, success, error_message)
        VALUES (?, ?, ?)
    """, [(date, success, error_message) for date in dates])
    
    conn.commit()
    conn.close()


def record_fetch_attempt(date_requested: str, success: bool, error_message: str = None) -> None:
    """Record a fetch attempt for one date."""
    record_fetch_attempts([date_requested], success, error_message)


def get_missing_date_ranges(start_date: str = None, end_date: str = None) -> List[Tuple[str, str]]:
    """
    Find date ranges with missing or incomplete data.
    Returns list of (start_date, end_date) tuples to backfill.
    """
    from datetime import datetime, timedelta
    
    if end_date is None:
        # Yesterday: today never has final data yet, so asking for it every run
        # only wastes a request.
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if start_date is None:
        # Default to 90 days back
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    
    # Generate all expected dates
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    expected_dates = set()
    
    while current <= end:
        expected_dates.add(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    
    # Get actual dates in database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT date FROM consumption 
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date))
    
    available_dates = set(row[0] for row in cursor.fetchall())
    conn.close()
    
    # Find missing dates
    missing_dates = sorted(expected_dates - available_dates)
    
    if not missing_dates:
        return []
    
    # Group into ranges
    ranges = []
    range_start = missing_dates[0]
    range_end = missing_dates[0]
    
    for date_str in missing_dates[1:]:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        prev_date = datetime.strptime(range_end, "%Y-%m-%d")
        
        if (date - prev_date).days == 1:
            # Continue the range
            range_end = date_str
        else:
            # Gap detected, save range and start new one
            ranges.append((range_start, range_end))
            range_start = date_str
            range_end = date_str
    
    # Add final range
    ranges.append((range_start, range_end))

    # Skip ranges whose last failure is recent and still unretried, so a period
    # the portal has no data for is not re-requested on every startup/weekly run.
    recent_failures = set(get_failed_fetch_dates(days_back=7))
    return [r for r in ranges if r[1] not in recent_failures]


def get_failed_fetch_dates(days_back: int = 30) -> List[str]:
    """Get dates that failed to fetch in the last N days."""
    from datetime import datetime, timedelta
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
    
    cursor.execute("""
        SELECT DISTINCT f.date_requested FROM fetch_attempts f
        WHERE f.success = 0
        AND f.attempt_date > ?
        AND NOT EXISTS (
            SELECT 1 FROM fetch_attempts s
            WHERE s.date_requested = f.date_requested AND s.success = 1
        )
        ORDER BY f.date_requested DESC
    """, (cutoff,))
    
    failed_dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return failed_dates


def get_pricing_tiers() -> List[Dict]:
    """Return all pricing tiers, baseline first, then chronological."""
    defaults = [{
        "cost_per_kwh": COST_PER_KWH,
        "daily_fixed_rate": DAILY_FIXED_RATE,
        "gst_rate": GST_RATE,
        "effective_date": None,
    }]
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cost_per_kwh, daily_fixed_rate, gst_rate, effective_date
            FROM pricing_tiers
            ORDER BY (effective_date IS NOT NULL), effective_date, id
        """)
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.OperationalError:
        return defaults

    if not rows:
        return defaults
    return [
        {
            "cost_per_kwh": row[0],
            "daily_fixed_rate": row[1],
            "gst_rate": row[2],
            "effective_date": row[3],
        }
        for row in rows
    ]


def get_pricing_settings() -> Dict:
    """Return the most recently configured tier (the one the UI edits)."""
    tiers = get_pricing_tiers()
    current = tiers[-1]
    return {
        "cost_per_kwh": current["cost_per_kwh"],
        "daily_fixed_rate": current["daily_fixed_rate"],
        "gst_rate": current["gst_rate"],
        "effective_date": current["effective_date"],
        "tiers": tiers,
    }


def _validated_rate(value, name: str, maximum: float) -> float:
    """Validate a non-negative monetary rate."""
    try:
        rate = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(rate) or rate < 0 or rate > maximum:
        raise ValueError(f"{name} must be between 0 and {maximum}")
    return rate


def _validated_date(value) -> Optional[str]:
    """Normalise an optional effective date to YYYY-MM-DD."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError("Effective date must be in YYYY-MM-DD format")


def update_pricing_settings(cost_per_kwh, daily_fixed_rate, effective_date=None) -> Dict:
    """Persist a pricing tier. A blank effective date updates the all-data tier."""
    rate = _validated_rate(cost_per_kwh, "Price per kWh", 10)
    fixed = _validated_rate(daily_fixed_rate, "Daily fixed charge", 100)
    date = _validated_date(effective_date)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if date is None:
        cursor.execute("""
            SELECT id FROM pricing_tiers WHERE effective_date IS NULL ORDER BY id LIMIT 1
        """)
    else:
        cursor.execute("""
            SELECT id FROM pricing_tiers WHERE effective_date = ? ORDER BY id LIMIT 1
        """, (date,))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE pricing_tiers
            SET cost_per_kwh = ?, daily_fixed_rate = ?, gst_rate = ?
            WHERE id = ?
        """, (rate, fixed, GST_RATE, existing[0]))
    else:
        cursor.execute("""
            INSERT INTO pricing_tiers (cost_per_kwh, daily_fixed_rate, gst_rate, effective_date)
            VALUES (?, ?, ?, ?)
        """, (rate, fixed, GST_RATE, date))
    conn.commit()
    conn.close()
    return get_pricing_settings()


def pricing_for_date(date_str: str, tiers: List[Dict]) -> Dict:
    """Pick the tier in force on a given date."""
    dated = [t for t in tiers if t["effective_date"] and t["effective_date"] <= date_str]
    if dated:
        return max(dated, key=lambda t: t["effective_date"])
    for tier in tiers:
        if tier["effective_date"] is None:
            return tier
    return {
        "cost_per_kwh": COST_PER_KWH,
        "daily_fixed_rate": DAILY_FIXED_RATE,
        "gst_rate": GST_RATE,
    }


def cost_components(total_kwh: float, days: int, settings: Dict) -> Dict:
    """Split a period's cost into energy, daily fixed charge and GST (excl. rounding)."""
    energy = total_kwh * settings["cost_per_kwh"]
    fixed = days * settings["daily_fixed_rate"]
    gst = (energy + fixed) * settings["gst_rate"]
    return {
        "energy": energy,
        "fixed": fixed,
        "gst": gst,
        "total": energy + fixed + gst,
    }


def itemise_rows(rows: List[Dict], tiers: List[Dict]) -> Tuple[Dict, List[Dict]]:
    """Itemise a set of daily readings, applying the tier in force on each date."""
    totals = {"energy": 0.0, "fixed": 0.0, "gst": 0.0, "total": 0.0, "days": len(rows)}
    daily = []
    for row in rows:
        parts = cost_components(row["value"], 1, pricing_for_date(row["date"], tiers))
        daily.append(parts)
        for key in ("energy", "fixed", "gst", "total"):
            totals[key] += parts[key]
    return totals, daily


def calculate_cost(kwh: float) -> float:
    """Total cost for a day's kWh using the most recently configured tariff."""
    return cost_components(kwh, 1, get_pricing_settings())["total"]


def get_daily_costs(days: int = 30) -> List[Dict]:
    """Get consumption and itemised costs for each day."""
    tiers = get_pricing_tiers()
    rows = get_consumption_by_range(days)

    daily_costs = []
    for row in rows:
        settings = pricing_for_date(row["date"], tiers)
        parts = cost_components(row["value"], 1, settings)
        daily_costs.append({
            "date": row["date"],
            "weekday": row["weekday"],
            "kwh": row["value"],
            "energy_cost": round(parts["energy"], 2),
            "fixed_cost": round(parts["fixed"], 2),
            "gst": round(parts["gst"], 2),
            "cost": round(parts["total"], 2),
        })

    return daily_costs


def get_all_monthly_costs() -> List[Dict]:
    """Get consumption and itemised costs for all available months."""
    tiers = get_pricing_tiers()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT date, value FROM consumption ORDER BY date ASC")

    by_month = {}
    for date_str, value in cursor.fetchall():
        if not date_str:
            continue
        by_month.setdefault(date_str[:7], []).append({"date": date_str, "value": value})
    conn.close()

    months = []
    for month_str in sorted(by_month, reverse=True):
        rows = by_month[month_str]
        values = [row["value"] for row in rows]
        totals, _ = itemise_rows(rows, tiers)
        year, month = month_str.split('-')
        months.append({
            "year": int(year),
            "month": int(month),
            "month_str": month_str,
            "total_kwh": round(sum(values), 2),
            "energy_cost": round(totals["energy"], 2),
            "fixed_cost": round(totals["fixed"], 2),
            "gst": round(totals["gst"], 2),
            "total_cost": round(totals["total"], 2),
            "days": len(rows),
            "min_kwh": round(min(values), 2),
            "max_kwh": round(max(values), 2),
            "avg_kwh": round(sum(values) / len(values), 2),
            "avg_daily_cost": round(totals["total"] / len(rows), 2),
        })
    return months


def get_cost_statistics(days: Optional[int] = 30) -> Dict:
    """Get itemised cost statistics for the period (None means all time)."""
    tiers = get_pricing_tiers()
    rows = get_consumption_by_range(days)
    current = get_pricing_settings()

    pricing = {
        "cost_per_kwh": current["cost_per_kwh"],
        "daily_fixed_rate": current["daily_fixed_rate"],
        "gst_rate": current["gst_rate"],
        "effective_date": current["effective_date"],
    }

    if not rows:
        return {
            "period_days": days,
            "total_kwh": 0.0,
            "energy_cost": 0.0,
            "fixed_cost": 0.0,
            "gst": 0.0,
            "total_cost": 0.0,
            "avg_daily_kwh": 0.0,
            "avg_daily_cost": 0.0,
            "min_daily_cost": 0.0,
            "max_daily_cost": 0.0,
            "cost_per_kwh": current["cost_per_kwh"] * (1 + current["gst_rate"]),
            "pricing": pricing,
        }

    totals, daily = itemise_rows(rows, tiers)
    total_kwh = sum(row["value"] for row in rows)

    return {
        "period_days": len(rows),
        "total_kwh": round(total_kwh, 2),
        "energy_cost": round(totals["energy"], 2),
        "fixed_cost": round(totals["fixed"], 2),
        "gst": round(totals["gst"], 2),
        "total_cost": round(totals["total"], 2),
        "avg_daily_kwh": round(total_kwh / len(rows), 2),
        "avg_daily_cost": round(totals["total"] / len(rows), 2),
        "min_daily_cost": round(min(p["total"] for p in daily), 2),
        "max_daily_cost": round(max(p["total"] for p in daily), 2),
        "cost_per_kwh": current["cost_per_kwh"] * (1 + current["gst_rate"]),
        "pricing": pricing,
    }


def get_cost_trend(days: int = 30) -> Dict:
    """Calculate cost trends, applying the tariff in force on each date."""
    tiers = get_pricing_tiers()
    now = datetime.now()

    first_half_start = now - timedelta(days=days)
    first_half_end = now - timedelta(days=days // 2)
    second_half_start = first_half_end + timedelta(days=1)
    second_half_end = now

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date, value FROM consumption
        WHERE date >= ? AND date <= ?
    """, (first_half_start.strftime("%Y-%m-%d"), first_half_end.strftime("%Y-%m-%d")))
    first_rows = [{"date": r[0], "value": r[1]} for r in cursor.fetchall()]

    cursor.execute("""
        SELECT date, value FROM consumption
        WHERE date >= ? AND date <= ?
    """, (second_half_start.strftime("%Y-%m-%d"), second_half_end.strftime("%Y-%m-%d")))
    second_rows = [{"date": r[0], "value": r[1]} for r in cursor.fetchall()]
    conn.close()

    first_totals, _ = itemise_rows(first_rows, tiers)
    second_totals, _ = itemise_rows(second_rows, tiers)
    first_period_cost = first_totals["total"]
    second_period_cost = second_totals["total"]

    if first_period_cost > 0:
        cost_change_pct = ((second_period_cost - first_period_cost) / first_period_cost) * 100
    else:
        cost_change_pct = 0

    def period_payload(rows, totals):
        return {
            "kwh": round(sum(r["value"] for r in rows), 2),
            "days": len(rows),
            "energy_cost": round(totals["energy"], 2),
            "fixed_cost": round(totals["fixed"], 2),
            "gst": round(totals["gst"], 2),
            "cost": round(totals["total"], 2),
        }

    return {
        "first_period": period_payload(first_rows, first_totals),
        "second_period": period_payload(second_rows, second_totals),
        "cost_change_amount": round(second_period_cost - first_period_cost, 2),
        "cost_change_percent": round(cost_change_pct, 1),
    }


def get_sync_info() -> Dict:
    """Get current sync information (last sync and next scheduled sync)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT last_sync_timestamp, next_scheduled_sync, sync_status
        FROM sync_info
        LIMIT 1
    """)
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "last_sync": result[0],
            "next_scheduled_sync": result[1],
            "sync_status": result[2]
        }
    else:
        return {
            "last_sync": None,
            "next_scheduled_sync": None,
            "sync_status": "idle"
        }


def update_sync_info(last_sync_timestamp: str = None, next_scheduled_sync: str = None, sync_status: str = None) -> None:
    """Update sync information."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Build update query dynamically
    updates = []
    params = []
    
    if last_sync_timestamp is not None:
        updates.append("last_sync_timestamp = ?")
        params.append(last_sync_timestamp)
    
    if next_scheduled_sync is not None:
        updates.append("next_scheduled_sync = ?")
        params.append(next_scheduled_sync)
    
    if sync_status is not None:
        updates.append("sync_status = ?")
        params.append(sync_status)
    
    if updates:
        query = "UPDATE sync_info SET " + ", ".join(updates)
        cursor.execute(query, params)
        conn.commit()
    
    conn.close()


def record_sync_start() -> None:
    """Record that a sync has started."""
    update_sync_info(sync_status='syncing')


def record_sync_complete() -> None:
    """Record that a sync has completed successfully."""
    from datetime import datetime
    now = datetime.now().isoformat()
    update_sync_info(last_sync_timestamp=now, sync_status='idle')
