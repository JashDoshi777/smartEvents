---
title: LiveIQ
emoji: 📊
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: India-first live-events intelligence for Zomato District
---

# LiveIQ

India-first live-events intelligence: artist scoring, city markets, venues, pricing and an AI copilot.
FastAPI + Next.js, one container. See `DATA_DICTIONARY.md` and `frontend/DESIGN_GUIDE.md`.

Required secrets are listed in `backend/.env.example` (minimum: `POSTGRES_URL`, `POSTGRES_SYNC_URL`, `SECRET_KEY`).
