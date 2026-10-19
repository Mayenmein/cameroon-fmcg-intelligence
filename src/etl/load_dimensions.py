# scripts/load_dimensions.py
import pandas as pd
from sqlalchemy import text
from pathlib import Path
from typing import Literal, Any
from sqlalchemy.exc import SQLAlchemyError

from src.etl.build_dimensions import build_dim_date, build_dim_region, build_dim_market, build_dim_product
from src.db.connection import get_engine
from src.config.settings import Settings
settings = Settings()

def load_parquet(parquet_path: Path, table_name: str, 
                 if_exists: Literal["replace", "append"] = "replace", chunksize: int = 1000):
    """Load a Parquet file into a Postgres table."""
    df = pd.read_parquet(parquet_path)
    engine = get_engine()

    if if_exists == "replace":
        with engine.begin() as conn:
            # TRUNCATE with RESTART IDENTITY resets SERIAL sequences so IDs start cleanly at 1
            conn.execute(text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE'))
        if_exists = "append"

    try:
        df.to_sql(
            table_name, engine,
            if_exists=if_exists, index=False,
            chunksize=chunksize, method=None,
        )
        print(f"Loaded {len(df):,} rows into {table_name}")
    except SQLAlchemyError as e:
        print(f"\n=== {table_name} load failed ===")
        print(f"Type:    {type(e).__name__}")
        print(f"Orig:    {type(getattr(e, 'orig', None)).__name__}")
        print(f"Message: {str(getattr(e, 'orig', e))[:500]}")
        raise


def row_count(table_name: str) -> Any:
    """Return the number of rows in a Postgres table.
    Args:
        table_name (str): The name of the table to count rows for."""
    with get_engine().connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()


def main():
    """Main function to build and load dimension tables."""
    # 1. Build the dimensions on disk
    build_dim_date()
    build_dim_region()
    build_dim_market()
    build_dim_product()

    # 2. Load them into Postgres in dependency order (using replace + sequence reset)
    load_parquet(settings.data_processed_dir / "dim_date.parquet", "dim_date", if_exists="replace")
    load_parquet(settings.data_processed_dir / "dim_region.parquet", "dim_region", if_exists="replace")
    load_parquet(settings.data_processed_dir / "dim_market.parquet", "dim_market", if_exists="replace")
    load_parquet(settings.data_processed_dir / "dim_product.parquet", "dim_product", if_exists="replace")
    
    # 3. Confirm
    print("\nRow counts:")
    print(f"  dim_date:   {row_count('dim_date'):,}")
    print(f"  dim_region: {row_count('dim_region'):,}")
    print(f"  dim_market: {row_count('dim_market'):,}")
    print(f"  dim_product: {row_count('dim_product'):,}")


if __name__ == "__main__":
    main()