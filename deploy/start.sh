#!/usr/bin/env bash
# Runs the three processes of the LiveIQ container. If any dies, the container exits
# (Hugging Face restarts it) rather than limping along half-alive.
set -u

cd /app/backend
uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='*' &
API_PID=$!

cd /app/web
PORT=3000 HOSTNAME=127.0.0.1 node server.js &
WEB_PID=$!

nginx -c /app/nginx.conf -g 'daemon off;' &
NGINX_PID=$!

trap 'kill $API_PID $WEB_PID $NGINX_PID 2>/dev/null' TERM INT
wait -n $API_PID $WEB_PID $NGINX_PID
code=$?
echo "A LiveIQ process exited (code $code) — shutting the container down" >&2
kill $API_PID $WEB_PID $NGINX_PID 2>/dev/null
exit 1
