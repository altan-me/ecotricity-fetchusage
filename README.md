# ⚡ Ecotricity Consumption Tracker

A comprehensive Python system to automatically fetch your power consumption data from the Ecotricity portal, store it in a local database, and visualize it with an interactive web dashboard.

## Features

### Core Features
- 🔐 **Secure Authentication**: Automatically logs into your Ecotricity account
- 📊 **Data Fetching**: Retrieves daily power consumption data from the Ecotricity API
- 💾 **Local Database**: Stores consumption data in SQLite for historical tracking
- 📈 **Interactive Dashboard**: Beautiful web UI with real-time visualizations
- 🔄 **Scheduled Updates**: Automatic periodic fetching of new consumption data

### Dashboard Features
- 📊 **Time Series Visualization**: View consumption trends over time
- 📉 **Statistical Analysis**: Average, min, max, and trending insights
- 📍 **Day of Week Breakdown**: See which days typically use more power
- 🎯 **High/Low Analysis**: Identify your consumption patterns
- 📥 **Data Export**: Download data as JSON or CSV
- 🎨 **Beautiful UI**: Modern, responsive design

### CLI Features
- 🎨 **Rich Display**: Formatted table with color-coded consumption values
- 🔍 **Debug Output**: Comprehensive logging for troubleshooting
- 🗓️ **Flexible Date Ranges**: Multiple preset date range options

## Requirements

- Python 3.7+
- Dependencies (see `requirements.txt`):
  - `requests` - HTTP requests library
  - `python-dotenv` - Environment variable management
  - `rich` - Rich terminal output formatting
  - `flask` - Web framework for dashboard
  - `apscheduler` - Background task scheduling

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ecotricity-fetchusage
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### Credentials Setup (Required)

You have three options to provide your Ecotricity credentials:

#### Option 1: Environment Variables (Recommended)
```bash
# Windows (PowerShell)
$env:ECOTRICITY_LOGIN="your_account_number"
$env:ECOTRICITY_PASSWORD="your_password"
python run.py web

# Windows (CMD)
set ECOTRICITY_LOGIN=your_account_number
set ECOTRICITY_PASSWORD=your_password
python run.py web

# Linux/macOS
export ECOTRICITY_LOGIN="your_account_number"
export ECOTRICITY_PASSWORD="your_password"
python run.py web
```

#### Option 2: .env File (Recommended for Development)
1. Create a `.env` file in the project directory:
   ```
   ECOTRICITY_LOGIN=your_account_number
   ECOTRICITY_PASSWORD=your_password
   ```

2. Run any command:
   ```bash
   python run.py web
   python run.py scheduler
   python run.py all
   ```

#### Option 3: Interactive Prompts
Simply run the script without setting credentials:
```bash
python ecotricity.py
```
You'll be prompted to enter your login and password.

### Optional: Configuration File

Create or edit `config.json` to customize settings:

```json
{
  "scheduler": {
    "enabled": true,
    "hour": 23,
    "minute": 0
  },
  "web_ui": {
    "host": "127.0.0.1",
    "port": 5000,
    "debug": false
  }
}
```

### Cost Configuration

To adjust the cost calculations, edit [database.py](database.py) and modify these constants:

```python
COST_PER_KWH = 0.2125  # $0.2125 per kWh (before GST)
GST_RATE = 0.15       # 15% GST
```

**Default Settings:**
- Cost: $0.2125 per kWh + 15% GST = **$0.244375 per kWh**
- All dashboard costs include GST automatically

## Usage

### Quick Start: Run Everything

The easiest way to get started is to run the complete system with both scheduler and web UI:

```bash
python run.py all
```

This will:
1. **Backfill** missing historical data (90 days by default)
2. **Fetch** consumption data immediately
3. Start the **background scheduler** to fetch data daily at 23:00
4. Start the **weekly backfill** job (Mondays at 2 AM) to catch any newly available data
5. Launch the **web UI dashboard** at `http://127.0.0.1:5000`

### Individual Commands

#### Fetch Data Once
Fetch consumption data and store in the database:

```bash
# Default: last 7 days
python run.py fetch

# Specific date range
python run.py fetch --dates "last 30 days"
python run.py fetch --dates "last month"
```

Available date presets:
- `last 2 days`
- `last 7 days` (default)
- `last 30 days`
- `last month`
- `last 3 months`

#### Run Scheduler Only
Automatically fetch data at scheduled times:

```bash
# Fetch daily at 23:00 (default)
python run.py scheduler

# Fetch daily at 22:30
python run.py scheduler --hour 22 --minute 30
```

