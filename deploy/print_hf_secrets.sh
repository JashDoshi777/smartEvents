#!/usr/bin/env bash
# Prints what to paste into Hugging Face → Space → Settings → "Variables and secrets".
# Run LOCALLY in your own terminal (reads backend/.env on your machine; nothing is sent anywhere):
#     bash deploy/print_hf_secrets.sh
#
# For each item: type the NAME into the "Name" box, then copy ONLY the line under VALUE into the "Value" box.
# Select the value with a triple-click or by dragging, and do NOT include a trailing line break/space.
set -euo pipefail
ENV_FILE="$(dirname "$0")/../backend/.env"
[ -f "$ENV_FILE" ] || { echo "backend/.env not found"; exit 1; }

get() { awk -F= -v k="$1" '{kk=$1; gsub(/ /,"",kk)} kk==k {v=$0; sub(/^[^=]*=[ ]*/,"",v); gsub(/^["'"'"']|["'"'"']$/,"",v); gsub(/[ \t\r]+$/,"",v); print v; exit}' "$ENV_FILE"; }
show() { printf 'NAME : %s\nVALUE:\n%s\n\n' "$1" "$2"; }

echo "################ SECRETS  (Settings → New secret) ################"
echo; echo "=== REQUIRED ==="; echo
for k in POSTGRES_URL POSTGRES_SYNC_URL; do show "$k" "$(get $k)"; done
show SECRET_KEY "$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
echo "(SECRET_KEY above is freshly generated. It must be long and random — never reuse an example value.)"
echo; echo "=== RECOMMENDED (features degrade gracefully without them) ==="; echo
for k in GROQ_API_KEY LASTFM_API_KEY LASTFM_SHARED_SECRET YOUTUBE_API_KEY SPOTIFY_CLIENT_ID SPOTIFY_CLIENT_SECRET TICKETMASTER_API_KEY NEWSAPI_KEY; do
  v="$(get $k)"; [ -n "$v" ] && show "$k" "$v"
done
echo "=== OPTIONAL ==="; echo
for k in PREDICT_HQ_TOKEN GOOGLE_PLACES_API_KEY EVENTBRITE_TOKEN FOURSQUARE_PLACES_API FOURSQUARE_CLIENT_ID FOURSQUARE_CLIENT_SECRET; do
  v="$(get $k)"; [ -n "$v" ] && show "$k" "$v"
done
echo "################ VARIABLES  (Settings → New variable; not secret) ################"; echo
show CORS_ORIGINS '["https://jashdoshi77-smartevents.hf.space"]'
