
import os
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from src.config.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data" / "processed" / "inventory_full_run_revised1"

DATABASE_URL = Settings().database_url 

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Set DATABASE_URL to run PostgreSQL integration tests.",
)


@pytest.fixture(scope="module")
def db():
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        yield engine
    finally:
        engine.dispose()


def read_table(db, table):
    # Table names are fixed by the tests, not user input.
    return pd.read_sql(
        text(f'SELECT * FROM "{table}"'),
        db,
    )


def read_parquet(name):
    return pd.read_parquet(SIM_DIR / f"{name}.parquet")


def test_required_tables_exist(db):
    expected = {
        "dim_product",
        "dim_customer",
        "dim_date",
        "fact_sales",
        "fact_inventory_snapshot",
        "fact_inventory_movements",
        "fact_purchase_orders",
        "fact_delivery_events",
        "fact_stockout_events",
    }

    with db.connect() as connection:
        actual = set(
            connection.execute(
                text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
            ).scalars()
        )

    assert expected <= actual


def test_product_dimension_matches_simulation(db):
    products = read_table(db, "dim_product")
    sales = read_parquet("sim_sales")

    assert not products["product_id"].duplicated().any()
    assert products["product_name"].notna().all()

    simulated_ids = set(sales["product_id"].unique())
    database_ids = set(products["product_id"])

    assert simulated_ids <= database_ids


def test_sales_row_count_and_reconciliation(db):
    simulated = read_parquet("sim_sales")

    with db.connect() as connection:
        result = connection.execute(
            text("""
                SELECT
                    COUNT(*) AS row_count,
                    COALESCE(SUM(demand_qty), 0) AS demand,
                    COALESCE(SUM(quantity), 0) AS fulfilled,
                    COALESCE(SUM(lost_sales_qty), 0) AS lost
                FROM fact_sales
            """)
        ).mappings().one()

    assert result["row_count"] == len(simulated)
    assert result["demand"] == pytest.approx(
        simulated["demand_qty"].sum()
    )
    assert result["fulfilled"] == pytest.approx(
        simulated["sales_qty"].sum()
    )
    assert result["lost"] == pytest.approx(
        simulated["lost_sales_qty"].sum()
    )

    assert (
        simulated["demand_qty"]
        == simulated["sales_qty"] + simulated["lost_sales_qty"]
    ).all()


@pytest.mark.parametrize(
    ("parquet_name", "table_name", "columns"),
    [
        (
            "sim_inventory_snapshot",
            "fact_inventory_snapshot",
            [
                "date", "product_id", "opening_stock", "arrivals_qty",
                "demand_qty", "sales_qty", "lost_sales_qty",
                "closing_stock", "on_order_qty", "inventory_position",
            ],
        ),
        (
            "sim_purchase_orders",
            "fact_purchase_orders",
            [
                "order_id", "order_date", "arrival_date",
                "product_id", "quantity", "lead_time_days",
            ],
        ),
        (
            "sim_delivery_events",
            "fact_delivery_events",
            [
                "order_id", "product_id", "arrival_date",
                "quantity_received",
            ],
        ),
        (
            "sim_inventory_movements",
            "fact_inventory_movements",
            [
                "date", "product_id", "movement_type",
                "quantity_change", "reference_id", "on_hand_after",
            ],
        ),
        (
            "sim_stockout_events",
            "fact_stockout_events",
            [
                "date", "customer_id", "product_id",
                "demand_qty", "fulfilled_qty", "lost_sales_qty",
            ],
        ),
    ],
)
def test_fact_table_row_counts_match_parquet(
    db, parquet_name, table_name, columns
):
    simulated = read_parquet(parquet_name)
    stored = read_table(db, table_name)

    assert set(columns) <= set(simulated.columns)
    assert set(columns) <= set(stored.columns)
    assert len(stored) == len(simulated)


def test_inventory_snapshots_match_parquet(db):
    simulated = read_parquet("sim_inventory_snapshot")
    stored = read_table(db, "fact_inventory_snapshot")

    keys = ["date", "product_id"]
    numeric = [
        "opening_stock", "arrivals_qty", "demand_qty",
        "sales_qty", "lost_sales_qty", "closing_stock",
        "on_order_qty", "inventory_position",
    ]

    simulated["date"] = pd.to_datetime(simulated["date"]).dt.normalize()
    stored["date"] = pd.to_datetime(stored["date"]).dt.normalize()

    assert not stored.duplicated(keys).any()

    merged = simulated.merge(
        stored,
        on=keys,
        how="outer",
        suffixes=("_file", "_db"),
        indicator=True,
        validate="one_to_one",
    )

    assert (merged["_merge"] == "both").all()

    for column in numeric:
        assert merged[f"{column}_file"].tolist() == pytest.approx(
            merged[f"{column}_db"].tolist()
        )


