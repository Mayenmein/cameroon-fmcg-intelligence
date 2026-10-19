# src/db/connection.py
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.config.settings import settings


def get_engine() -> Engine:
    """Return a SQLAlchemy engine connected to the configured Postgres database."""
    return create_engine(settings.database_url, future=True)