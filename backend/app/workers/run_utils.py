"""
LiveIQ — Shared Celery/asyncio bridge helper.

Every worker module runs its actual logic as an async coroutine but is
invoked from Celery's sync task context, so each one needs to spin up an
event loop. That part (asyncio.new_event_loop() + run_until_complete +
close()) was previously copy-pasted verbatim into 9 separate worker
files — this consolidates it into one place.

The copy-pasted version had a real, intermittent bug: `engine` and
`AsyncSessionLocal` (app/core/database.py) are created ONCE at process
import time, and SQLAlchemy's async engine binds its underlying asyncpg
connection pool to whichever event loop first opens a connection on it.
A Celery worker process runs many tasks over its lifetime, each via a
brand-new `asyncio.new_event_loop()` — so the SECOND task to touch the
engine hits a connection pool still bound to the FIRST task's (now
closed) loop, surfacing as "Future attached to a different loop" or
"RuntimeError: Event loop is closed", non-deterministically, mid-upsert.
Disposing the engine's pool at the end of every run forces the next
task to lazily open fresh connections on ITS OWN new loop instead of
reusing stale ones from a dead loop.
"""

import asyncio

from app.core.database import engine


def run_async(coro):
    """Run an async coroutine from a sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()
