
from pathlib import Path

import pandas as pd
from tqdm import tqdm
from sqlalchemy import text

from src.etl.build_facts import build_fact_market_price, build_fact_trade
from src.db.connection import get_engine


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
SIM_DIR = PROCESSED / "inventory_full_run_revised1"

# Only allow known table names in SQL statements.
ALLOWED_TABLES = {
    "dim_wfp_market",
    "fact_market_price",
    "fact_trade",
    "fact_sales",
    "fact_inventory_snapshot",
    "fact_inventory_movements",
    "fact_purchase_orders",
    "fact_delivery_events",
    "fact_stockout_events",
}


def load_parquet(parquet_path, table_name, chunksize=5000, truncate=True):
    """Load a Parquet file into an existing PostgreSQL table."""
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"Unexpected table name: {table_name}")

    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    engine = get_engine()

    if df.empty:
        print(f"Skipped empty file: {parquet_path}")
        return

    if truncate:
        with engine.begin() as conn:
            conn.execute(
                text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY')
            )

    df.to_sql(
        table_name,
        engine,
        if_exists="append",
        index=False,
        chunksize=chunksize,
        method=None,
    )

    print(f"Loaded {len(df):,} rows into {table_name}")


def prepare_simulated_sales():
    """Map simulator sales columns to the PostgreSQL fact_sales schema."""
    sales_path = SIM_DIR / "sim_sales.parquet"

    if not sales_path.exists():
        raise FileNotFoundError(f"Simulator sales not found: {sales_path}")

    sales = pd.read_parquet(sales_path)
    engine = get_engine()

    required = {
        "date_id",
        "customer_id",
        "product_id",
        "demand_qty",
        "sales_qty",
        "lost_sales_qty",
    }

    missing = required - set(sales.columns)
    if missing:
        raise ValueError(f"sim_sales.parquet is missing columns: {sorted(missing)}")

    if sales.empty:
        raise ValueError("sim_sales.parquet contains no records.")

    # Verify that simulated customer IDs exist in PostgreSQL.
    customers = pd.read_sql(
        text("SELECT customer_id, region_id, market_id FROM dim_customer"),
        engine,
    )

    if customers["customer_id"].duplicated().any():
        raise ValueError("dim_customer contains duplicate customer IDs.")

    sales = sales.merge(
        customers,
        on="customer_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    unmatched = sales["_merge"] != "both"
    if unmatched.any():
        ids = sales.loc[unmatched, "customer_id"].unique()[:10].tolist()
        raise ValueError(
            f"Simulator customer IDs are missing from dim_customer. "
            f"Example IDs: {ids}"
        )

    sales.drop(columns="_merge", inplace=True)

    # Verify demand reconciliation before inserting.
    if not (
        sales["demand_qty"]
        == sales["sales_qty"] + sales["lost_sales_qty"]
    ).all():
        raise ValueError(
            "Sales reconciliation failed: demand_qty must equal "
            "sales_qty + lost_sales_qty."
        )

    # Map simulator fields to fact_sales columns.
    sales["quantity"] = sales["sales_qty"]
    sales["unit_price"] = None  # Simulator does not generate prices.
    sales["discount"] = 0.0

    # Exclude simulator-only columns and PostgreSQL-generated sale_id/revenue.
    return sales[
        [
            "date_id",
            "product_id",
            "customer_id",
            "region_id",
            "market_id",
            "demand_qty",
            "quantity",
            "lost_sales_qty",
            "unit_price",
            "discount",
        ]
    ]

def load_simulated_sales():
    sales = prepare_simulated_sales()
    engine = get_engine()
    chunksize = 5000
    total = len(sales)

    with engine.begin() as conn:
        for start in tqdm(
            range(0, total, chunksize),
            desc="Loading fact_sales",
            unit="batch",
        ):
            batch = sales.iloc[start:start + chunksize]

            batch.to_sql(
                "fact_sales",
                conn,
                if_exists="append",
                index=False,
                method=None,
            )

    print(f"Loaded {total:,} rows into fact_sales")

def clear_simulator_tables():
    """Clear simulator outputs together, without CASCADE."""
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(
            text("""
                TRUNCATE TABLE
                    fact_delivery_events,
                    fact_purchase_orders,
                    fact_sales,
                    fact_stockout_events,
                    fact_inventory_movements,
                    fact_inventory_snapshot
                RESTART IDENTITY
            """)
        )



def main():
    # Build the public-data fact files.
    build_fact_market_price()
    build_fact_trade()

    # Clear public-data tables in foreign-key-safe order.
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            TRUNCATE TABLE fact_market_price, dim_wfp_market
            RESTART IDENTITY
        """))
        conn.execute(text("TRUNCATE TABLE fact_trade"))

    # Load public market and trade data.
    load_parquet(
        PROCESSED / "dim_wfp_market.parquet",
        "dim_wfp_market",
        truncate=False,
    )
    load_parquet(
        PROCESSED / "fact_market_price.parquet",
        "fact_market_price",
        truncate=False,
    )
    load_parquet(
        PROCESSED / "fact_trade.parquet",
        "fact_trade",
        truncate=False,
    )

    # Validate customer mappings before clearing simulator tables.
    prepared_sales = prepare_simulated_sales()

    # Clear previous simulator outputs before reloading.
    clear_simulator_tables()

    # Load simulated sales.
    prepared_sales.to_sql(
        "fact_sales",
        engine,
        if_exists="append",
        index=False,
        chunksize=5000,
        method=None,
    )
    print(f"Loaded {len(prepared_sales):,} rows into fact_sales")

    # Load inventory snapshots and movements.
    load_parquet(
        SIM_DIR / "sim_inventory_snapshot.parquet",
        "fact_inventory_snapshot",
        truncate=False,
    )
    load_parquet(
        SIM_DIR / "sim_inventory_movements.parquet",
        "fact_inventory_movements",
        truncate=False,
    )

    # Load purchase orders before dependent delivery events.
    load_parquet(
        SIM_DIR / "sim_purchase_orders.parquet",
        "fact_purchase_orders",
        truncate=False,
    )
    load_parquet(
        SIM_DIR / "sim_delivery_events.parquet",
        "fact_delivery_events",
        truncate=False,
    )

    # Load stockout events.
    load_parquet(
        SIM_DIR / "sim_stockout_events.parquet",
        "fact_stockout_events",
        truncate=False,
    )

    print("Database loading completed.")

if __name__ == "__main__":
    main()
