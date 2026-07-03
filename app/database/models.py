from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class SearchCache(Base):
    """Caches raw search queries mapped to resolved AniList details."""
    __tablename__ = "search_cache"

    id = Column(Integer, primary_key=True)
    query_text = Column(String(255), unique=True, nullable=False, index=True)
    anilist_id = Column(Integer, nullable=False)
    title_english = Column(String(500), nullable=True)
    title_romaji = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class EpisodeCache(Base):
    """Caches episode lists for resolved anime."""
    __tablename__ = "episode_cache"

    id = Column(Integer, primary_key=True)
    anilist_id = Column(Integer, nullable=False, index=True)
    ep_number = Column(String(50), nullable=False)  # Keep string to support specials like '1.5' or 'OVA'
    play_url = Column(String(1000), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DownloadCache(Base):
    """Caches direct file download URLs per episode play URL."""
    __tablename__ = "download_cache"

    id = Column(Integer, primary_key=True)
    play_url = Column(String(1000), unique=True, nullable=False, index=True)
    qualities = Column(JSON, nullable=False)  # Format: {"1080p": "url1", "720p": "url2", ...}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
