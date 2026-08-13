# Quick Start Guide - Docker

## 🚀 Get Running in 2 Minutes

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone and navigate to directory
cd ecotricity-fetchusage

# 2. Create .env file with your credentials
cat > .env << EOF
ECOTRICITY_LOGIN=your_account_number
ECOTRICITY_PASSWORD=your_password
EOF

# 3. Start the container
docker-compose up -d

# 4. Open in browser
# Navigate to http://localhost:5000
```

**That's it!** The scheduler will automatically fetch data daily at 11 PM (or your configured time).

### Option 2: Docker CLI

```bash
# Build
docker build -t ecotricity .

# Run
docker run -d \
  --name ecotricity \
  -p 5000:5000 \
  -e ECOTRICITY_LOGIN="your_account_number" \
  -e ECOTRICITY_PASSWORD="your_password" \
  -v ecotricity_data:/app \
  ecotricity:latest

# Access at http://localhost:5000
```

## 📋 Configuration

### Custom Scheduler Time

Edit `.env` or pass environment variables:

```bash
# Start fetch at 2 PM daily (14:00)
docker-compose -e SCHEDULER_HOUR=14 -e SCHEDULER_MINUTE=0 up
```

Or add to `.env`:
```
SCHEDULER_HOUR=14
SCHEDULER_MINUTE=0
```

### Custom Port

```bash
# Run on port 8000 instead
docker-compose down
sed -i 's/"5000:5000"/"8000:5000"/g' docker-compose.yml
docker-compose up -d
# Access at http://localhost:8000
```

## 📊 Using the Dashboard

Once running, the web UI shows:
- **Last 30 days consumption** - Line chart with trend
- **Day-of-week analysis** - Which days use most power
- **High/Low distribution** - Peak usage patterns
- **Daily costs** - Cost breakdown per day
- **Monthly summary** - Total usage and cost by month
- **Cost statistics** - Total, average, and trend analysis

All data is automatically updated as the scheduler fetches new information.

## 🛠️ Common Tasks

### View Logs

```bash
# All logs
docker-compose logs

# Follow in real-time
docker-compose logs -f

# Last 20 lines
docker-compose logs --tail=20

# Scheduler only
docker-compose logs -f ecotricity | grep -i "scheduler"
```

### Manually Trigger Fetch

```bash
# One-time fetch of last 7 days
docker-compose exec ecotricity python run.py fetch

# Fetch specific date range
docker-compose exec ecotricity python run.py fetch --dates "last month"

# Backfill missing data
docker-compose exec ecotricity python run.py backfill
```

### Check Database

```bash
# List database files
docker-compose exec ecotricity ls -lah *.db

# Get data summary
docker-compose exec ecotricity python -c "
from database import *
init_db()
all_data = get_all_consumption()
print(f'Total records: {len(all_data)}')
print(f'Date range: {all_data[0]["date"]} to {all_data[-1]["date"]}')
print(f'Total consumption: {sum(r["value"] for r in all_data):.2f} kWh')
"
```

### Check Container Health

```bash
# View health status
docker-compose ps

# Check detailed health info
docker inspect ecotricity | grep -A 10 '"Health"'
```

### Stop and Clean Up

```bash
# Stop container (keep data)
docker-compose down

# Stop and remove everything (including database!)
docker-compose down -v

# Remove image
docker image rm ecotricity:latest
```

## 🔗 URLs and Endpoints

| URL | Purpose |
|-----|---------|
| `http://localhost:5000` | Main dashboard |
| `http://localhost:5000/health` | Health check |
| `http://localhost:5000/api/data` | Consumption data (JSON) |
| `http://localhost:5000/api/summary` | Statistical summary |
| `http://localhost:5000/api/costs/statistics` | Cost analytics |
| `http://localhost:5000/api/export/json` | Export all data as JSON |
| `http://localhost:5000/api/export/csv` | Export as CSV |

## 🐛 Troubleshooting

### Container won't start

Check the logs:
```bash
docker-compose logs
```

Look for:
- **"Credentials not found"** → Set `ECOTRICITY_LOGIN` and `ECOTRICITY_PASSWORD` in `.env`
- **"Connection refused"** → Docker daemon not running
- **"Port 5000 already in use"** → Change port in `docker-compose.yml`

### Can't connect to web UI

```bash
# Verify container is running
docker-compose ps

# Check if port 5000 is listening
# Windows:
netstat -ano | findstr :5000
# macOS/Linux:
lsof -i :5000

# Try accessing from inside container
docker-compose exec ecotricity curl http://localhost:5000
```

### Database permission errors

The container runs as unprivileged user `appuser` (UID 1000). If you get permission errors:

```bash
# Check file permissions
docker-compose exec ecotricity ls -la /app/consumption.db

# Fix permissions
docker-compose exec ecotricity chmod 666 /app/consumption.db
```

### No data showing in dashboard

```bash
# Check if scheduler has run
docker-compose logs | grep -i fetch

# Manually trigger a fetch
docker-compose exec ecotricity python run.py fetch

# Check database has data
docker-compose exec ecotricity python -c "
from database import get_all_consumption
data = get_all_consumption()
print(f'Records in database: {len(data)}')
if data:
    print(f'Latest: {data[-1]}')
"
```

## 📚 More Information

- [Full Docker Setup Guide](DOCKER.md)
- [Application README](README.md)
- [Configuration Details](README.md#configuration)

## 💡 Tips

1. **Always backup your database** before updating:
   ```bash
   docker-compose exec ecotricity cp consumption.db consumption.db.backup
   ```

2. **Use named volumes** for persistent data:
   ```bash
   docker volume ls  # See all volumes
   docker volume inspect ecotricity_data  # Check volume details
   ```

3. **Check the health regularly**:
   ```bash
   docker-compose ps  # Green = healthy, yellow = starting, red = unhealthy
   ```

4. **Update image regularly**:
   ```bash
   docker pull ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:latest
   docker-compose pull
   docker-compose up -d
   ```
