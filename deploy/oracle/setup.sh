#!/usr/bin/env bash
# One-shot setup for an Oracle Cloud always-free VM (Ubuntu 22.04 / 24.04, Ampere A1 or x86).
# Run once as the default user:  curl -fsSL https://raw.githubusercontent.com/Shiripatel/delta-desk/main/deploy/oracle/setup.sh | bash
# Installs Docker, opens ports 80/443 in the VM firewall, clones the repository to /opt/delta-desk,
# writes a starter .env, builds and starts the app behind Caddy, and installs the pull-based auto-deploy.
set -euo pipefail

REPO="https://github.com/Shiripatel/delta-desk.git"
DIR="/opt/delta-desk"

echo "== packages"
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl git gnupg >/dev/null

echo "== docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER" || true

echo "== firewall: allow 80 and 443 (Oracle images ship an iptables policy that drops everything else)"
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo apt-get install -y -qq iptables-persistent >/dev/null 2>&1 || true
sudo netfilter-persistent save >/dev/null 2>&1 || true

echo "== code"
if [ ! -d "$DIR/.git" ]; then
  sudo mkdir -p "$DIR" && sudo chown "$USER":"$USER" "$DIR"
  git clone "$REPO" "$DIR"
fi
cd "$DIR"
git pull --ff-only

echo "== environment"
if [ ! -f .env ]; then
  cat > .env <<EOF
# Delta Desk on Oracle: edit and run  deploy/oracle/deploy.sh  to apply
DD_QUOTES=yahoo
DD_FEED=synthetic
DD_MODE=paper
PYTHONUNBUFFERED=1
DD_ADMIN_TOKEN=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)
DD_TRAFFIC_SALT=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)
TELEGRAM_BOT_TOKEN=
DD_OWNER_CHAT=
GROQ_API_KEY=
DATABASE_URL=
# domain for HTTPS once DNS points here, e.g. desk.example.com ; leave :80 to serve on the IP
SITE_ADDRESS=:80
EOF
  echo "wrote $DIR/.env (fill the secrets later)"
fi
mkdir -p data

echo "== build and start"
sudo docker compose -f deploy/oracle/docker-compose.yml --env-file .env up -d --build

echo "== auto-deploy every 5 minutes (pulls main; rebuilds only when the commit changed)"
chmod +x deploy/oracle/deploy.sh
( crontab -l 2>/dev/null | grep -v 'deploy/oracle/deploy.sh' ; echo "*/5 * * * * cd $DIR && ./deploy/oracle/deploy.sh >> /var/tmp/delta-desk-deploy.log 2>&1" ) | crontab -

IP=$(curl -s -m 5 https://api.ipify.org || echo "<public-ip>")
echo
echo "Delta Desk is starting. In about two minutes open:  http://$IP/"
echo "Health:  curl -s http://127.0.0.1/healthz"
echo "Logs:    sudo docker compose -f $DIR/deploy/oracle/docker-compose.yml logs -f app"
echo "Secrets: nano $DIR/.env  then  $DIR/deploy/oracle/deploy.sh"
