#!/usr/bin/env bash
# Pull-based deploy: fetch main, rebuild and restart only when the commit changed (or when forced with --force).
# Installed by setup.sh as a five-minute cron; also run it by hand after editing .env:  ./deploy/oracle/deploy.sh --force
set -euo pipefail
cd "$(dirname "$0")/../.."
before=$(git rev-parse HEAD)
git fetch -q origin main
git reset -q --hard origin/main
after=$(git rev-parse HEAD)
if [ "$before" != "$after" ] || [ "${1:-}" = "--force" ]; then
  echo "$(date -Is) deploying $after"
  sudo docker compose -f deploy/oracle/docker-compose.yml --env-file .env up -d --build --remove-orphans
  sudo docker image prune -f >/dev/null 2>&1 || true
fi
