#!/bin/sh
set -eu

mkdir -p "${DATA_DIR:-/data}"
chown -R appuser:appuser "${DATA_DIR:-/data}"
if [ ! -f "${DATA_DIR:-/data}/sources.json" ]; then
  cp /app/sources.example.json "${DATA_DIR:-/data}/sources.json"
fi
exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
