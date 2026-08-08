#!/bin/sh
set -eu

mkdir -p "${DATA_DIR:-/data}/assets"
if [ ! -f "${DATA_DIR:-/data}/assets/ottawa-logo.png" ] && [ -f /app/assets/ottawa-logo.png ]; then
  cp /app/assets/ottawa-logo.png "${DATA_DIR:-/data}/assets/ottawa-logo.png"
fi
chown -R appuser:appuser "${DATA_DIR:-/data}"
if [ ! -f "${DATA_DIR:-/data}/sources.json" ]; then
  cp /app/sources.example.json "${DATA_DIR:-/data}/sources.json"
fi
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/app.conf
