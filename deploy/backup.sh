#!/bin/bash
# Daily backup script for tBotSheduler SQLite database
# Usage: ./backup.sh [db_path] [backup_dir]

DB_PATH="${1:-/opt/tBotSheduler/bot.db}"
BACKUP_DIR="${2:-/opt/tBotSheduler/backups}"

# Create backup dir
mkdir -p "$BACKUP_DIR"

# Backup with date
DATE=$(date +%Y%m%d_%H%M%S)
cp "$DB_PATH" "$BACKUP_DIR/bot-$DATE.db"

# Compress
gzip "$BACKUP_DIR/bot-$DATE.db" 2>/dev/null || true

# Remove backups older than 7 days
find "$BACKUP_DIR" -name "bot-*.db.gz" -mtime +7 -delete

echo "Backup saved: bot-$DATE.db.gz"
echo "Total backups: $(find "$BACKUP_DIR" -name 'bot-*.db.gz' | wc -l)"