#### Backfill Missing Data
Fill in gaps in your consumption history (especially useful if recent data wasn't available):

```bash
# Backfill missing data from last 90 days
python run.py backfill

# Backfill specific date range
python run.py backfill --start 2026-01-01 --end 2026-03-31

# Backfill more date ranges per run
python run.py backfill --max 10

# All together
python run.py backfill --start 2026-01-01 --max 15
```

**How Backfill Works:**
- Automatically detects missing data in your history
- Retries fetches for dates that didn't have data yet
- Runs on startup when scheduler starts
- Runs weekly (Mondays at 2 AM) to catch newly available data
- Respects API rate limits by processing a limited number of ranges per run

#### Run Web UI Only
Start the interactive dashboard:

```bash
# Default: http://127.0.0.1:5000
python run.py web

# Custom host/port
python run.py web --host 0.0.0.0 --port 8000

# With debug mode
python run.py web --debug
```

**Supported Date Presets in Dashboard:**
The web UI displays data using these supported date ranges:
- `last 2 days`
- `last 7 days` (default)
- `last 30 days`
- `last month`
- `last 3 months`

### Original CLI Usage

The original command-line interface is still available:

```bash
python ecotricity.py

# Specific date range
python ecotricity.py --dates "last 7 days"
python ecotricity.py --dates "last month"
```

## Web Dashboard

The web dashboard provides interactive visualizations of your consumption data.

### URL
```
http://127.0.0.1:5000
```

### Features

1. **Summary Statistics**
   - Total consumption (last 30 days)
   - Daily average
   - Min/max consumption
   - 30-day trend (% change)

2. **Cost Analysis** (with 15% GST included)
   - Total cost for last 30 days
   - Daily average cost
   - Cost range (min/max daily cost)
   - Cost trends
   - Monthly cost breakdown table
   - All-time average costs

3. **Charts**
   - Time series line chart with trend line
   - Day-of-week bar chart
   - High/Low distribution (doughnut chart)

4. **Insights**
   - Peak consumption days
   - Day-of-week patterns
   - Usage stability analysis
   - Trend indicators
   - Monthly spending analysis

5. **Data Export**
   - Download as JSON
   - Download as CSV

### API Endpoints

- `GET /api/data` - Consumption data for last 30 days
- `GET /api/statistics` - Statistical summaries
- `GET /api/summary` - Overall summary (30 days + all time)
- `GET /api/daily-breakdown` - Average by day of week
- `GET /api/trends` - Trend calculations
- `GET /api/costs/statistics` - Cost statistics and trends (with GST)
- `GET /api/costs/daily` - Daily costs for last 30 days
- `GET /api/costs/monthly` - Monthly cost breakdown
- `GET /api/export/json` - Export all data as JSON
- `GET /api/export/csv` - Export all data as CSV

## Database

Consumption data is stored in SQLite database (`consumption.db`):

```
consumption.db
├── consumption table:
│   ├── id (primary key)
│   ├── date (unique)
│   ├── weekday
│   ├── value (kWh)
│   └── fetched_at (timestamp)
│
└── fetch_attempts table (for backfill tracking):
    ├── id (primary key)
    ├── date_requested
    ├── attempt_date
    ├── success (boolean)
    └── error_message
```

You can query this database directly or use the provided Python API.

## Data Collection Strategy

The system handles **incomplete historical data** through a multi-pronged approach:

### 1. **Daily Fetch**
- Runs daily (default 23:00) to capture current consumption
- Fetches last 7 days to handle any API delays
- Records successful fetches in the database

### 2. **Automatic Backfill on Startup**
- When scheduler starts, automatically backfills missing data from last 90 days
- Smart detection of date gaps in your history
- Prevents re-fetching already available data

### 3. **Weekly Backfill Job**
- Runs every Monday at 2 AM
- Catches any newly available historical data
- Handles cases where data becomes available after initial fetch failed

### 4. **Manual Backfill Command**
```bash
# Backfill any recent gaps
python run.py backfill

# Backfill specific date range
python run.py backfill --start 2026-01-01 --end 2026-06-30
```

### Why This Matters
Some utility APIs don't make data available immediately:
- Last 2-3 days may not have final readings
- Certain date ranges may require finalization
- Manual corrections from utility may appear later

The backfill system ensures you gradually capture all available data over time without manual intervention.

## Project Structure

```
ecotricity-fetchusage/
├── ecotricity.py          # Original CLI script
├── app.py                 # Flask web application
├── scheduler.py           # Background task scheduler
├── database.py            # Database operations
├── config.py              # Configuration management
├── run.py                 # Main entry point with subcommands
├── consumption.db         # SQLite database (created on first run)
├── config.json            # Configuration file (auto-generated)
├── requirements.txt       # Python dependencies
├── templates/
│   └── index.html        # Dashboard HTML/CSS/JS
└── README.md             # This file
```

## Troubleshooting

### "Credentials not found" Error
- Ensure `ECOTRICITY_LOGIN` and `ECOTRICITY_PASSWORD` are set
- Create a `.env` file with your credentials
- Or set environment variables before running

### "No metering data available" (HTTP 503)
- The date range doesn't contain any data in your account
- Check the Ecotricity portal for available date ranges
- Try a different date range

### Login Failed
- Verify your account number and password are correct
- Check that your Ecotricity account is active
- Your account may have changed (check portal)

### Web UI won't start
- Check if port 5000 is already in use: `python run.py web --port 8000`
- Ensure Flask is installed: `pip install flask`
- Check error output for more details

### Scheduler stops unexpectedly
- Check the error output in the terminal
- Ensure credentials remain valid
- The session may have expired; restart the scheduler
- Check your internet connection

## Monitoring

### Scheduler Status
The scheduler logs all fetch operations to the console with timestamps. Look for:
- `Starting scheduled fetch...` - Fetch started
- `✓ Fetched and stored X records` - Successful fetch
- `✗ Scheduled fetch failed` - Error occurred

### Database Status
Check the database for latest data:

```python
from database import get_last_fetch_date, get_data_range

# Get most recent data date
last_date = get_last_fetch_date()
print(f"Last data: {last_date}")

# Get full date range
start, end = get_data_range()
print(f"Data range: {start} to {end}")
```

## API Details

- **Portal**: https://portal.ecotricity.co.nz/powercommerce/eco/fo/portal
- **Data Endpoint**: `/analysis/valueRequest`
- **Supported dateTypes**: 
  - `DAY` - Single day only, returns HALF_HOUR granularity (30-minute intervals)
  - `WEEK` - 1-7 day ranges, returns DAY granularity
  - `MONTH` - Any date range, returns DAY granularity
- **Default Granularity**: DAY (daily consumption) for ranges over 1 day
- **Metric**: `POWER_ACTIVE_PURCHASE_CONSUMPTION`
- **Timezone**: Pacific/Auckland

## License

[Add license information here]

## Contributing

[Add contribution guidelines here]
