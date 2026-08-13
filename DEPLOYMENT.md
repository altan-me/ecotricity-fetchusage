# Deployment Guide

## Overview

Your Ecotricity consumption tracker is now configured for both local development and production deployment using Docker.

## 📦 What You Have

### Application Stack
- **Backend**: Python 3.11 with Flask, APScheduler
- **Database**: SQLite (persistent)
- **Frontend**: Interactive web dashboard with charts
- **Scheduler**: Automatic daily fetches + weekly backfill

### Deployment Options
1. **Local Development** - Run with docker-compose
2. **Production with Docker** - Self-hosted container
3. **GitHub Actions** - Automated CI/CD with auto-publish

## 🚀 Quick Deployment Options

### Option 1: Local Development (Recommended for Testing)

```bash
# 1. Clone the repository
cd ecotricity-fetchusage

# 2. Create .env file
cat > .env << EOF
ECOTRICITY_LOGIN=your_account_number
ECOTRICITY_PASSWORD=your_password
SCHEDULER_HOUR=23
SCHEDULER_MINUTE=0
EOF

# 3. Start with docker-compose
docker-compose up -d

# 4. View logs
docker-compose logs -f

# 5. Access web UI
# Open browser to http://localhost:5000

# 6. Stop when done
docker-compose down
```

**Time to deployment: 2-3 minutes**

### Option 2: Docker Manual Deployment (Production Ready)

```bash
# 1. Build the image
docker build -t ecotricity:v1.0 .

# 2. Run the container
docker run -d \
  --name ecotricity-prod \
  --restart always \
  -p 5000:5000 \
  -e ECOTRICITY_LOGIN="your_account" \
  -e ECOTRICITY_PASSWORD="your_password" \
  -e SCHEDULER_HOUR=23 \
  -v ecotricity_data:/app \
  ecotricity:v1.0

# 3. Verify it's running
docker ps
docker logs ecotricity-prod

# 4. Access web UI
# Open browser to http://localhost:5000

# 5. Monitor health
docker inspect ecotricity-prod | grep -A 10 Health
```

**Features**: Full control, auto-restart, persistent storage

### Option 3: GitHub Actions Auto-Deploy (Recommended for CI/CD)

```bash
# 1. Push to GitHub
git add .
git commit -m "Add Docker and GitHub Actions support"
git push origin main

# 2. GitHub Actions automatically:
#    - Builds Docker image
#    - Publishes to GitHub Container Registry (GHCR)
#    - Tags with branch/version/SHA

# 3. View build at:
# https://github.com/YOUR_USERNAME/ecotricity-fetchusage/actions

# 4. Pull and run published image:
docker login ghcr.io
docker pull ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:main
docker run -d \
  -p 5000:5000 \
  -e ECOTRICITY_LOGIN="your_account" \
  -e ECOTRICITY_PASSWORD="your_password" \
  -v ecotricity_data:/app \
  ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:main
```

**Features**: Automated builds, semantic versioning, container registry

## 📋 Deployment Checklist

### Before Deployment
- [ ] .env file created with valid credentials
- [ ] Tested locally with docker-compose
- [ ] Database (consumption.db) backed up if upgrading
- [ ] Port 5000 available (or configure alternative)
- [ ] Docker Engine running

### After Deployment
- [ ] Container is running: `docker ps`
- [ ] Health check passing: `curl http://localhost:5000/health`
- [ ] Web UI accessible: `http://localhost:5000`
- [ ] Logs show no errors: `docker-compose logs`
- [ ] Database persists: `ls -la /app/consumption.db`

### Ongoing Monitoring
- [ ] Monitor health status daily
- [ ] Check scheduler logs for fetch errors
- [ ] Backup database weekly
- [ ] Update image monthly

## 🔧 Configuration Reference

### Environment Variables

| Variable | Type | Default | Required | Notes |
|----------|------|---------|----------|-------|
| ECOTRICITY_LOGIN | String | - | Yes | Your account number |
| ECOTRICITY_PASSWORD | String | - | Yes | Your password |
| SCHEDULER_HOUR | Int 0-23 | 23 | No | Daily fetch time |
| SCHEDULER_MINUTE | Int 0-59 | 0 | No | Daily fetch minute |
| FLASK_HOST | String | 0.0.0.0 | No | Web server host |
| FLASK_PORT | Int | 5000 | No | Web server port |

### Ports

| Port | Service | Protocol |
|------|---------|----------|
| 5000 | Web UI + API | HTTP |

### Volumes

| Volume | Mount | Purpose |
|--------|-------|---------|
| ecotricity_data | /app | Persistent database storage |

## 📊 Database Management

### Backup Database
```bash
# Local backup
docker-compose exec ecotricity cp consumption.db consumption.db.$(date +%Y%m%d)

# Extract to host machine
docker cp ecotricity-prod:/app/consumption.db ./consumption.db.backup
```

