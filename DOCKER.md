# Docker Setup & GitHub Actions

## Quick Start with Docker Compose

### Prerequisites
- Docker and Docker Compose installed
- `.env` file with Ecotricity credentials

### Running with Docker Compose

1. **Create/update your `.env` file:**
```bash
ECOTRICITY_LOGIN=your_account_number
ECOTRICITY_PASSWORD=your_password
SCHEDULER_HOUR=23
SCHEDULER_MINUTE=0
```

2. **Build and start the container:**
```bash
docker-compose up --build
```

3. **Access the web UI:**
Navigate to `http://localhost:5000` in your browser

4. **View logs:**
```bash
docker-compose logs -f
```

5. **Stop the container:**
```bash
docker-compose down
```

### Docker Compose Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ECOTRICITY_LOGIN` | Required | Your Ecotricity account number |
| `ECOTRICITY_PASSWORD` | Required | Your Ecotricity password |
| `SCHEDULER_HOUR` | 23 | Hour for daily fetch (0-23) |
| `SCHEDULER_MINUTE` | 0 | Minute for daily fetch (0-59) |
| `FLASK_HOST` | 0.0.0.0 | Web server host (0.0.0.0 for docker) |
| `FLASK_PORT` | 5000 | Web server port |

### Docker Compose Services

The compose file defines:
- **ecotricity** service running both scheduler and web UI
- **ecotricity_data** volume for persistent database storage
- Health checks every 30 seconds
- Auto-restart policy

## Building Docker Image Manually

### Build the image:
```bash
docker build -t ecotricity-fetchusage:latest .
```

### Run the container:
```bash
docker run -d \
  --name ecotricity \
  -p 5000:5000 \
  -e ECOTRICITY_LOGIN="your_login" \
  -e ECOTRICITY_PASSWORD="your_password" \
  -e SCHEDULER_HOUR=23 \
  -v ecotricity_data:/app \
  ecotricity-fetchusage:latest
```

### View logs:
```bash
docker logs -f ecotricity
```

### Access the web UI:
Navigate to `http://localhost:5000`

## GitHub Actions CI/CD

The `.github/workflows/docker-build.yml` workflow automatically:
- Builds Docker image on pushes to `main`/`master` branches
- Builds on pull requests (for validation only)
- Creates and pushes images on tags (e.g., `v1.0.0`)
- Publishes to GitHub Container Registry (GHCR)
- Uses cache for faster builds

### Workflow Triggers

**On Commits:**
- Push to `main` or `master` → publishes `latest` + branch name
- Tag `v*` → publishes semantic version tags

**On Pull Requests:**
- Validates build (doesn't push)

### Generated Image Tags

For a commit to `main`:
- `ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:main`
- `ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:latest`
- `ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:sha-<commit_hash>`

For a tag `v1.2.3`:
- `ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:1.2.3`
- `ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:1.2`
- `ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:latest`

### Using Published Images

Pull and run from GHCR:
```bash
docker pull ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:latest
docker run -d \
  -p 5000:5000 \
  -e ECOTRICITY_LOGIN="your_login" \
  -e ECOTRICITY_PASSWORD="your_password" \
  -v ecotricity_data:/app \
  ghcr.io/YOUR_USERNAME/ecotricity-fetchusage:latest
```

### Requirements for GitHub Actions

- GitHub Actions enabled on your repository
- GHCR access (automatic with `secrets.GITHUB_TOKEN`)
- No additional secrets needed for public pushes

## Health Checks

Both Docker and docker-compose include health checks:
- Endpoint: `GET /health`
- Interval: Every 30 seconds
- Timeout: 10 seconds
- Start period: 5 seconds (allows startup)
- Retries: 3 failures to mark unhealthy

Check container health:
```bash
docker ps -a  # Shows health status
docker inspect ecotricity | grep -A 10 '"Health"'
```

## Database Persistence

The SQLite database (`consumption.db`) is automatically persisted in the Docker volume:
- **Local dev:** Volume mount `ecotricity_data` persists between container restarts
- **Stop/remove container:** `docker-compose down` preserves database
- **Full cleanup:** `docker-compose down -v` removes volume and data

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs ecotricity

# Verify credentials are set
docker-compose config | grep ECOTRICITY
```

### Web UI not accessible
```bash
# Ensure port 5000 is available
netstat -ano | grep 5000  # Windows
lsof -i :5000              # macOS/Linux

# Verify container is running
docker ps | grep ecotricity
```

### Database file permissions
If using non-standard volumes, ensure `appuser` (UID 1000) can write:
```bash
docker exec ecotricity ls -la /app/consumption.db
```

### GitHub Actions build failing
- Check workflow logs in repository Settings → Actions
- Verify `.github/workflows/docker-build.yml` syntax
- Ensure repository has GitHub Actions enabled

## Advanced Configuration

### Custom Dockerfile with environment
Create an `.env.docker` file and use in docker-compose:
```yaml
env_file:
  - .env
  - .env.docker
```

### Multi-stage builds
The Dockerfile uses multi-stage builds to minimize image size:
- Builder stage: Installs Python dependencies
- Runtime stage: Minimal Python environment + app code
- Results in ~300MB image (vs 800MB+ without optimization)

### Container networking
For connecting with other services, use docker-compose networks:
```yaml
networks:
  - ecotricity-net
```

See `docker-compose.yml` for current configuration.
