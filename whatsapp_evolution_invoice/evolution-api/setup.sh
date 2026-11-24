#!/usr/bin/env bash
# One-shot installer for Evolution API on the VPS.
# Usage:  cd evolution-api && bash setup.sh
set -euo pipefail

if [ ! -f .env ]; then
  cp .env.example .env
  API_KEY=$(openssl rand -hex 24)
  DB_PASS=$(openssl rand -hex 16)
  sed -i "s/CHANGE_ME_LONG_RANDOM_KEY/${API_KEY}/" .env
  sed -i "s/CHANGE_ME_DB_PASSWORD/${DB_PASS}/g" .env
  echo ">> .env created"
fi

docker compose pull
docker compose up -d

API_KEY=$(grep '^AUTHENTICATION_API_KEY=' .env | cut -d= -f2)
INSTANCE=${1:-odoo}

echo ">> waiting for API ..."
for i in $(seq 1 30); do
  curl -fs http://127.0.0.1:8080/ >/dev/null && break
  sleep 2
done

echo ">> creating instance '${INSTANCE}' (ignore 'already in use' errors on re-run)"
curl -s -X POST http://127.0.0.1:8080/instance/create \
  -H "apikey: ${API_KEY}" -H "Content-Type: application/json" \
  -d "{\"instanceName\":\"${INSTANCE}\",\"integration\":\"WHATSAPP-BAILEYS\",\"qrcode\":true}" \
  | head -c 300; echo

cat <<EOF

=========================================================
 Evolution API is running on 127.0.0.1:8080 (internal)
 API KEY  : ${API_KEY}
 INSTANCE : ${INSTANCE}

 Scan the QR (one time):
   1) From your PC:  ssh -L 8080:127.0.0.1:8080 root@YOUR_VPS_IP
   2) Open:          http://localhost:8080/manager
   3) Login with the API KEY above -> instance '${INSTANCE}' -> Get QR Code
   4) WhatsApp on phone -> Linked devices -> Link a device -> scan

 Connect Odoo container to the same network:
   docker network connect evolution-net <odoo_container_name>
 Then in Odoo settings use URL: http://evolution_api:8080
=========================================================
EOF