def test_purchase_orders_match_parquet(db):
    simulated = read_parquet("sim_purchase_orders")
    stored = read_table(db, "fact_purchase_orders")

    keys = ["order_id"]
    columns = [
        "order_date", "arrival_date", "product_id",
        "quantity", "lead_time_days",
    ]

    assert not stored.duplicated(keys).any()

    simulated["order_date"] = pd.to_datetime(
        simulated["order_date"]
    ).dt.normalize()
    simulated["arrival_date"] = pd.to_datetime(
        simulated["arrival_date"]
    ).dt.normalize()
    stored["order_date"] = pd.to_datetime(
        stored["order_date"]
    ).dt.normalize()
    stored["arrival_date"] = pd.to_datetime(
        stored["arrival_date"]
    ).dt.normalize()

    merged = simulated.merge(
        stored,
        on=keys,
        how="outer",
        suffixes=("_file", "_db"),
        indicator=True,
        validate="one_to_one",
    )

    assert (merged["_merge"] == "both").all()

    for column in columns:
        left = merged[f"{column}_file"]
        right = merged[f"{column}_db"]

        if column == "quantity":
            assert left.tolist() == pytest.approx(right.tolist())
        else:
            pd.testing.assert_series_equal(
                left.reset_index(drop=True),
                right.reset_index(drop=True),
                check_names=False,
            )


def test_foreign_keys_have_no_orphans(db):
    checks = {
        "fact_sales_product": """
            SELECT COUNT(*) FROM fact_sales f
            LEFT JOIN dim_product d ON f.product_id = d.product_id
            WHERE d.product_id IS NULL
        """,
        "fact_sales_customer": """
            SELECT COUNT(*) FROM fact_sales f
            LEFT JOIN dim_customer d ON f.customer_id = d.customer_id
            WHERE d.customer_id IS NULL
        """,
        "snapshot_product": """
            SELECT COUNT(*) FROM fact_inventory_snapshot f
            LEFT JOIN dim_product d ON f.product_id = d.product_id
            WHERE d.product_id IS NULL
        """,
        "orders_product": """
            SELECT COUNT(*) FROM fact_purchase_orders f
            LEFT JOIN dim_product d ON f.product_id = d.product_id
            WHERE d.product_id IS NULL
        """,
        "deliveries_order": """
            SELECT COUNT(*) FROM fact_delivery_events f
            LEFT JOIN fact_purchase_orders o ON f.order_id = o.order_id
            WHERE o.order_id IS NULL
        """,
        "stockouts_customer": """
            SELECT COUNT(*) FROM fact_stockout_events f
            LEFT JOIN dim_customer d ON f.customer_id = d.customer_id
            WHERE d.customer_id IS NULL
        """,
    }

    with db.connect() as connection:
        for name, query in checks.items():
            count = connection.execute(text(query)).scalar_one()
            assert count == 0, f"{name}: found {count} orphan records"


def test_database_inventory_values_are_valid(db):
    queries = {
        "negative_closing_stock": """
            SELECT COUNT(*) FROM fact_inventory_snapshot
            WHERE closing_stock < 0
        """,
        "incorrect_inventory_position": """
            SELECT COUNT(*) FROM fact_inventory_snapshot
            WHERE inventory_position <> closing_stock + on_order_qty
        """,
        "invalid_order_dates": """
            SELECT COUNT(*) FROM fact_purchase_orders
            WHERE arrival_date < order_date
        """,
        "invalid_sales_reconciliation": """
            SELECT COUNT(*) FROM fact_sales
            WHERE demand_qty <> quantity + lost_sales_qty
        """,
        "invalid_stockout_reconciliation": """
            SELECT COUNT(*) FROM fact_stockout_events
            WHERE demand_qty <> fulfilled_qty + lost_sales_qty
        """,
    }

    with db.connect() as connection:
        for name, query in queries.items():
            count = connection.execute(text(query)).scalar_one()
            assert count == 0, f"{name}: found {count} invalid records"
