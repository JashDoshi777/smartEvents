"""Tiny ad-hoc SQL runner: python scripts/_q.py "select ..." """
import sys
sys.path.insert(0, ".")
from sqlalchemy import create_engine, text
from app.core.config import settings
e = create_engine(settings.POSTGRES_SYNC_URL)
with e.connect() as c:
    for r in c.execute(text(sys.argv[1])):
        print(*r, sep=" | ")
