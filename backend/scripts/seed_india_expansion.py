"""
LiveIQ — India expansion seed.

Adds well-known Indian entities (artists, comedians, IPL/ISL/PKL teams,
festivals, films) that the original seed lacked, then collects REAL metrics
for each via the existing entity_metrics pipeline (Last.fm, YouTube,
Google Trends, NewsAPI). Nothing here fabricates popularity numbers: only
identity facts (name, type, home city) are seeded; scores come from live APIs.

Also repairs mis-ingested rows from the global-chart importer (Bollywood
film titles stored as "artists", a news site stored as an artist).

Idempotent: safe to re-run. Usage:
    python scripts/seed_india_expansion.py            # seed + fix + collect metrics
    python scripts/seed_india_expansion.py --no-metrics
"""
import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.models.entity import Entity

A, C, S, M, X = "artist", "comedian", "sports_team", "movie", "attraction"

# name, type, category, genre, home_city, home_state
ROWS = [
    # ── Hindi / Bollywood / Pop ──
    ("Vishal-Shekhar", A, "Bollywood", "Bollywood", "Mumbai", "Maharashtra"),
    ("Darshan Raval", A, "Bollywood", "Pop", "Surat", "Gujarat"),
    ("B Praak", A, "Bollywood", "Bollywood", "Amritsar", "Punjab"),
    ("Sachet-Parampara", A, "Bollywood", "Bollywood", "Mumbai", "Maharashtra"),
    ("Dhvani Bhanushali", A, "Bollywood", "Pop", "Mumbai", "Maharashtra"),
    ("Arjun Kanungo", A, "Bollywood", "Pop", "Mumbai", "Maharashtra"),
    ("Lucky Ali", A, "Indian Indie", "Indie Pop", "Bengaluru", "Karnataka"),
    ("Papon", A, "Indian Indie", "Folk Fusion", "Guwahati", "Assam"),
    ("Anuv Jain", A, "Indian Indie", "Indie Pop", "Delhi NCR", "Delhi"),
    ("Vilen", A, "Indian Indie", "Indie Pop", "Bengaluru", "Karnataka"),
    ("Sanam", A, "Indian Indie", "Pop Rock", "Mumbai", "Maharashtra"),
    ("Lost Stories", A, "Indian EDM", "Electronic", "Mumbai", "Maharashtra"),
    ("Zaeden", A, "Indian EDM", "Electronic", "Mumbai", "Maharashtra"),
    # ── Punjabi / Hip-hop ──
    ("Gippy Grewal", A, "Punjabi Pop", "Punjabi", "Ludhiana", "Punjab"),
    ("Sultaan", A, "Punjabi Pop", "Punjabi", "Chandigarh", "Punjab"),
    ("Seedhe Maut", A, "Indian Hip-Hop", "Hip-Hop", "Delhi NCR", "Delhi"),
    ("Emiway Bantai", A, "Indian Hip-Hop", "Hip-Hop", "Mumbai", "Maharashtra"),
    ("KR$NA", A, "Indian Hip-Hop", "Hip-Hop", "Delhi NCR", "Delhi"),
    ("King", A, "Indian Hip-Hop", "Hip-Hop", "Delhi NCR", "Delhi"),
    ("MC Stan", A, "Indian Hip-Hop", "Hip-Hop", "Pune", "Maharashtra"),
    ("Dino James", A, "Indian Hip-Hop", "Hip-Hop", "Dehradun", "Uttarakhand"),
    ("Brodha V", A, "Indian Hip-Hop", "Hip-Hop", "Bengaluru", "Karnataka"),
    # ── South / regional / fusion ──
    ("Anirudh Ravichander", A, "South Indian", "Film Music", "Chennai", "Tamil Nadu"),
    ("Devi Sri Prasad", A, "South Indian", "Film Music", "Hyderabad", "Telangana"),
    ("Sid Sriram", A, "South Indian", "Playback", "Chennai", "Tamil Nadu"),
    ("Raghu Dixit Project", A, "Indian Indie", "Folk Rock", "Bengaluru", "Karnataka"),
    ("Thaikkudam Bridge", A, "Indian Indie", "Fusion", "Kochi", "Kerala"),
    ("Avial", A, "Indian Indie", "Rock", "Thiruvananthapuram", "Kerala"),
    ("Indian Ocean", A, "Indian Indie", "Fusion Rock", "Delhi NCR", "Delhi"),
    ("Ravi Shankar", A, "Classical", "Sitar", "Varanasi", "Uttar Pradesh"),
    ("Kaushiki Chakraborty", A, "Classical", "Hindustani", "Kolkata", "West Bengal"),
    # ── Stand-up comedy ──
    ("Samay Raina", C, "Stand-Up Comedy", "Stand-Up", "Delhi NCR", "Delhi"),
    ("Vir Das", C, "Stand-Up Comedy", "Stand-Up", "Mumbai", "Maharashtra"),
    ("Abhishek Upmanyu", C, "Stand-Up Comedy", "Stand-Up", "Delhi NCR", "Delhi"),
    ("Rahul Subramanian", C, "Stand-Up Comedy", "Stand-Up", "Bengaluru", "Karnataka"),
    ("Gaurav Kapoor", C, "Stand-Up Comedy", "Stand-Up", "Delhi NCR", "Delhi"),
    ("Sapan Verma", C, "Stand-Up Comedy", "Stand-Up", "Delhi NCR", "Delhi"),
    ("Aakash Mehta", C, "Stand-Up Comedy", "Stand-Up", "Mumbai", "Maharashtra"),
    ("Rohan Joshi", C, "Stand-Up Comedy", "Stand-Up", "Mumbai", "Maharashtra"),
    ("Tanmay Bhat", C, "Stand-Up Comedy", "Stand-Up", "Mumbai", "Maharashtra"),
    ("Aditi Mittal", C, "Stand-Up Comedy", "Stand-Up", "Mumbai", "Maharashtra"),
    ("Abish Mathew", C, "Stand-Up Comedy", "Stand-Up", "Bengaluru", "Karnataka"),
    ("Harsh Gujral", C, "Stand-Up Comedy", "Stand-Up", "Delhi NCR", "Delhi"),
    ("Prashasti Singh", C, "Stand-Up Comedy", "Stand-Up", "Delhi NCR", "Delhi"),
    ("Daniel Fernandes", C, "Stand-Up Comedy", "Stand-Up", "Mumbai", "Maharashtra"),
    # ── IPL / ISL / PKL ──
    ("Gujarat Titans", S, "Cricket", "IPL", "Ahmedabad", "Gujarat"),
    ("Lucknow Super Giants", S, "Cricket", "IPL", "Lucknow", "Uttar Pradesh"),
    ("Sunrisers Hyderabad", S, "Cricket", "IPL", "Hyderabad", "Telangana"),
    ("Rajasthan Royals", S, "Cricket", "IPL", "Jaipur", "Rajasthan"),
    ("Punjab Kings", S, "Cricket", "IPL", "Mohali", "Punjab"),
    ("Bengaluru FC", S, "Football", "ISL", "Bengaluru", "Karnataka"),
    ("Kerala Blasters FC", S, "Football", "ISL", "Kochi", "Kerala"),
    ("Mohun Bagan Super Giant", S, "Football", "ISL", "Kolkata", "West Bengal"),
    ("East Bengal FC", S, "Football", "ISL", "Kolkata", "West Bengal"),
    ("FC Goa", S, "Football", "ISL", "Margao", "Goa"),
    ("Patna Pirates", S, "Kabaddi", "PKL", "Patna", "Bihar"),
    ("Bengaluru Bulls", S, "Kabaddi", "PKL", "Bengaluru", "Karnataka"),
    ("Jaipur Pink Panthers", S, "Kabaddi", "PKL", "Jaipur", "Rajasthan"),
    # ── Festivals (live-event brands) ──
    ("Sunburn Festival", X, "Festival", "EDM Festival", "Pune", "Maharashtra"),
    ("NH7 Weekender", X, "Festival", "Multi-genre Festival", "Pune", "Maharashtra"),
    ("Lollapalooza India", X, "Festival", "Multi-genre Festival", "Mumbai", "Maharashtra"),
    ("Magnetic Fields Festival", X, "Festival", "Electronic Festival", "Alsisar", "Rajasthan"),
    ("Echoes of Earth", X, "Festival", "Electronic Festival", "Bengaluru", "Karnataka"),
    ("Ziro Festival of Music", X, "Festival", "Indie Festival", "Ziro", "Arunachal Pradesh"),
    # ── Films ──
    ("Jawan", M, "Bollywood", "Action", "Mumbai", "Maharashtra"),
    ("Pathaan", M, "Bollywood", "Action", "Mumbai", "Maharashtra"),
    ("Animal", M, "Bollywood", "Drama", "Mumbai", "Maharashtra"),
    ("RRR", M, "South Indian", "Action", "Hyderabad", "Telangana"),
    ("KGF: Chapter 2", M, "South Indian", "Action", "Bengaluru", "Karnataka"),
]

