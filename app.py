"""
Flask web UI for visualizing power consumption data.
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import json
import threading
from database import (
    init_db,
    get_all_consumption,
    get_consumption_by_range,
    get_statistics,
    get_daily_stats,
    get_last_fetch_date,
    get_data_range,
    get_daily_costs,
    get_monthly_costs,
    get_all_monthly_costs,
    get_cost_statistics,
    get_cost_trend,
    get_sync_info,
    update_sync_info,
    record_sync_start,
    record_sync_complete,
    TOTAL_COST_PER_KWH,
)

app = Flask(__name__)

# Initialize database on startup
init_db()

# Global variable to store the scheduler instance (set by run.py)
_scheduler = None

def set_scheduler(scheduler):
    """Set the global scheduler instance."""
    global _scheduler
    _scheduler = scheduler
    
    # Calculate and store next scheduled sync time
    if _scheduler and hasattr(_scheduler, 'scheduler'):
        try:
            jobs = _scheduler.scheduler.get_jobs()
            daily_job = next((j for j in jobs if j.id == 'daily_fetch'), None)
            if daily_job and daily_job.next_run_time:
                update_sync_info(next_scheduled_sync=daily_job.next_run_time.isoformat())
        except:
            pass


@app.route("/")
def index():
    """Render the main dashboard page."""
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    """Get consumption data for the chart."""
    days = 30  # Default to last 30 days
    rows = get_consumption_by_range(days)
    
    return jsonify({
        "dates": [r["date"] for r in rows],
        "values": [r["value"] for r in rows],
        "weekdays": [r["weekday"] for r in rows],
    })


@app.route("/api/statistics")
def api_statistics():
    """Get statistical summaries."""
    stats = get_statistics(days=30)
    daily = get_daily_stats()
    
    return jsonify({
        "overall": stats,
        "byDayOfWeek": daily,
        "lastFetch": get_last_fetch_date(),
    })


@app.route("/api/summary")
def api_summary():
    """Get summary statistics for display."""
    stats_30 = get_statistics(days=30)
    stats_all = get_statistics(days=365)  # Get all time if available
    start_date, end_date = get_data_range()
    
    return jsonify({
        "last30Days": {
            "total": round(stats_30["total"], 2),
            "average": round(stats_30["average"], 2),
            "min": round(stats_30["min"], 2),
            "max": round(stats_30["max"], 2),
            "count": stats_30["count"],
        },
        "allTime": {
            "total": round(stats_all["total"], 2),
            "average": round(stats_all["average"], 2),
            "min": round(stats_all["min"], 2),
            "max": round(stats_all["max"], 2),
            "count": stats_all["count"],
        },
        "dataRange": {
            "start": start_date,
            "end": end_date,
        },
        "lastFetch": get_last_fetch_date(),
    })


@app.route("/api/daily-breakdown")
def api_daily_breakdown():
    """Get average consumption by day of week."""
    daily = get_daily_stats()
    
    days_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    ordered_daily = {}
    for day in days_order:
        if day in daily:
            ordered_daily[day] = daily[day]
    
    return jsonify(ordered_daily)


@app.route("/api/trends")
def api_trends():
    """Get 7-day and 30-day trend data."""
    rows_7 = get_consumption_by_range(days=7)
    rows_30 = get_consumption_by_range(days=30)
    
    avg_7 = sum(r["value"] for r in rows_7) / len(rows_7) if rows_7 else 0
    avg_30 = sum(r["value"] for r in rows_30) / len(rows_30) if rows_30 else 0
    
    # Calculate trend (comparing first half to second half of 30-day window)
    if len(rows_30) >= 2:
        mid = len(rows_30) // 2
        first_half = sum(r["value"] for r in rows_30[:mid]) / mid if mid > 0 else 0
        second_half = sum(r["value"] for r in rows_30[mid:]) / (len(rows_30) - mid) if len(rows_30) > mid else 0
        trend = ((second_half - first_half) / first_half * 100) if first_half > 0 else 0
    else:
        trend = 0
    
    return jsonify({
        "avg7Days": round(avg_7, 2),
        "avg30Days": round(avg_30, 2),
        "trend30Days": round(trend, 1),  # % change
        "trend7vs30": round(((avg_7 - avg_30) / avg_30 * 100), 1) if avg_30 > 0 else 0,
    })


@app.route("/api/export/json")
def export_json():
    """Export all consumption data as JSON."""
    data = get_all_consumption()
    return jsonify(data)


@app.route("/api/export/csv")
def export_csv():
    """Export all consumption data as CSV."""
    from flask import make_response
    
    data = get_all_consumption()
    
    # Create CSV content
    csv_lines = ["Date,Day,Value (kWh)"]
    for row in data:
        csv_lines.append(f"{row['date']},{row['weekday']},{row['value']:.2f}")
    
    csv_content = "\n".join(csv_lines)
    
    response = make_response(csv_content)
    response.headers["Content-Disposition"] = "attachment; filename=consumption.csv"
    response.headers["Content-Type"] = "text/csv"
    
    return response


@app.route("/api/costs/daily")
def api_costs_daily():
    """Get daily costs for the last 30 days."""
    costs = get_daily_costs(days=30)
    return jsonify(costs)


@app.route("/api/costs/monthly")
def api_costs_monthly():
    """Get all monthly costs."""
    months = get_all_monthly_costs()
    return jsonify(months)


@app.route("/api/costs/statistics")
def api_costs_statistics():
    """Get cost statistics."""
    stats_30 = get_cost_statistics(days=30)
    stats_all = get_cost_statistics(days=365)
    trend = get_cost_trend(days=30)
    
    return jsonify({
        "last30Days": stats_30,
        "allTime": stats_all,
        "trend": trend,
        "costPerKwh": TOTAL_COST_PER_KWH
    })


@app.route("/api/sync/info")
def api_sync_info():
    """Get sync information (last sync and next scheduled sync)."""
    try:
        sync_info = get_sync_info()
        return jsonify(sync_info)
    except Exception as e:
        print(f"Error getting sync info: {e}")
        return jsonify({
            "last_sync": None,
            "next_scheduled_sync": None,
            "sync_status": "unknown",
            "error": str(e)
        }), 200


@app.route("/api/sync/trigger", methods=["POST"])
def api_sync_trigger():
    """Manually trigger a sync with optional date range."""
    global _scheduler
    
    # Get date range from query parameter (default: last 30 days)
    date_range = request.args.get('range', 'last 30 days')
    
    # Validate date range to prevent injection
    valid_ranges = ['last 7 days', 'last 14 days', 'last 30 days', 'last 3 months']
    if date_range not in valid_ranges:
        date_range = 'last 30 days'
    
    # Check if scheduler is available
    if _scheduler is None:
        return jsonify({
            "error": "Scheduler not initialized",
            "status": "unavailable",
            "message": "Sync not available. Please ensure app is running with 'python run.py all' or scheduler is initialized."
        }), 503
    
    try:
        # Record sync start
        try:
            record_sync_start()
            print(f"[app] Recorded sync start for {date_range}")
        except Exception as e:
            print(f"[app] Warning: Failed to record sync start: {e}")
        
        # Run fetch in background thread to avoid blocking the API response
        def run_fetch():
            try:
                print(f"[app] Starting fetch_and_store in background thread for {date_range}")
                _scheduler.fetch_and_store(date_range=date_range)
                try:
                    record_sync_complete()
                    print("[app] Recorded sync complete")
                except Exception as e:
                    print(f"[app] Warning: Failed to record sync complete: {e}")
            except Exception as e:
                try:
                    update_sync_info(sync_status='idle')
                except:
                    pass
                print(f"[app] Manual sync failed: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"[app] Spawning sync thread for {date_range}")
        thread = threading.Thread(target=run_fetch, daemon=True)
        thread.start()
        
        return jsonify({
            "status": "syncing",
            "message": "Sync started in background"
        }), 202
    
    except Exception as e:
        print(f"[app] Error in sync trigger endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "status": "error",
            "message": "An error occurred while triggering sync"
        }), 500


@app.route("/health")
def health():
    """Health check endpoint for Docker/monitoring."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)
