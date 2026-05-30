#!/bin/bash
set -e

echo "Starting custom Cloud Run Odoo wrapper..."

# 1. Google Cloud Run passes the required HTTP listening port via the PORT env var.
# We save this to HTTP_PORT. If not set, default to 8069.
HTTP_PORT=${PORT:-8069}

# 2. Odoo's official entrypoint script uses the 'PORT' env var to define the
# PostgreSQL database port. We must re-assign PORT to the actual DB port (e.g. 5432)
# so the official entrypoint connects to the database correctly instead of trying
# to connect to the HTTP port.
export PORT=5432

# 3. Re-export standard DB connection variables in case they were provided
# via custom env vars (like DB_HOST, DB_USER).
export HOST=${DB_HOST:-$HOST}
export USER=${DB_USER:-$USER}
export PASSWORD=${DB_PASSWORD:-$PASSWORD}

echo "Configured Web HTTP Port: $HTTP_PORT"
echo "Configured DB Host: $HOST"
echo "Configured DB Port: $PORT"

# 4. Call the official Odoo entrypoint script.
# We pass --http-port so Odoo listens on the Cloud Run port.
# We pass --proxy-mode so Odoo handles HTTPS redirects and cookies properly behind the Cloud Run load balancer.
exec /entrypoint.sh odoo --http-port="$HTTP_PORT" --proxy-mode "$@"
