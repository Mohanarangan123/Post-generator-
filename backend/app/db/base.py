"""
SQLAlchemy declarative base.

All ORM models (created in future phases) should inherit from `Base`
so that Alembic autogeneration can discover them via this metadata.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base class for all ORM models."""
    pass
