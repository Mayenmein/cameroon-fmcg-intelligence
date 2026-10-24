from sqlalchemy import text
import pandas as pd

from src.etl.build_facts import build_fact_market_price, build_fact_trade
from src.db.connection import get_engine


def load_parquet(parquet_path, table_name, chunksize=5000):
    df = pd.read_parquet(parquet_path)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE'))
    df.to_sql(
        table_name, engine,
        if_exists="append", index=False,
        chunksize=chunksize, method=None,
    )
    print(f"Loaded {len(df):,} rows into {table_name}")


def main():
    build_fact_market_price()
    build_fact_trade()

    load_parquet(
        "data/processed/dim_wfp_market.parquet",
        "dim_wfp_market",
    )
    load_parquet(
        "data/processed/fact_market_price.parquet",
        "fact_market_price",
    )
    load_parquet(
        "data/processed/fact_trade.parquet",
        "fact_trade",
    )

if __name__ == "__main__":
    main()