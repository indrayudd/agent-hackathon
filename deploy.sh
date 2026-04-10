#!/bin/bash
set -e

DOMAIN="agenticeda.duckdns.org"
EMAIL="indro@umd.edu"

echo "=== AgenticEDA Deployment ==="

# Step 1: Start with HTTP-only nginx (so certbot can do its challenge)
echo "[1/4] Starting services with HTTP..."
cp nginx/nginx-http-only.conf nginx/active.conf
docker compose up -d --build

echo "Waiting for services to start..."
sleep 10

# Step 2: Get SSL cert
echo "[2/4] Requesting SSL certificate from Let's Encrypt..."
docker compose run --rm certbot certonly \
    --webroot -w /var/www/certbot \
    --email "$EMAIL" --agree-tos --no-eff-email \
    -d "$DOMAIN"

# Step 3: Switch to HTTPS nginx config
echo "[3/4] Switching to HTTPS..."
cp nginx/nginx.conf nginx/active.conf
docker compose restart nginx

echo "[4/4] Done!"
echo ""
echo "  HTTP:  http://$DOMAIN  (redirects to HTTPS)"
echo "  HTTPS: https://$DOMAIN"
echo ""
echo "Certbot will auto-renew certificates every 12 hours."
