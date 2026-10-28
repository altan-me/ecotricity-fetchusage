# Build stage
FROM python:3.15-slim AS builder

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.15-slim

WORKDIR /app

# Use shell for CMD to expand environment variables
SHELL ["/bin/sh", "-c"]

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application code
COPY . .

# Create non-root user for security and install packages system-wide
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Copy dependencies from builder (pip packages)
COPY --from=builder --chown=appuser:appuser /usr/local/lib/python3.15/site-packages /usr/local/lib/python3.15/site-packages
COPY --from=builder --chown=appuser:appuser /usr/local/bin /usr/local/bin

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health', timeout=5)" || exit 1

# Environment variables with defaults
ENV SCHEDULER_HOUR=23 \
    SCHEDULER_MINUTE=0 \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000

# Run both scheduler and web UI
CMD python run.py all --hour $SCHEDULER_HOUR --minute $SCHEDULER_MINUTE --host $FLASK_HOST --port $FLASK_PORT