# Film titles that the global-chart importer stored as music "artists".
FILM_TITLES_TO_RECLASSIFY = ["Jodhaa Akbar", "Chak De India", "Om Shanti Om", "Saawariya", "Chingaari", "Baadshah", "Jhoom Barabar Jhoom"]
# Not an entertainment entity at all (news publication).
NOISE_TO_DEACTIVATE = ["Newslaundry"]


async def run(collect_metrics: bool = True) -> None:
    async with AsyncSessionLocal() as s:
        existing = {n.lower() for (n,) in (await s.execute(select(Entity.name))).all()}
        added = []
        for name, etype, cat, genre, city, state in ROWS:
            if name.lower() in existing:
                continue
            s.add(Entity(
                name=name, entity_type=etype, category=cat, genre=genre, genres=[genre],
                country="India", home_city=city, home_state=state,
                primary_market="India", is_verified=False, is_international=False,
                is_active_on_district=False, status="active",
                data_sources=["lastfm", "youtube", "google_trends", "news"] if etype == A else ["youtube", "google_trends", "news"],
                external_ids={},
            ))
            added.append(name)

        fixed = 0
        r = await s.execute(
            update(Entity).where(Entity.name.in_(FILM_TITLES_TO_RECLASSIFY), Entity.entity_type == A)
            .values(entity_type=M, category="Bollywood")
        )
        fixed += r.rowcount or 0
        r = await s.execute(update(Entity).where(Entity.name.in_(NOISE_TO_DEACTIVATE)).values(status="inactive"))
        fixed += r.rowcount or 0
        # Foreign acts that tour India are international, whatever the importer said.
        await s.execute(
            update(Entity).where(Entity.name.in_(["Dua Lipa", "BLACKPINK", "Alan Walker", "Hardwell", "Russell Peters"]))
            .values(is_international=True)
        )
        await s.commit()
    print(f"seeded {len(added)} new entities; repaired {fixed} rows")

    if collect_metrics and added:
        from app.workers.entity_metrics import _process_single_entity
        async with AsyncSessionLocal() as s:
            rows = (await s.execute(select(Entity).where(Entity.name.in_(added)))).scalars().all()
            ents = [{"id": e.id, "name": e.name, "external_ids": e.external_ids or {}, "entity_type": e.entity_type, "category": e.category} for e in rows]
        sem = asyncio.Semaphore(3)

        async def one(e):
            async with sem:
                try:
                    return await _process_single_entity(e)
                except Exception as exc:  # keep going; one bad API call must not abort the batch
                    print("metric collection failed for", e["name"], exc)

        await asyncio.gather(*[one(e) for e in ents])
        print("metrics collected for", len(ents), "entities")


if __name__ == "__main__":
    asyncio.run(run(collect_metrics="--no-metrics" not in sys.argv))
