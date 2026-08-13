"""
Flask web UI for visualizing power consumption data.
"""

from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta
import json
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
    TOTAL_COST_PER_KWH,
)

app = Flask(__name__)

# Initialize database on startup
init_db()


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


@app.route("/health")
def health():
    """Health check endpoint for Docker/monitoring."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)
