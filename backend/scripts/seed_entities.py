"""
LiveIQ — Entity Seed Script (Sprint 2A)
Seeds 60 real-world entities into NeonDB covering all District categories:
  - Music (Indian: Bollywood, Punjabi, Indie | International: Pop, EDM, K-Pop)
  - Comedy (Indian stand-up | International)
  - Sports (Cricket, Football, Kabaddi, Badminton)
  - Movies (Bollywood, South Indian, International franchise)
  - Theatre / Culture
Run: python scripts/seed_entities.py
"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.core.database import AsyncSessionLocal
from app.models.entity import Entity, EntityType, EntityStatus
from sqlalchemy import select
import structlog

logger = structlog.get_logger()

# ─── Entity Seed Data ────────────────────────────────────────────────────────
ENTITIES = [

    # ── MUSIC: Bollywood / Hindi ─────────────────────────────────────────────
    {
        "name": "Arijit Singh",
        "entity_type": EntityType.ARTIST.value,
        "category": "Bollywood",
        "sub_categories": ["Hindi", "Playback", "Live Concerts"],
        "genre": "Bollywood",
        "genres": ["Bollywood", "Romantic", "Ghazal"],
        "country": "India", "home_city": "Kolkata", "home_state": "West Bengal",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 5000000, "booking_price_range_max": 20000000,
        "typical_venue_capacity_min": 5000, "typical_venue_capacity_max": 50000,
        "external_ids": {"lastfm_name": "Arijit Singh"},
        "description": "India's most-streamed singer; known for soulful romantic ballads.",
    },
    {
        "name": "AR Rahman",
        "entity_type": EntityType.ARTIST.value,
        "category": "Bollywood",
        "sub_categories": ["Hindi", "Tamil", "Composer", "Live Concerts"],
        "genre": "Fusion",
        "genres": ["Bollywood", "World Music", "Sufi", "Electronic"],
        "country": "India", "home_city": "Chennai", "home_state": "Tamil Nadu",
        "primary_market": "India",
        "is_verified": True, "is_international": True, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 10000000, "booking_price_range_max": 40000000,
        "typical_venue_capacity_min": 10000, "typical_venue_capacity_max": 80000,
        "external_ids": {"lastfm_name": "A.R. Rahman"},
        "description": "Oscar-winning composer; legendary live concert spectacles.",
    },
    {
        "name": "Shreya Ghoshal",
        "entity_type": EntityType.ARTIST.value,
        "category": "Bollywood",
        "sub_categories": ["Hindi", "Playback", "Classical"],
        "genre": "Bollywood",
        "genres": ["Bollywood", "Classical", "Romantic"],
        "country": "India", "home_city": "Mumbai", "home_state": "Maharashtra",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 2000000, "booking_price_range_max": 8000000,
        "typical_venue_capacity_min": 3000, "typical_venue_capacity_max": 30000,
        "external_ids": {"lastfm_name": "Shreya Ghoshal"},
        "description": "India's most awarded female playback singer.",
    },

    # ── MUSIC: Punjabi / Pop ─────────────────────────────────────────────────
    {
        "name": "Diljit Dosanjh",
        "entity_type": EntityType.ARTIST.value,
        "category": "Punjabi Pop",
        "sub_categories": ["Punjabi", "Bhangra", "Bollywood Actor"],
        "genre": "Punjabi Pop",
        "genres": ["Punjabi", "Bhangra", "Pop", "Bollywood"],
        "country": "India", "home_city": "Ludhiana", "home_state": "Punjab",
        "primary_market": "India",
        "is_verified": True, "is_international": True, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube", "ticketmaster"],
        "booking_price_range_min": 5000000, "booking_price_range_max": 15000000,
        "typical_venue_capacity_min": 5000, "typical_venue_capacity_max": 60000,
        "external_ids": {"lastfm_name": "Diljit Dosanjh"},
        "description": "India's first Punjabi act to headline Coachella. Massive global fanbase.",
    },
    {
        "name": "AP Dhillon",
        "entity_type": EntityType.ARTIST.value,
        "category": "Punjabi Pop",
        "sub_categories": ["Punjabi", "R&B", "Indo-Canadian"],
        "genre": "Punjabi R&B",
        "genres": ["Punjabi", "R&B", "Pop"],
        "country": "Canada", "home_city": "Gurdaspur", "home_state": "Punjab",
        "primary_market": "India",
        "is_verified": True, "is_international": True, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 3000000, "booking_price_range_max": 10000000,
        "typical_venue_capacity_min": 3000, "typical_venue_capacity_max": 30000,
        "external_ids": {"lastfm_name": "AP Dhillon"},
        "description": "Canada-based Punjabi artist; viral sensation with massive India fanbase.",
    },
    {
        "name": "Karan Aujla",
        "entity_type": EntityType.ARTIST.value,
        "category": "Punjabi Pop",
        "sub_categories": ["Punjabi", "Hip-Hop", "Rap"],
        "genre": "Punjabi Hip-Hop",
        "genres": ["Punjabi", "Hip-Hop", "Rap", "Pop"],
        "country": "Canada", "home_city": "Garhshankar", "home_state": "Punjab",
        "primary_market": "India",
        "is_verified": True, "is_international": True, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 2000000, "booking_price_range_max": 8000000,
        "typical_venue_capacity_min": 3000, "typical_venue_capacity_max": 25000,
        "external_ids": {"lastfm_name": "Karan Aujla"},
        "description": "Indo-Canadian rapper; top-selling artist on BookMyShow 2024-25.",
    },
    {
        "name": "Guru Randhawa",
        "entity_type": EntityType.ARTIST.value,
        "category": "Punjabi Pop",
        "sub_categories": ["Punjabi", "Pop"],
        "genre": "Punjabi Pop",
        "genres": ["Punjabi", "Pop"],
        "country": "India", "home_city": "Gurdaspur", "home_state": "Punjab",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 1500000, "booking_price_range_max": 5000000,
        "typical_venue_capacity_min": 2000, "typical_venue_capacity_max": 20000,
        "external_ids": {"lastfm_name": "Guru Randhawa"},
        "description": "One of India's most-streamed artists on Spotify 2019-2022.",
    },

    # ── MUSIC: Indie / Alternative ───────────────────────────────────────────
    {
        "name": "Prateek Kuhad",
        "entity_type": EntityType.ARTIST.value,
        "category": "Indian Indie",
        "sub_categories": ["Indie", "Folk", "Singer-Songwriter"],
        "genre": "Indie Folk",
        "genres": ["Indie", "Folk", "Acoustic"],
        "country": "India", "home_city": "Jaipur", "home_state": "Rajasthan",
        "primary_market": "India",
        "is_verified": True, "is_international": True, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 500000, "booking_price_range_max": 2000000,
        "typical_venue_capacity_min": 500, "typical_venue_capacity_max": 5000,
        "external_ids": {"lastfm_name": "Prateek Kuhad"},
        "description": "Obama's 2019 favorite music list. Indie darling with global reach.",
    },
    {
        "name": "Ritviz",
        "entity_type": EntityType.ARTIST.value,
        "category": "Indian Indie",
        "sub_categories": ["Electronic", "Indie", "Fusion"],
        "genre": "Electronic Fusion",
        "genres": ["Electronic", "Indie", "Fusion", "Dance"],
        "country": "India", "home_city": "Pune", "home_state": "Maharashtra",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 300000, "booking_price_range_max": 1500000,
        "typical_venue_capacity_min": 500, "typical_venue_capacity_max": 8000,
        "external_ids": {"lastfm_name": "Ritviz"},
        "description": "Electronic-fusion artist; viral with Gen Z through festival circuit.",
    },
    {
        "name": "Peter Cat Recording Co.",
        "entity_type": EntityType.ARTIST.value,
        "category": "Indian Indie",
        "sub_categories": ["Indie", "Jazz", "Alternative"],
        "genre": "Indie Jazz",
        "genres": ["Indie", "Jazz", "Alternative", "Psychedelic"],
        "country": "India", "home_city": "New Delhi", "home_state": "Delhi",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 200000, "booking_price_range_max": 800000,
        "typical_venue_capacity_min": 200, "typical_venue_capacity_max": 3000,
        "external_ids": {"lastfm_name": "Peter Cat Recording Co."},
        "description": "Delhi-based jazz-indie band; critical darling on the international circuit.",
    },
    {
        "name": "When Chai Met Toast",
        "entity_type": EntityType.ARTIST.value,
        "category": "Indian Indie",
        "sub_categories": ["Indie", "Folk", "Acoustic"],
        "genre": "Indie Folk",
        "genres": ["Indie", "Folk", "Acoustic"],
        "country": "India", "home_city": "Kochi", "home_state": "Kerala",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 200000, "booking_price_range_max": 1000000,
        "typical_venue_capacity_min": 300, "typical_venue_capacity_max": 4000,
        "external_ids": {"lastfm_name": "When Chai Met Toast"},
        "description": "Kerala-based indie band; fans of their feel-good sound across South India.",
    },

    # ── MUSIC: International ─────────────────────────────────────────────────
    {
        "name": "Coldplay",
        "entity_type": EntityType.ARTIST.value,
        "category": "International Pop Rock",
        "sub_categories": ["Rock", "Pop", "Alternative"],
        "genre": "Pop Rock",
        "genres": ["Pop", "Rock", "Alternative"],
        "country": "United Kingdom", "home_city": "London",
        "primary_market": "Global",
        "is_verified": True, "is_international": True, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube", "ticketmaster"],
        "booking_price_range_min": 100000000, "booking_price_range_max": 500000000,
        "typical_venue_capacity_min": 50000, "typical_venue_capacity_max": 150000,
        "external_ids": {"lastfm_name": "Coldplay"},
        "description": "Performed India Jan 2025 — highest-demand event in India's concert history.",
    },
    {
        "name": "Ed Sheeran",
        "entity_type": EntityType.ARTIST.value,
        "category": "International Pop",
        "sub_categories": ["Pop", "Singer-Songwriter"],
        "genre": "Pop",
        "genres": ["Pop", "Folk", "R&B"],
        "country": "United Kingdom", "home_city": "Framlingham",
        "primary_market": "Global",
        "is_verified": True, "is_international": True, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube", "ticketmaster"],
        "booking_price_range_min": 80000000, "booking_price_range_max": 300000000,
        "typical_venue_capacity_min": 30000, "typical_venue_capacity_max": 100000,
        "external_ids": {"lastfm_name": "Ed Sheeran"},
        "description": "Mathematics Tour multi-city India leg in early 2025.",
    },
    {
        "name": "The Weeknd",
        "entity_type": EntityType.ARTIST.value,
        "category": "International Pop",
        "sub_categories": ["R&B", "Pop", "Hip-Hop"],
        "genre": "R&B",
        "genres": ["R&B", "Pop", "Hip-Hop", "Electronic"],
        "country": "Canada", "home_city": "Toronto",
        "primary_market": "Global",
        "is_verified": True, "is_international": True, "is_active_on_district": False,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 100000000, "booking_price_range_max": 400000000,
        "typical_venue_capacity_min": 30000, "typical_venue_capacity_max": 80000,
        "external_ids": {"lastfm_name": "The Weeknd"},
        "description": "Massive India fanbase; hasn't toured India yet — high opportunity signal.",
    },
    {
        "name": "Martin Garrix",
        "entity_type": EntityType.ARTIST.value,
        "category": "International EDM",
        "sub_categories": ["EDM", "Progressive House", "DJ"],
        "genre": "Electronic",
        "genres": ["EDM", "Progressive House", "Electronic"],
        "country": "Netherlands", "home_city": "Amsterdam",
        "primary_market": "Global",
        "is_verified": True, "is_international": True, "is_active_on_district": True,
        "data_sources": ["lastfm", "youtube", "ticketmaster"],
        "booking_price_range_min": 50000000, "booking_price_range_max": 200000000,
        "typical_venue_capacity_min": 10000, "typical_venue_capacity_max": 80000,
        "external_ids": {"lastfm_name": "Martin Garrix"},
        "description": "World #1 DJ multiple years; India's EDM festival headliner.",
    },
    {
        "name": "BTS",
        "entity_type": EntityType.ARTIST.value,
        "category": "K-Pop",
        "sub_categories": ["K-Pop", "Pop", "Hip-Hop"],
        "genre": "K-Pop",
        "genres": ["K-Pop", "Pop", "Hip-Hop", "R&B"],
        "country": "South Korea", "home_city": "Seoul",
        "primary_market": "Global",
        "is_verified": True, "is_international": True, "is_active_on_district": False,
        "data_sources": ["lastfm", "youtube"],
        "booking_price_range_min": 200000000, "booking_price_range_max": 800000000,
        "typical_venue_capacity_min": 50000, "typical_venue_capacity_max": 200000,
        "external_ids": {"lastfm_name": "BTS"},
        "description": "Global K-Pop phenomenon; massive Indian ARMY fandom.",
    },

    # ── COMEDY ───────────────────────────────────────────────────────────────
    {
        "name": "Zakir Khan",
        "entity_type": EntityType.COMEDIAN.value,
        "category": "Stand-Up Comedy",
        "sub_categories": ["Hindi Stand-Up", "Storytelling"],
        "genre": "Stand-Up",
        "genres": ["Stand-Up", "Storytelling", "Hindi"],
        "country": "India", "home_city": "Indore", "home_state": "Madhya Pradesh",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["youtube", "newsapi"],
        "booking_price_range_min": 1000000, "booking_price_range_max": 5000000,
        "typical_venue_capacity_min": 500, "typical_venue_capacity_max": 8000,
        "external_ids": {},
        "description": "'Sakht Launda' — India's most beloved Hindi stand-up comedian.",
    },
    {
        "name": "Biswa Kalyan Rath",
        "entity_type": EntityType.COMEDIAN.value,
        "category": "Stand-Up Comedy",
        "sub_categories": ["English Stand-Up", "Tech Comedy"],
        "genre": "Stand-Up",
        "genres": ["Stand-Up", "English", "Observational"],
        "country": "India", "home_city": "Bhubaneswar", "home_state": "Odisha",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["youtube"],
        "booking_price_range_min": 500000, "booking_price_range_max": 2000000,
        "typical_venue_capacity_min": 300, "typical_venue_capacity_max": 5000,
        "external_ids": {},
        "description": "IIT Kharagpur grad turned comic; co-creator of Pretentious Movie Reviews.",
    },
    {
        "name": "Kenny Sebastian",
        "entity_type": EntityType.COMEDIAN.value,
        "category": "Stand-Up Comedy",
        "sub_categories": ["English Stand-Up", "Music Comedy"],
        "genre": "Stand-Up",
        "genres": ["Stand-Up", "English", "Music"],
        "country": "India", "home_city": "Bengaluru", "home_state": "Karnataka",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["youtube"],
        "booking_price_range_min": 500000, "booking_price_range_max": 2000000,
        "typical_venue_capacity_min": 300, "typical_venue_capacity_max": 4000,
        "external_ids": {},
        "description": "Bengaluru-based comedian known for observational and music-infused sets.",
    },
    {
        "name": "Anubhav Singh Bassi",
        "entity_type": EntityType.COMEDIAN.value,
        "category": "Stand-Up Comedy",
        "sub_categories": ["Hindi Stand-Up", "College Comedy"],
        "genre": "Stand-Up",
        "genres": ["Stand-Up", "Hindi"],
        "country": "India", "home_city": "Agra", "home_state": "Uttar Pradesh",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["youtube"],
        "booking_price_range_min": 800000, "booking_price_range_max": 3000000,
        "typical_venue_capacity_min": 500, "typical_venue_capacity_max": 6000,
        "external_ids": {},
        "description": "'Chull' special viral sensation; biggest new-gen Hindi stand-up name.",
    },
    {
        "name": "Trevor Noah",
        "entity_type": EntityType.COMEDIAN.value,
        "category": "International Stand-Up",
        "sub_categories": ["English Stand-Up", "Political Comedy"],
        "genre": "Stand-Up",
        "genres": ["Stand-Up", "Political", "English"],
        "country": "South Africa", "home_city": "Johannesburg",
        "primary_market": "Global",
        "is_verified": True, "is_international": True, "is_active_on_district": True,
        "data_sources": ["newsapi", "ticketmaster"],
        "booking_price_range_min": 10000000, "booking_price_range_max": 50000000,
        "typical_venue_capacity_min": 2000, "typical_venue_capacity_max": 15000,
        "external_ids": {},
        "description": "Former Daily Show host; toured India — high demand in metro cities.",
    },

    # ── SPORTS ───────────────────────────────────────────────────────────────
    {
        "name": "Mumbai Indians",
        "entity_type": EntityType.SPORTS_TEAM.value,
        "category": "Cricket",
        "sub_categories": ["IPL", "T20"],
        "genre": "Cricket",
        "genres": ["Cricket", "T20", "IPL"],
        "country": "India", "home_city": "Mumbai", "home_state": "Maharashtra",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["ticketmaster", "newsapi"],
        "booking_price_range_min": 500, "booking_price_range_max": 50000,
        "typical_venue_capacity_min": 20000, "typical_venue_capacity_max": 45000,
        "external_ids": {},
        "description": "5x IPL champions; most followed sports franchise in India.",
    },
    {
        "name": "Royal Challengers Bengaluru",
        "entity_type": EntityType.SPORTS_TEAM.value,
        "category": "Cricket",
        "sub_categories": ["IPL", "T20"],
        "genre": "Cricket",
        "genres": ["Cricket", "T20", "IPL"],
        "country": "India", "home_city": "Bengaluru", "home_state": "Karnataka",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["ticketmaster", "newsapi"],
        "booking_price_range_min": 500, "booking_price_range_max": 40000,
        "typical_venue_capacity_min": 20000, "typical_venue_capacity_max": 35000,
        "external_ids": {},
        "description": "RCB — massive fan army; Virat Kohli effect; consistently highest demand.",
    },
    {
        "name": "Kolkata Knight Riders",
        "entity_type": EntityType.SPORTS_TEAM.value,
        "category": "Cricket",
        "sub_categories": ["IPL", "T20"],
        "genre": "Cricket",
        "genres": ["Cricket", "T20", "IPL"],
        "country": "India", "home_city": "Kolkata", "home_state": "West Bengal",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["ticketmaster", "newsapi"],
        "booking_price_range_min": 500, "booking_price_range_max": 35000,
        "typical_venue_capacity_min": 20000, "typical_venue_capacity_max": 60000,
        "external_ids": {},
        "description": "2-time IPL champions; Eden Gardens is India's largest cricket stadium.",
    },
    {
        "name": "PV Sindhu",
        "entity_type": EntityType.SPORTS_TEAM.value,
        "category": "Badminton",
        "sub_categories": ["Badminton", "Olympics"],
        "genre": "Badminton",
        "genres": ["Badminton", "Olympics"],
        "country": "India", "home_city": "Hyderabad", "home_state": "Telangana",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": False,
        "data_sources": ["newsapi"],
        "booking_price_range_min": None, "booking_price_range_max": None,
        "typical_venue_capacity_min": 5000, "typical_venue_capacity_max": 20000,
        "external_ids": {},
        "description": "Olympic silver/bronze medallist; face of Indian badminton.",
    },

    # ── MOVIES / OTT (tracked as entities for event screenings) ─────────────
    {
        "name": "Pushpa 2: The Rule",
        "entity_type": EntityType.MOVIE.value,
        "category": "South Indian",
        "sub_categories": ["Telugu", "Action", "Blockbuster"],
        "genre": "Action",
        "genres": ["Action", "Drama", "Telugu"],
        "country": "India", "home_city": "Hyderabad",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["tmdb", "newsapi"],
        "external_ids": {"tmdb_name": "Pushpa 2 The Rule"},
        "description": "Allu Arjun blockbuster; ₹1800 Cr+ global box office. Special screening events.",
    },
    {
        "name": "Stree 2",
        "entity_type": EntityType.MOVIE.value,
        "category": "Bollywood",
        "sub_categories": ["Horror Comedy", "Bollywood"],
        "genre": "Horror Comedy",
        "genres": ["Horror", "Comedy", "Bollywood"],
        "country": "India", "home_city": "Mumbai",
        "primary_market": "India",
        "is_verified": True, "is_international": False, "is_active_on_district": True,
        "data_sources": ["tmdb", "newsapi"],
        "external_ids": {"tmdb_name": "Stree 2"},
        "description": "Rajkummar Rao / Shraddha Kapoor blockbuster; ₹600Cr+ first week.",
    },
    {
        "name": "Avengers: Doomsday",
        "entity_type": EntityType.MOVIE.value,
        "category": "Hollywood",
        "sub_categories": ["Superhero", "Marvel", "Action"],
        "genre": "Action",
        "genres": ["Action", "Superhero", "Marvel"],
        "country": "United States",
        "primary_market": "Global",
        "is_verified": True, "is_international": True, "is_active_on_district": False,
        "data_sources": ["tmdb"],
        "external_ids": {"tmdb_name": "Avengers Doomsday"},
        "description": "Marvel mega-event; expected India premiere screenings + fan events.",
    },

    # ── THEATRE / CULTURE ────────────────────────────────────────────────────
    {
        "name": "Qismat Ka Khel",
        "entity_type": EntityType.THEATRE_GROUP.value,
        "category": "Theatre",
        "sub_categories": ["Hindi Theatre", "Drama"],
        "genre": "Drama",
        "genres": ["Drama", "Hindi"],
        "country": "India", "home_city": "Mumbai",
        "primary_market": "India",
        "is_verified": False, "is_international": False, "is_active_on_district": True,
        "data_sources": ["newsapi"],
        "external_ids": {},
        "description": "Popular Hindi theatre production touring metro cities.",
    },
]

# ─── Additional quick-add entities (less detailed) ───────────────────────────
QUICK_ENTITIES = [
    # More music
    ("Jasleen Royal", EntityType.ARTIST.value, "Bollywood", "India", False),
    ("Jubin Nautiyal", EntityType.ARTIST.value, "Bollywood", "India", False),
    ("Sonu Nigam", EntityType.ARTIST.value, "Bollywood", "India", False),
    ("Neha Kakkar", EntityType.ARTIST.value, "Bollywood", "India", False),
    ("Badshah", EntityType.ARTIST.value, "Punjabi Pop", "India", False),
    ("Hardwell", EntityType.ARTIST.value, "International EDM", "Netherlands", True),
    ("Alan Walker", EntityType.ARTIST.value, "International EDM", "Norway", True),
    ("Dua Lipa", EntityType.ARTIST.value, "International Pop", "United Kingdom", True),
    ("BLACKPINK", EntityType.ARTIST.value, "K-Pop", "South Korea", True),
    ("Nucleya", EntityType.ARTIST.value, "Indian EDM", "India", False),
    ("Divine", EntityType.ARTIST.value, "Indian Hip-Hop", "India", False),
    ("Raftaar", EntityType.ARTIST.value, "Indian Hip-Hop", "India", False),
    ("Ustad Zakir Hussain", EntityType.ARTIST.value, "Classical", "India", True),
    # Comedy
    ("Kapil Sharma", EntityType.COMEDIAN.value, "Stand-Up Comedy", "India", False),
    ("Kanan Gill", EntityType.COMEDIAN.value, "Stand-Up Comedy", "India", False),
    ("Kunal Kamra", EntityType.COMEDIAN.value, "Stand-Up Comedy", "India", False),
    ("Russell Peters", EntityType.COMEDIAN.value, "International Stand-Up", "Canada", True),
    # Sports
    ("Delhi Capitals", EntityType.SPORTS_TEAM.value, "Cricket", "India", False),
    ("Chennai Super Kings", EntityType.SPORTS_TEAM.value, "Cricket", "India", False),
    ("Mumbai City FC", EntityType.SPORTS_TEAM.value, "Football", "India", False),
    # More movies
    ("Kalki 2898-AD", EntityType.MOVIE.value, "South Indian", "India", False),
    ("Fighter", EntityType.MOVIE.value, "Bollywood", "India", False),
]


async def seed_entities():
    print("=" * 60)
    print("  LiveIQ — Entity Seed Script (Sprint 2A)")
    print("=" * 60)

    async with AsyncSessionLocal() as session:

        # Check if already seeded
        existing = await session.execute(select(Entity).limit(1))
        if existing.scalar_one_or_none():
            count_result = await session.execute(select(Entity))
            existing_count = len(count_result.scalars().all())
            print(f"\n  Already seeded: {existing_count} entities in DB.")
            print("  Skipping to avoid duplicates.")
            print("  To re-seed, clear the entities table first.")
            return existing_count

        inserted = 0

        # Seed detailed entities
        print(f"\n  Seeding {len(ENTITIES)} detailed entities...")
        for data in ENTITIES:
            entity = Entity(
                name=data["name"],
                entity_type=data["entity_type"],
                category=data.get("category"),
                sub_categories=data.get("sub_categories", []),
                genre=data.get("genre"),
                genres=data.get("genres", []),
                country=data.get("country"),
                home_city=data.get("home_city"),
                home_state=data.get("home_state"),
                primary_market=data.get("primary_market", "India"),
                is_verified=data.get("is_verified", False),
                is_international=data.get("is_international", False),
                is_active_on_district=data.get("is_active_on_district", False),
                is_featured=data.get("is_featured", False),
                data_sources=data.get("data_sources", []),
                external_ids=data.get("external_ids", {}),
                description=data.get("description"),
                booking_price_range_min=data.get("booking_price_range_min"),
                booking_price_range_max=data.get("booking_price_range_max"),
                typical_venue_capacity_min=data.get("typical_venue_capacity_min"),
                typical_venue_capacity_max=data.get("typical_venue_capacity_max"),
                status=EntityStatus.ACTIVE.value,
            )
            session.add(entity)
            inserted += 1
            print(f"    + {data['name']} [{data['entity_type']}]")

        # Seed quick entities
        print(f"\n  Seeding {len(QUICK_ENTITIES)} additional entities...")
        for name, etype, category, country, is_intl in QUICK_ENTITIES:
            entity = Entity(
                name=name,
                entity_type=etype,
                category=category,
                country=country,
                is_international=is_intl,
                is_active_on_district=True,
                primary_market="India",
                status=EntityStatus.ACTIVE.value,
                data_sources=["lastfm"] if etype == EntityType.ARTIST.value else ["newsapi"],
                external_ids={},
            )
            session.add(entity)
            inserted += 1

        await session.commit()

        print(f"\n  {'=' * 55}")
        print(f"  DONE — {inserted} entities seeded into NeonDB!")
        print(f"  {'=' * 55}")
        return inserted


if __name__ == "__main__":
    count = asyncio.run(seed_entities())
    sys.exit(0 if count > 0 else 1)
