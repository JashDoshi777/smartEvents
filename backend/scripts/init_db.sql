-- LiveIQ — Database Initialization Script
-- Run once by Docker on first container start.

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Enable pgvector for AI embeddings (install separately if needed)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable trigram search for fuzzy entity name matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- TimescaleDB hypertable is set up AFTER Alembic migrations via a separate step.
-- See: backend/scripts/setup_timescale.py
