#!/bin/sh
# Fix volume permissions at runtime (Railway mounts volumes as root)
if [ -d /app/output ] && [ ! -w /app/output ]; then
    echo "Fixing /app/output permissions..."
    chmod 777 /app/output 2>/dev/null || true
fi
# Fix catalog volume permissions if configured
if [ -n "$CATALOG_VOLUME_DIR" ] && [ -d "$CATALOG_VOLUME_DIR" ]; then
    echo "Fixing catalog volume permissions..."
    chmod 777 "$CATALOG_VOLUME_DIR" 2>/dev/null || true
fi
exec "$@"
