from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, JSON, Text, func, UniqueConstraint, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class SearchCache(Base):
    """Caches raw search queries mapped to resolved AniList details."""
    __tablename__ = "search_cache"

    id = Column(Integer, primary_key=True)
    query_text = Column(String(255), nullable=False, index=True)
    anilist_id = Column(Integer, nullable=False, index=True)
    title_english = Column(String(500), nullable=True)
    title_romaji = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(1000), nullable=True)
    duration = Column(String(100), nullable=True)
    synonyms = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('query_text', 'anilist_id', name='_query_anilist_uc'),
    )

class TelegramFileCache(Base):
    """Caches Telegram file_id for zero-second instant delivery across server crashes/restarts."""
    __tablename__ = "telegram_file_cache"

    id = Column(Integer, primary_key=True)
    anilist_id = Column(BigInteger, nullable=False, index=True)
    ep_number = Column(String(50), nullable=False, index=True)
    quality = Column(String(50), nullable=False, index=True)
    file_id = Column(String(500), nullable=False)
    file_size = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('anilist_id', 'ep_number', 'quality', name='_anilist_ep_quality_uc'),
    )

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
    duration = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserFavorites(Base):
    """Stores user's favorite/saved anime series."""
    __tablename__ = "user_favorites"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    anilist_id = Column(Integer, nullable=False)
    anime_title = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'anilist_id', name='_user_anime_fav_uc'),
    )


class BotAdmin(Base):
    """Stores dynamically added bot administrators."""
    __tablename__ = "bot_admins"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    added_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """Tracks all interacting user accounts for tracking system metrics and global broadcasting."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_blocked = Column(Boolean, default=False, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AnimeTopicCache(Base):
    """Maps series to their specific forum topic in the library group."""
    __tablename__ = "anime_topic_cache"

    anilist_id = Column(BigInteger, primary_key=True, index=True)
    topic_id = Column(Integer, nullable=False)


class PersistentTaskQueue(Base):
    """Tracks ongoing background jobs securely across server restarts."""
    __tablename__ = "persistent_task_queue"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    message_id = Column(Integer, nullable=True)  # Status message to edit
    anilist_id = Column(BigInteger, nullable=False)
    anime_title = Column(String(500), nullable=False)
    episode_num = Column(String(50), nullable=False)
    quality = Column(String(50), nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # pending, processing, completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SystemSettings(Base):
    """Stores persistent configuration settings like custom thumbnails and channel verification settings."""
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True, index=True)
    value = Column(Text, nullable=True)


class Blacklist(Base):
    """Stores banned user IDs to prevent unauthorized access or structural tampering."""
    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    reason = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


