# scripts/build_database.py
from pathlib import Path
from sqlalchemy import create_engine, text
from src.config.settings import settings


def _admin_engine():
    url = (
        f"postgresql+psycopg2://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/postgres"
    )
    return create_engine(url, isolation_level="AUTOCOMMIT", future=True)


def _target_engine():
    return create_engine(settings.database_url, future=True)


def create_database_if_missing() -> None:
    with _admin_engine().connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": settings.db_name},
        ).scalar()
        if exists:
            print(f"Database '{settings.db_name}' already exists.")
        else:
            conn.execute(text(f'CREATE DATABASE "{settings.db_name}"'))
            print(f"Created database '{settings.db_name}'.")


def apply_schema(schema_path: Path = Path("src/db/schema.sql")) -> None:
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    with _target_engine().begin() as conn:
        conn.exec_driver_sql(schema_path.read_text())
    print(f"Schema applied from {schema_path}")


def list_tables() -> None:
    with _target_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name;
        """)).fetchall()
    print(f"\nTables in '{settings.db_name}' ({len(rows)}):")
    for (name,) in rows:
        print(f"  - {name}")


def build_database() -> None:
    create_database_if_missing()
    apply_schema()
    list_tables()


if __name__ == "__main__":
    build_database()