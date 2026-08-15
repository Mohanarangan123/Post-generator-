"""
Database engine and session management.

Provides:
- `engine`: SQLAlchemy engine built from the configured DATABASE_URL
- `SessionLocal`: session factory for request-scoped DB sessions
- `get_db`: FastAPI dependency that yields a DB session
- `check_db_connection`: lightweight connectivity check used by /status
"""
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# pool_pre_ping ensures stale connections are detected and refreshed
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db():
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> tuple[bool, str]:
    """
    Attempt a simple connection + query against the database.

    Returns:
        (is_connected, message)
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "Database connection successful"
    except Exception as exc:  # noqa: BLE001 - we want to report any failure reason
        logger.error("Database connection check failed: %s", exc)
        return False, f"Database connection failed: {exc}"