### Restore Database
```bash
# From docker-compose
docker-compose exec ecotricity mv consumption.db.backup consumption.db

# From host machine
docker cp consumption.db.backup ecotricity-prod:/app/consumption.db
```

### View Database Contents
```bash
# Summary
docker-compose exec ecotricity python -c "
from database import *
init_db()
data = get_all_consumption()
print(f'Records: {len(data)}')
print(f'Date range: {data[0][\"date\"]} to {data[-1][\"date\"]}' if data else 'No data')
"

# Export to CSV
docker-compose exec ecotricity python run.py fetch > /dev/null
curl http://localhost:5000/api/export/csv > consumption.csv
```

## 🚨 Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs ecotricity

# Common issues:
# - Credentials missing: Set ECOTRICITY_LOGIN and ECOTRICITY_PASSWORD
# - Port in use: Change FLASK_PORT or kill existing process
# - Permissions: Fix volume permissions with: docker-compose exec ecotricity chmod 777 /app
```

### No data in web UI

```bash
# Check if scheduler has run
docker-compose logs | grep fetch

# Manual fetch
docker-compose exec ecotricity python run.py fetch

# Check database
docker-compose exec ecotricity python run.py fetch --dates "last month"
```

### Web UI not accessible

```bash
# Verify container running
docker-compose ps

# Check port binding
docker-compose port ecotricity 5000

# Test from container
docker-compose exec ecotricity curl http://localhost:5000/health

# Check network
docker network ls
docker inspect ecotricity-fetchusage_default
```

### GitHub Actions build failing

```bash
# Check workflow logs
# https://github.com/YOUR_USERNAME/ecotricity-fetchusage/actions

# Common issues:
# - Invalid YAML syntax: Run: docker-compose config
# - Docker login failed: Check GitHub secrets
# - Out of disk space: Clean up old images: docker prune
```

## 🔄 Updates and Maintenance

### Update Application Code

```bash
# Pull latest
git pull origin main

# Rebuild image
docker-compose build

# Restart with new image
docker-compose down
docker-compose up -d
```

### Update From GitHub Container Registry

```bash
# Pull latest
docker pull ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:latest

# Stop old container
docker stop ecotricity-prod
docker rm ecotricity-prod

# Run new image
docker run -d \
  --name ecotricity-prod \
  --restart always \
  -p 5000:5000 \
  -e ECOTRICITY_LOGIN="..." \
  -e ECOTRICITY_PASSWORD="..." \
  -v ecotricity_data:/app \
  ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:latest
```

### Clean Up Old Images

```bash
# Remove unused images
docker image prune -a

# Remove all stopped containers
docker container prune

# Remove unused volumes
docker volume prune
```

## 📈 Performance Tuning

### Optimize for Low Resource Environments

```yaml
# docker-compose.yml additions for limited resources
services:
  ecotricity:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M
        reservations:
          cpus: '0.25'
          memory: 128M
```

### Optimize for High Traffic

```bash
# Increase Flask workers
docker run -d \
  --name ecotricity \
  -p 5000:5000 \
  -e WORKERS=4 \
  ecotricity:latest

# Use gunicorn instead of Flask dev server (for production)
```

## 🔐 Security Best Practices

- ✅ Runs as non-root user (appuser, UID 1000)
- ✅ Credentials in .env (not in image)
- ✅ Health checks enabled
- ✅ Read-only volumes where possible
- ⚠️ TODO: Add network segmentation for multi-container setup
- ⚠️ TODO: Add rate limiting for API endpoints
- ⚠️ TODO: Add authentication for web UI (optional)

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [DOCKER.md](DOCKER.md) | Complete Docker reference |
| [QUICKSTART_DOCKER.md](QUICKSTART_DOCKER.md) | Quick start guide |
| [README.md](README.md) | Application overview |
| [DOCKER_SETUP_SUMMARY.md](DOCKER_SETUP_SUMMARY.md) | Setup summary |

## 🎯 Next Steps

1. **Choose deployment option** (local, manual, or GitHub Actions)
2. **Set up .env file** with your credentials
3. **Deploy and verify** the setup
4. **Monitor logs** for any issues
5. **Back up database** regularly
6. **Update documentation** with your deployment details

## 📞 Support

For issues:
1. Check logs: `docker-compose logs -f`
2. Review DOCKER.md troubleshooting section
3. Check GitHub Actions logs for CI/CD issues
4. Verify .env credentials are correct

---

**Deployment Options**: Local Dev | Manual Docker | GitHub Actions
**Container Registry**: Docker Hub | GitHub Container Registry (GHCR)
**Database**: SQLite (persistent volume)
**Scheduling**: APScheduler (daily + weekly)
