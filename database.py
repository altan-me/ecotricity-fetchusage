"""
Database module for storing and retrieving power consumption data.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Create data directory for persistent storage
DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "consumption.db"

# Cost configuration ($ per kWh + GST)
COST_PER_KWH = 0.2125  # $0.2125 per kWh before GST
GST_RATE = 0.15  # 15% GST
TOTAL_COST_PER_KWH = COST_PER_KWH * (1 + GST_RATE)  # $0.244375 per kWh with GST


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


def calculate_cost(kwh: float) -> float:
    """Calculate cost for given kWh usage (including GST)."""
    return kwh * TOTAL_COST_PER_KWH


def get_daily_costs(days: int = 30) -> List[Dict]:
    """Get consumption and costs for each day."""
    rows = get_consumption_by_range(days)
    
    daily_costs = []
    for row in rows:
        cost = calculate_cost(row["value"])
        daily_costs.append({
            "date": row["date"],
            "weekday": row["weekday"],
            "kwh": row["value"],
            "cost": round(cost, 2)
        })
    
    return daily_costs


def get_all_monthly_costs() -> List[Dict]:
    """Get consumption and costs for all available months."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            strftime('%Y-%m', date) as month,
            SUM(value) as total_kwh,
            COUNT(*) as days,
            MIN(value) as min_kwh,
            MAX(value) as max_kwh,
            AVG(value) as avg_kwh
        FROM consumption
        GROUP BY month
        ORDER BY month DESC
    """)
    
    months = []
    for row in cursor.fetchall():
        total_kwh = row[1]
        month_str = row[0]
        year, month = month_str.split('-')
        
        months.append({
            "year": int(year),
            "month": int(month),
            "month_str": month_str,
            "total_kwh": round(total_kwh, 2),
            "total_cost": round(calculate_cost(total_kwh), 2),
            "days": row[2],
            "min_kwh": round(row[3], 2),
            "max_kwh": round(row[4], 2),
            "avg_kwh": round(row[5], 2),
            "avg_daily_cost": round(calculate_cost(row[5]), 2)
        })
    
    conn.close()
    return months


def get_cost_statistics(days: Optional[int] = 30) -> Dict:
    """Get cost statistics for the period (None means all time)."""
    rows = get_consumption_by_range(days)
    
    if not rows:
        return {
            "period_days": days,
            "total_kwh": 0.0,
            "total_cost": 0.0,
            "avg_daily_kwh": 0.0,
            "avg_daily_cost": 0.0,
            "min_daily_cost": 0.0,
            "max_daily_cost": 0.0,
            "cost_per_kwh": TOTAL_COST_PER_KWH
        }
    
    values = [r["value"] for r in rows]
    total_kwh = sum(values)
    total_cost = calculate_cost(total_kwh)
    avg_daily_kwh = total_kwh / len(values)
    avg_daily_cost = calculate_cost(avg_daily_kwh)
    
    daily_costs = [calculate_cost(v) for v in values]
    min_daily_cost = min(daily_costs)
    max_daily_cost = max(daily_costs)
    
    return {
        "period_days": len(values),
        "total_kwh": round(total_kwh, 2),
        "total_cost": round(total_cost, 2),
        "avg_daily_kwh": round(avg_daily_kwh, 2),
        "avg_daily_cost": round(avg_daily_cost, 2),
        "min_daily_cost": round(min_daily_cost, 2),
        "max_daily_cost": round(max_daily_cost, 2),
        "cost_per_kwh": TOTAL_COST_PER_KWH
    }


def get_cost_trend(days: int = 30) -> Dict:
    """Calculate cost trends (comparing periods)."""
    from datetime import datetime
    
    now = datetime.now()
    
    # Get two equal periods
    first_half_start = now - timedelta(days=days)
    first_half_end = now - timedelta(days=days//2)
    second_half_start = first_half_end + timedelta(days=1)
    second_half_end = now
    
    first_start_str = first_half_start.strftime("%Y-%m-%d")
    first_end_str = first_half_end.strftime("%Y-%m-%d")
    second_start_str = second_half_start.strftime("%Y-%m-%d")
    second_end_str = second_half_end.strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # First period
    cursor.execute("""
        SELECT SUM(value) FROM consumption WHERE date >= ? AND date <= ?
    """, (first_start_str, first_end_str))
    first_period_kwh = cursor.fetchone()[0] or 0
    
    # Second period
    cursor.execute("""
        SELECT SUM(value) FROM consumption WHERE date >= ? AND date <= ?
    """, (second_start_str, second_end_str))
    second_period_kwh = cursor.fetchone()[0] or 0
    
    conn.close()
    
    first_period_cost = calculate_cost(first_period_kwh)
    second_period_cost = calculate_cost(second_period_kwh)
    
    # Calculate percentage change
    if first_period_cost > 0:
        cost_change_pct = ((second_period_cost - first_period_cost) / first_period_cost) * 100
    else:
        cost_change_pct = 0
    
    return {
        "first_period": {
            "kwh": round(first_period_kwh, 2),
            "cost": round(first_period_cost, 2)
        },
        "second_period": {
            "kwh": round(second_period_kwh, 2),
            "cost": round(second_period_cost, 2)
        },
        "cost_change_amount": round(second_period_cost - first_period_cost, 2),
        "cost_change_percent": round(cost_change_pct, 1)
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
