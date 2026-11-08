"""Hosting dashboards (Hugging Face, etc.) often append a newline when a secret is pasted."""
from app.core.config import Settings


def test_string_settings_are_stripped(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql+asyncpg://u:p@host/neondb\n")
    monkeypatch.setenv("POSTGRES_SYNC_URL", "  postgresql://u:p@host/neondb  \n")
    monkeypatch.setenv("SECRET_KEY", "k" * 40 + "\n")
    monkeypatch.setenv("GROQ_API_KEY", " gsk_abc \n")
    s = Settings(_env_file=None)
    assert s.POSTGRES_URL.endswith("/neondb")
    assert s.POSTGRES_SYNC_URL == "postgresql://u:p@host/neondb"
    assert s.SECRET_KEY == "k" * 40
    assert s.GROQ_API_KEY == "gsk_abc"
