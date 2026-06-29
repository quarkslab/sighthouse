#!/bin/sh

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
PIPELINE_DB="$SCRIPT_DIR/../pipeline/data/postgres"

set -a
. ${SCRIPT_DIR}/../../.env
. ${SCRIPT_DIR}/../../.version
set +a

# Define paths for the key and certificate
KEY_PATH="nginx/certs/server.key"
CRT_PATH="nginx/certs/server.crt"

mkdir -p "$SCRIPT_DIR/data/frontend"
mkdir -p "$SCRIPT_DIR/data/redis"
mkdir -p "$SCRIPT_DIR/data/rustfs"

# Copy pipeline database if one exist
if [ -d "$PIPELINE_DB" ]; then
  cp -r "$PIPELINE_DB" "$SCRIPT_DIR/data/bsim"
else
  mkdir -p "$SCRIPT_DIR/data/bsim"
fi

# Generate certificate if none exist
if [ ! -f "$KEY_PATH" ] && [ ! -f "$CRT_PATH" ]; then
  echo "No certificates found under $KEY_PATH/$CRT_PATH."
  if ! command -v openssl >/dev/null 2>&1; then
    echo "OpenSSL is not installed. Please install OpenSSL first or provide your own certificates."
    exit 1
  fi
  echo "Generating self-signed certificates."
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$KEY_PATH" \
    -out "$CRT_PATH" \
    -subj "/CN=example.com" 2>/dev/null
  echo ""
  echo "#############################################"
  echo "#                                           #"
  echo "#                 WARNING:                  #"
  echo "#  These certificates are not suitable for  #"
  echo "#  production use! Self-signed are subject  #"
  echo "#  to Man-In-the-Middle Attack. Use only    #"
  echo "#  for local testing.                       #"
  echo "#                                           #"
  echo "#############################################"
  echo ""
else
  echo "Found certificates under $KEY_PATH/$CRT_PATH."
fi

chown -R 1000:1000 "$SCRIPT_DIR/data"

echo "Starting docker compose file."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d
