#!/usr/bin/env bash
# Prints the NAME / VALUE pairs to paste into Hugging Face → Space → Settings → "Variables and secrets".
# Run it LOCALLY in your own terminal (it reads backend/.env on your machine; nothing is sent anywhere):
#     bash deploy/print_hf_secrets.sh
# Tip: pipe to your clipboard one key at a time, e.g.  bash deploy/print_hf_secrets.sh | grep '^POSTGRES_URL' | cut -d= -f2- | pbcopy
set -euo pipefail
ENV_FILE="$(dirname "$0")/../backend/.env"
[ -f "$ENV_FILE" ] || { echo "backend/.env not found"; exit 1; }

get() { awk -F= -v k="$1" '{kk=$1; gsub(/ /,"",kk)} kk==k {v=$0; sub(/^[^=]*=[ ]*/,"",v); gsub(/^["'"'"']|["'"'"']$/,"",v); print v; exit}' "$ENV_FILE"; }

echo "================ SECRETS (Settings → New secret) ================"
echo "--- REQUIRED"
for k in POSTGRES_URL POSTGRES_SYNC_URL; do echo "$k=$(get $k)"; done
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')   # <- NEW strong value generated now; use the same one everywhere you want sessions to be valid"
echo "--- RECOMMENDED (features degrade gracefully without them)"
for k in GROQ_API_KEY LASTFM_API_KEY LASTFM_SHARED_SECRET YOUTUBE_API_KEY SPOTIFY_CLIENT_ID SPOTIFY_CLIENT_SECRET TICKETMASTER_API_KEY NEWSAPI_KEY; do
  v="$(get $k)"; [ -n "$v" ] && echo "$k=$v"
done
echo "--- OPTIONAL (only if you use them)"
for k in PREDICT_HQ_TOKEN GOOGLE_PLACES_API_KEY EVENTBRITE_TOKEN FOURSQUARE_PLACES_API FOURSQUARE_CLIENT_ID FOURSQUARE_CLIENT_SECRET; do
  v="$(get $k)"; [ -n "$v" ] && echo "$k=$v"
done
echo
echo "================ VARIABLES (Settings → New variable; not secret) ================"
echo 'CORS_ORIGINS=["https://jashdoshi77-smartevents.hf.space"]'
echo "GROQ_MODEL=$(get GROQ_MODEL)"
