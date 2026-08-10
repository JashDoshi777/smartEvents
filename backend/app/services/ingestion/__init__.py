"""
LiveIQ — Ingestion Service Package
Exports all API clients for use in Celery tasks and FastAPI routes.
"""

from app.services.ingestion.base_client import BaseAPIClient
from app.services.ingestion.lastfm_client import LastFMClient       # Replaces Spotify (now requires Premium)
from app.services.ingestion.spotify_client import SpotifyClient     # Kept but requires Spotify Premium
from app.services.ingestion.youtube_client import YouTubeClient
from app.services.ingestion.ticketmaster_client import TicketmasterClient
from app.services.ingestion.tmdb_client import TMDBClient
from app.services.ingestion.reddit_client import RedditClient
from app.services.ingestion.newsapi_client import NewsAPIClient
from app.services.ingestion.google_trends_client import GoogleTrendsClient

__all__ = [
    "BaseAPIClient",
    "LastFMClient",
    "SpotifyClient",
    "YouTubeClient",
    "TicketmasterClient",
    "TMDBClient",
    "RedditClient",
    "NewsAPIClient",
    "GoogleTrendsClient",
]
