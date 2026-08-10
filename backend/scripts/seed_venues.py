"""
LiveIQ — Venue Seed Script
Seeds real, well-known Indian venues across all 12 tracked cities.
Run: python scripts/seed_venues.py
"""
import asyncio
import sys
sys.path.insert(0, '.')

VENUES = [
    # ── Mumbai ────────────────────────────────────────────────────────────────
    {
        "name": "Jio World Garden", "venue_type": "outdoor_grounds",
        "city": "Mumbai", "state": "Maharashtra",
        "total_capacity": 9000, "standing_capacity": 7000, "seated_capacity": 2000,
        "suitable_categories": ["music", "edm", "international"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 2000,
        "avg_fill_rate": 0.82, "avg_ticket_price": 3500.0, "avg_rating": 4.4,
        "amenities": {"food_stalls": True, "vip_lounge": True, "metro_nearby": False},
    },
    {
        "name": "Dome, NSCI SVP Stadium", "venue_type": "arena",
        "city": "Mumbai", "state": "Maharashtra",
        "total_capacity": 5000, "standing_capacity": 3000, "seated_capacity": 2000,
        "suitable_categories": ["music", "comedy", "sports"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 800,
        "avg_fill_rate": 0.78, "avg_ticket_price": 2800.0, "avg_rating": 4.2,
        "amenities": {"food_stalls": True, "vip_lounge": True, "metro_nearby": True},
    },
    {
        "name": "MMRDA Grounds, BKC", "venue_type": "outdoor_grounds",
        "city": "Mumbai", "state": "Maharashtra",
        "total_capacity": 50000, "standing_capacity": 45000, "seated_capacity": 5000,
        "suitable_categories": ["music", "sports"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 3000,
        "avg_fill_rate": 0.71, "avg_ticket_price": 4200.0, "avg_rating": 4.1,
        "amenities": {"food_stalls": True, "vip_lounge": True, "metro_nearby": True},
    },
    {
        "name": "St Andrews Auditorium", "venue_type": "theatre",
        "city": "Mumbai", "state": "Maharashtra",
        "total_capacity": 800, "standing_capacity": 0, "seated_capacity": 800,
        "suitable_categories": ["comedy", "theatre"],
        "is_indoor": True, "has_parking": False,
        "avg_fill_rate": 0.85, "avg_ticket_price": 800.0, "avg_rating": 4.3,
        "amenities": {"vip_lounge": False, "metro_nearby": True},
    },

    # ── Delhi NCR ─────────────────────────────────────────────────────────────
    {
        "name": "Jawaharlal Nehru Stadium", "venue_type": "stadium",
        "city": "Delhi NCR", "state": "Delhi",
        "total_capacity": 75000, "standing_capacity": 60000, "seated_capacity": 15000,
        "suitable_categories": ["sports", "music", "international"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 4000,
        "avg_fill_rate": 0.68, "avg_ticket_price": 3000.0, "avg_rating": 4.0,
        "amenities": {"food_stalls": True, "vip_lounge": True, "metro_nearby": True},
    },
    {
        "name": "Indira Gandhi Indoor Stadium", "venue_type": "arena",
        "city": "Delhi NCR", "state": "Delhi",
        "total_capacity": 14000, "standing_capacity": 9000, "seated_capacity": 5000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 1000,
        "avg_fill_rate": 0.75, "avg_ticket_price": 2600.0, "avg_rating": 4.2,
        "amenities": {"food_stalls": True, "vip_lounge": True, "metro_nearby": True},
    },
    {
        "name": "Siri Fort Auditorium", "venue_type": "theatre",
        "city": "Delhi NCR", "state": "Delhi",
        "total_capacity": 2000, "standing_capacity": 0, "seated_capacity": 2000,
        "suitable_categories": ["theatre", "comedy"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 200,
        "avg_fill_rate": 0.80, "avg_ticket_price": 1200.0, "avg_rating": 4.3,
        "amenities": {"metro_nearby": True},
    },
    {
        "name": "DLF CyberHub Amphitheatre", "venue_type": "amphitheatre",
        "city": "Delhi NCR", "state": "Delhi",
        "total_capacity": 3000, "standing_capacity": 2200, "seated_capacity": 800,
        "suitable_categories": ["music", "comedy"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 500,
        "avg_fill_rate": 0.83, "avg_ticket_price": 1800.0, "avg_rating": 4.4,
        "amenities": {"food_stalls": True, "metro_nearby": True},
    },

    # ── Bengaluru ─────────────────────────────────────────────────────────────
    {
        "name": "Palace Grounds", "venue_type": "outdoor_grounds",
        "city": "Bengaluru", "state": "Karnataka",
        "total_capacity": 40000, "standing_capacity": 36000, "seated_capacity": 4000,
        "suitable_categories": ["music", "edm", "sports"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 2500,
        "avg_fill_rate": 0.85, "avg_ticket_price": 3200.0, "avg_rating": 4.5,
        "amenities": {"food_stalls": True, "vip_lounge": True, "metro_nearby": False},
    },
    {
        "name": "Sree Kanteerava Indoor Stadium", "venue_type": "arena",
        "city": "Bengaluru", "state": "Karnataka",
        "total_capacity": 4000, "standing_capacity": 2500, "seated_capacity": 1500,
        "suitable_categories": ["sports", "music"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 600,
        "avg_fill_rate": 0.79, "avg_ticket_price": 2200.0, "avg_rating": 4.2,
        "amenities": {"food_stalls": True, "metro_nearby": True},
    },
    {
        "name": "Chowdiah Memorial Hall", "venue_type": "theatre",
        "city": "Bengaluru", "state": "Karnataka",
        "total_capacity": 1400, "standing_capacity": 0, "seated_capacity": 1400,
        "suitable_categories": ["music", "theatre", "classical"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 150,
        "avg_fill_rate": 0.81, "avg_ticket_price": 900.0, "avg_rating": 4.4,
        "amenities": {"metro_nearby": True},
    },

    # ── Hyderabad ─────────────────────────────────────────────────────────────
    {
        "name": "GMR Arena, Shamshabad", "venue_type": "outdoor_grounds",
        "city": "Hyderabad", "state": "Telangana",
        "total_capacity": 15000, "standing_capacity": 12500, "seated_capacity": 2500,
        "suitable_categories": ["music", "edm"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 1500,
        "avg_fill_rate": 0.74, "avg_ticket_price": 2800.0, "avg_rating": 4.1,
        "amenities": {"food_stalls": True, "metro_nearby": False},
    },
    {
        "name": "Gachibowli Indoor Stadium", "venue_type": "arena",
        "city": "Hyderabad", "state": "Telangana",
        "total_capacity": 10000, "standing_capacity": 6500, "seated_capacity": 3500,
        "suitable_categories": ["sports", "music"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 900,
        "avg_fill_rate": 0.72, "avg_ticket_price": 2000.0, "avg_rating": 4.0,
        "amenities": {"food_stalls": True, "metro_nearby": True},
    },
    {
        "name": "Ravindra Bharathi", "venue_type": "theatre",
        "city": "Hyderabad", "state": "Telangana",
        "total_capacity": 1200, "standing_capacity": 0, "seated_capacity": 1200,
        "suitable_categories": ["theatre", "classical", "comedy"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 100,
        "avg_fill_rate": 0.77, "avg_ticket_price": 700.0, "avg_rating": 4.3,
        "amenities": {"metro_nearby": True},
    },

    # ── Pune ──────────────────────────────────────────────────────────────────
    {
        "name": "Shree Shiv Chhatrapati Sports Complex", "venue_type": "sports_complex",
        "city": "Pune", "state": "Maharashtra",
        "total_capacity": 15000, "standing_capacity": 10000, "seated_capacity": 5000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 1200,
        "avg_fill_rate": 0.70, "avg_ticket_price": 2000.0, "avg_rating": 4.0,
        "amenities": {"food_stalls": True, "metro_nearby": False},
    },
    {
        "name": "Balewadi Sports Complex", "venue_type": "arena",
        "city": "Pune", "state": "Maharashtra",
        "total_capacity": 12000, "standing_capacity": 8000, "seated_capacity": 4000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 1000,
        "avg_fill_rate": 0.73, "avg_ticket_price": 2100.0, "avg_rating": 4.1,
        "amenities": {"food_stalls": True, "metro_nearby": False},
    },
    {
        "name": "Bal Gandharva Rang Mandir", "venue_type": "theatre",
        "city": "Pune", "state": "Maharashtra",
        "total_capacity": 1000, "standing_capacity": 0, "seated_capacity": 1000,
        "suitable_categories": ["theatre", "comedy"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 100,
        "avg_fill_rate": 0.82, "avg_ticket_price": 600.0, "avg_rating": 4.3,
        "amenities": {"metro_nearby": False},
    },

    # ── Chennai ───────────────────────────────────────────────────────────────
    {
        "name": "Jawaharlal Nehru Indoor Stadium, Chennai", "venue_type": "arena",
        "city": "Chennai", "state": "Tamil Nadu",
        "total_capacity": 9000, "standing_capacity": 6000, "seated_capacity": 3000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 700,
        "avg_fill_rate": 0.69, "avg_ticket_price": 1800.0, "avg_rating": 4.0,
        "amenities": {"food_stalls": True, "metro_nearby": True},
    },
    {
        "name": "YMCA Grounds, Nandanam", "venue_type": "outdoor_grounds",
        "city": "Chennai", "state": "Tamil Nadu",
        "total_capacity": 8000, "standing_capacity": 6500, "seated_capacity": 1500,
        "suitable_categories": ["music", "comedy"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 400,
        "avg_fill_rate": 0.71, "avg_ticket_price": 1400.0, "avg_rating": 4.0,
        "amenities": {"food_stalls": True, "metro_nearby": True},
    },
    {
        "name": "Music Academy Auditorium", "venue_type": "theatre",
        "city": "Chennai", "state": "Tamil Nadu",
        "total_capacity": 1800, "standing_capacity": 0, "seated_capacity": 1800,
        "suitable_categories": ["classical", "theatre"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 150,
        "avg_fill_rate": 0.84, "avg_ticket_price": 800.0, "avg_rating": 4.5,
        "amenities": {"metro_nearby": True},
    },

    # ── Kolkata ───────────────────────────────────────────────────────────────
    {
        "name": "Salt Lake Stadium (Vivekananda Yuba Bharati Krirangan)", "venue_type": "stadium",
        "city": "Kolkata", "state": "West Bengal",
        "total_capacity": 85000, "standing_capacity": 70000, "seated_capacity": 15000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 3000,
        "avg_fill_rate": 0.65, "avg_ticket_price": 2400.0, "avg_rating": 3.9,
        "amenities": {"food_stalls": True, "metro_nearby": True},
    },
    {
        "name": "Netaji Indoor Stadium", "venue_type": "arena",
        "city": "Kolkata", "state": "West Bengal",
        "total_capacity": 11000, "standing_capacity": 7000, "seated_capacity": 4000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 800,
        "avg_fill_rate": 0.70, "avg_ticket_price": 1900.0, "avg_rating": 4.0,
        "amenities": {"food_stalls": True, "metro_nearby": True},
    },
    {
        "name": "Rabindra Sadan", "venue_type": "theatre",
        "city": "Kolkata", "state": "West Bengal",
        "total_capacity": 1100, "standing_capacity": 0, "seated_capacity": 1100,
        "suitable_categories": ["theatre", "classical", "cultural"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 100,
        "avg_fill_rate": 0.79, "avg_ticket_price": 500.0, "avg_rating": 4.3,
        "amenities": {"metro_nearby": True},
    },

    # ── Ahmedabad ─────────────────────────────────────────────────────────────
    {
        "name": "EKA Arena by Transstadia", "venue_type": "arena",
        "city": "Ahmedabad", "state": "Gujarat",
        "total_capacity": 20000, "standing_capacity": 15000, "seated_capacity": 5000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 1500,
        "avg_fill_rate": 0.66, "avg_ticket_price": 2000.0, "avg_rating": 4.1,
        "amenities": {"food_stalls": True, "metro_nearby": False},
    },
    {
        "name": "GMDC Ground", "venue_type": "outdoor_grounds",
        "city": "Ahmedabad", "state": "Gujarat",
        "total_capacity": 25000, "standing_capacity": 22000, "seated_capacity": 3000,
        "suitable_categories": ["music", "garba"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 1500,
        "avg_fill_rate": 0.72, "avg_ticket_price": 1500.0, "avg_rating": 4.0,
        "amenities": {"food_stalls": True, "metro_nearby": False},
    },

    # ── Jaipur ────────────────────────────────────────────────────────────────
    {
        "name": "Sawai Mansingh Stadium", "venue_type": "stadium",
        "city": "Jaipur", "state": "Rajasthan",
        "total_capacity": 30000, "standing_capacity": 24000, "seated_capacity": 6000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 1500,
        "avg_fill_rate": 0.60, "avg_ticket_price": 1600.0, "avg_rating": 3.9,
        "amenities": {"food_stalls": True, "metro_nearby": False},
    },
    {
        "name": "Jawahar Kala Kendra", "venue_type": "art_gallery",
        "city": "Jaipur", "state": "Rajasthan",
        "total_capacity": 1500, "standing_capacity": 800, "seated_capacity": 700,
        "suitable_categories": ["cultural", "theatre", "music"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 150,
        "avg_fill_rate": 0.75, "avg_ticket_price": 500.0, "avg_rating": 4.4,
        "amenities": {"metro_nearby": False},
    },

    # ── Chandigarh ────────────────────────────────────────────────────────────
    {
        # Large concerts were redirected here from Sector 34 Grounds after
        # traffic/noise complaints led the UT administration to restrict Sector 34.
        "name": "Sector 25 Grounds", "venue_type": "outdoor_grounds",
        "city": "Chandigarh", "state": "Chandigarh (UT)",
        "total_capacity": 12000, "standing_capacity": 10000, "seated_capacity": 2000,
        "suitable_categories": ["music", "punjabi_pop", "edm"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 800,
        "avg_fill_rate": 0.76, "avg_ticket_price": 1700.0, "avg_rating": 4.1,
        "amenities": {"food_stalls": True, "metro_nearby": False},
    },
    {
        "name": "Tagore Theatre", "venue_type": "theatre",
        "city": "Chandigarh", "state": "Chandigarh (UT)",
        "total_capacity": 900, "standing_capacity": 0, "seated_capacity": 900,
        "suitable_categories": ["theatre", "comedy"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 100,
        "avg_fill_rate": 0.80, "avg_ticket_price": 600.0, "avg_rating": 4.2,
        "amenities": {"metro_nearby": False},
    },

    # ── Kochi ─────────────────────────────────────────────────────────────────
    {
        "name": "Jawaharlal Nehru International Stadium, Kochi", "venue_type": "stadium",
        "city": "Kochi", "state": "Kerala",
        "total_capacity": 41000, "standing_capacity": 34000, "seated_capacity": 7000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 2000,
        "avg_fill_rate": 0.62, "avg_ticket_price": 1500.0, "avg_rating": 3.9,
        "amenities": {"food_stalls": True, "metro_nearby": True},
    },
    {
        "name": "Kerala Fine Arts Hall", "venue_type": "theatre",
        "city": "Kochi", "state": "Kerala",
        "total_capacity": 700, "standing_capacity": 0, "seated_capacity": 700,
        "suitable_categories": ["cultural", "theatre", "classical"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 60,
        "avg_fill_rate": 0.78, "avg_ticket_price": 400.0, "avg_rating": 4.3,
        "amenities": {"metro_nearby": True},
    },

    # ── Indore ────────────────────────────────────────────────────────────────
    {
        "name": "Nehru Stadium, Indore", "venue_type": "stadium",
        "city": "Indore", "state": "Madhya Pradesh",
        "total_capacity": 25000, "standing_capacity": 20000, "seated_capacity": 5000,
        "suitable_categories": ["sports", "music"],
        "is_indoor": False, "has_parking": True, "parking_capacity": 1200,
        "avg_fill_rate": 0.58, "avg_ticket_price": 1300.0, "avg_rating": 3.8,
        "amenities": {"food_stalls": True, "metro_nearby": False},
    },
    {
        "name": "Abhay Prashal Indoor Stadium", "venue_type": "arena",
        "city": "Indore", "state": "Madhya Pradesh",
        "total_capacity": 6000, "standing_capacity": 4000, "seated_capacity": 2000,
        "suitable_categories": ["sports", "music", "comedy"],
        "is_indoor": True, "has_parking": True, "parking_capacity": 500,
        "avg_fill_rate": 0.64, "avg_ticket_price": 1000.0, "avg_rating": 3.9,
        "amenities": {"food_stalls": True, "metro_nearby": False},
    },
]


async def main():
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.venue import Venue

    print(f"\nSeeding {len(VENUES)} venues across {len(set(v['city'] for v in VENUES))} cities...")
    async with AsyncSessionLocal() as session:
        seeded, skipped = 0, 0
        for v in VENUES:
            result = await session.execute(
                select(Venue).where(Venue.name == v["name"], Venue.city == v["city"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  ~ {v['name']} ({v['city']}) already exists — skipping")
                skipped += 1
                continue

            venue = Venue(**v)
            session.add(venue)
            print(f"  + {v['name']} ({v['city']}, cap {v['total_capacity']})")
            seeded += 1

        await session.commit()

    print(f"\n{'='*55}")
    print(f"  DONE — {seeded} venues seeded, {skipped} skipped")
    print(f"{'='*55}\n")


asyncio.run(main())
