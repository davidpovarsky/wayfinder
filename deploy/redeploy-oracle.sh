#!/usr/bin/env bash
# Deploy the reviewed Wayfinder Israel branch on the existing Oracle server.
# Usage: sudo -u ubuntu bash /home/ubuntu/wayfinder-israel/deploy/redeploy-oracle.sh
set -euo pipefail
ROOT=/home/ubuntu/wayfinder-israel
BRANCH=feature/israel-mot-telegram-mapbox
cd "$ROOT"
test -f "$ROOT/.env" || { echo "Missing private .env; aborting" >&2; exit 2; }
old=$(git rev-parse HEAD)
git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH"
echo "Deploying commit $(git rev-parse --short HEAD) (previous $old)"
python3 -m unittest discover -s israel-compat/tests -p 'test_server.py' -q
if git diff --name-only "$old" HEAD | grep -q '^package-lock.json$'; then
  npm ci --no-audit --no-fund
fi
NODE_OPTIONS=--max-old-space-size=5120 npm run check
NODE_OPTIONS=--max-old-space-size=5120 npm run build
sudo systemctl restart wayfinder-oba-israel.service wayfinder-israel.service
for i in 1 2 3 4 5 6; do
  if curl -fsS --max-time 8 http://127.0.0.1:8770/healthz >/dev/null && curl -fsS --max-time 8 http://127.0.0.1:8771/ >/dev/null; then break; fi
  sleep 2
done
curl -fsS --max-time 10 http://127.0.0.1:8770/healthz >/dev/null
curl -fsS --max-time 10 http://127.0.0.1:8771/ >/dev/null
echo "Both Wayfinder Israel services healthy, deployed commit $(git rev-parse --short HEAD)"
