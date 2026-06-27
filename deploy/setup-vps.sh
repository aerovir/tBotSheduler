#!/bin/bash
# tBotSheduler — VPS setup script (Debian/Ubuntu)
# Run as root

set -e

echo "=== tBotSheduler VPS Setup ==="

# Config
APP_DIR="/opt/tBotSheduler"
APP_USER="tbot"
REPO_URL="https://github.com/aerovir/tBotSheduler.git"

# 1. System updates
echo "[1/8] Updating system..."
apt update && apt upgrade -y

# 2. Install dependencies
echo "[2/8] Installing dependencies..."
apt install -y python3 python3-venv python3-pip git sqlite3 fail2ban

# 3. Create non-root user
echo "[3/8] Creating user '$APP_USER'..."
id "$APP_USER" 2>/dev/null || useradd -m -s /bin/bash "$APP_USER"

# 4. Clone repo
echo "[4/8] Cloning repository..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# 5. Python venv + deps
echo "[5/8] Setting up Python environment..."
cd "$APP_DIR"
sudo -u "$APP_USER" python3 -m venv venv
sudo -u "$APP_USER" ./venv/bin/pip install -r requirements.txt

# 6. .env
echo "[6/8] Configuration..."
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" << EOF
BOT_TOKEN=your_bot_token_here
CHANNEL_USERNAME=@your_channel
WEB_APP_URL=https://your-domain.com/webapp
DATABASE_URL=sqlite+aiosqlite:///${APP_DIR}/bot.db
LOG_LEVEL=INFO
EOF
    echo "  → Edit $APP_DIR/.env with your settings"
fi

# 7. Install systemd service
echo "[7/8] Installing systemd service..."
cp "$APP_DIR/deploy/tbotsheduler.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable tbotsheduler
systemctl start tbotsheduler

# 8. Setup fail2ban for SSH
echo "[8/8] Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 86400
EOF
systemctl restart fail2ban

# Setup cron for backups
(crontab -l 2>/dev/null; echo "0 3 * * * $APP_DIR/deploy/backup.sh $APP_DIR/bot.db $APP_DIR/backups") | crontab -

echo ""
echo "=== Setup complete! ==="
echo "Edit: $APP_DIR/.env"
echo "Start: systemctl start tbotsheduler"
echo "Logs: journalctl -u tbotsheduler -f"
echo "Backups: daily at 3am to $APP_DIR/backups/"
