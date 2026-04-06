#!/bin/sh
# Fix volume permissions at runtime (Railway mounts volumes as root)
if [ -d /app/output ] && [ ! -w /app/output ]; then
    echo "Fixing /app/output permissions..."
    chmod 777 /app/output 2>/dev/null || true
fi
exec "$@"
