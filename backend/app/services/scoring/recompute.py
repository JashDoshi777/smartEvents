"""One-off/maintenance CLI: re-score every stored entity_metrics row with the
current composite formula (app/services/scoring/composite.py).

    python -m app.services.scoring.recompute          # dry run (prints counts)
    python -m app.services.scoring.recompute --apply  # writes composite_score

Only rows written by the metrics worker are touched (social-listening rows
never carry a composite). Idempotent; only the composite_score column changes.
"""
import asyncio
import sys

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.scoring.composite import compute_composite


async def main(apply: bool) -> None:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text(
            "select entity_id, time, lastfm_listeners, youtube_subscribers, google_trend_score, "
            "news_mentions_7d, composite_score, spotify_popularity, wikipedia_views_30d from entity_metrics "
            "where collection_source = 'entity_metrics_worker'"
        ))).all()
        ups = []
        for e, t, a, b, c, d, old, sp, wk in rows:
            new, _ = compute_composite(dict(lastfm_listeners=a, youtube_subscribers=b,
                                            google_trend_score=c, news_mentions_7d=d,
                                            spotify_popularity=sp, wikipedia_views_30d=wk))
            if (new is None) != (old is None) or (new is not None and abs(new - old) > 0.005):
                ups.append({"e": e, "t": t, "n": new})
        print(f"{len(rows)} rows, {len(ups)} need re-scoring")
        if apply and ups:
            await s.execute(text("update entity_metrics set composite_score=:n where entity_id=:e and time=:t"), ups)
            await s.commit()
            print("applied")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
