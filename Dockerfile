FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY pyproject.toml .
COPY src/ ./src/

# Create data and logs directories
RUN mkdir -p /data /app/logs

# Default environment
ENV BOT_TOKEN=""
ENV DATABASE_URL="sqlite+aiosqlite:////data/bot.db"
ENV LOG_LEVEL="INFO"
ENV WEB_APP_URL=""

# Expose healthcheck port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run
CMD ["python3", "-m", "tbot_sheduler"]
