
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data" / "processed" / "inventory_full_run_revised1"

EXPECTED_COLUMNS = {
    "sim_sales": {
        "date", "date_id", "customer_id", "product_id", "product_name",
        "demand_qty", "sales_qty", "lost_sales_qty",
    },
    "sim_stockout_events": {
        "date", "customer_id", "product_id",
        "demand_qty", "fulfilled_qty", "lost_sales_qty",
    },
    "sim_inventory_snapshot": {
        "date", "product_id", "opening_stock",
        "arrivals_qty", "demand_qty", "sales_qty", "lost_sales_qty",
        "closing_stock", "on_order_qty", "inventory_position",
    },
    "sim_inventory_movements": {
        "date", "product_id", "movement_type", "quantity_change",
        "reference_id", "on_hand_after",
    },
    "sim_purchase_orders": {
        "order_id", "order_date", "arrival_date", "product_id",
        "quantity", "lead_time_days",
    },
    "sim_delivery_events": {
        "order_id", "product_id",
        "arrival_date", "quantity_received",
    },
}


@pytest.fixture(scope="module")
def outputs():
    """Load the existing simulator outputs once for this test module."""
    assert SIM_DIR.is_dir(), (
        f"Simulator output directory not found: {SIM_DIR}. "
        "Run the simulator before running these tests."
    )

    frames = {}

    for name, expected_columns in EXPECTED_COLUMNS.items():
        path = SIM_DIR / f"{name}.parquet"

        assert path.is_file(), f"Missing simulator output: {path}"

        frame = pd.read_parquet(path)
        print(name,frame.columns)
        assert not frame.empty, f"{name} is unexpectedly empty"
        assert set(frame.columns) == expected_columns, (
            f"Unexpected columns in {name}"
        )

        frames[name] = frame

    return frames


def test_sales_reconcile_with_demand(outputs):
    sales = outputs["sim_sales"]

    assert sales[
        ["demand_qty", "sales_qty", "lost_sales_qty"]
    ].notna().all().all()

    assert (sales["demand_qty"] >= 0).all()
    assert (sales["sales_qty"] >= 0).all()
    assert (sales["lost_sales_qty"] >= 0).all()
    assert (sales["sales_qty"] <= sales["demand_qty"]).all()

    assert (
        sales["sales_qty"] + sales["lost_sales_qty"]
        == sales["demand_qty"]
    ).all()


def test_inventory_balances_reconcile(outputs):
    inventory = outputs["sim_inventory_snapshot"]

    assert not inventory.duplicated(["date", "product_id"]).any()

    quantity_columns = [
        "opening_stock", "arrivals_qty", "demand_qty", "sales_qty",
        "lost_sales_qty", "closing_stock", "on_order_qty",
        "inventory_position",
    ]

    assert inventory[quantity_columns].notna().all().all()

    for column in quantity_columns:
        assert (inventory[column] >= 0).all(), (
            f"Negative quantity in {column}"
        )

    expected_closing_stock = (
        inventory["opening_stock"]
        + inventory["arrivals_qty"]
        - inventory["sales_qty"]
    )

    pd.testing.assert_series_equal(
        inventory["closing_stock"].reset_index(drop=True),
        expected_closing_stock.reset_index(drop=True),
        check_names=False,
    )

    expected_position = (
        inventory["closing_stock"] + inventory["on_order_qty"]
    )

    pd.testing.assert_series_equal(
        inventory["inventory_position"].reset_index(drop=True),
        expected_position.reset_index(drop=True),
        check_names=False,
    )

    assert (
        inventory["sales_qty"] <= inventory["demand_qty"]
    ).all()

    assert (
        inventory["sales_qty"] + inventory["lost_sales_qty"]
        == inventory["demand_qty"]
    ).all()


def test_stockout_events_are_consistent_with_sales(outputs):
    sales = outputs["sim_sales"]
    stockouts = outputs["sim_stockout_events"]

    assert (stockouts["demand_qty"] > 0).all()
    assert (stockouts["fulfilled_qty"] >= 0).all()
    assert (stockouts["lost_sales_qty"] > 0).all()

    assert (
        stockouts["fulfilled_qty"] + stockouts["lost_sales_qty"]
        == stockouts["demand_qty"]
    ).all()

    assert stockouts["lost_sales_qty"].sum() == sales[
        "lost_sales_qty"
    ].sum()


def test_purchase_orders_are_valid(outputs):
    orders = outputs["sim_purchase_orders"]

    assert not orders["order_id"].duplicated().any()
    assert (orders["quantity"] > 0).all()
    assert (orders["lead_time_days"] >= 0).all()

    assert (
        pd.to_datetime(orders["arrival_date"])
        >= pd.to_datetime(orders["order_date"])
    ).all()


def test_deliveries_reference_valid_orders(outputs):
    orders = outputs["sim_purchase_orders"]
    deliveries = outputs["sim_delivery_events"]

    assert (deliveries["quantity_received"] > 0).all()
    assert deliveries["order_id"].isin(orders["order_id"]).all()

    order_details = orders[
        ["order_id", "product_id", "quantity", "arrival_date"]
    ].rename(columns={"arrival_date": "scheduled_arrival_date"})

    linked = deliveries.merge(
        order_details,
        on="order_id",
        how="left",
        validate="many_to_one",
        suffixes=("_delivery", "_order"),
        indicator=True,
    )

    assert (linked["_merge"] == "both").all()
    assert (
        linked["product_id_delivery"] == linked["product_id_order"]
    ).all()

    # An order may remain outstanding after the simulation horizon.
    received = deliveries.groupby("order_id")[
        "quantity_received"
    ].sum()

    ordered = orders.set_index("order_id")["quantity"]

    assert (received <= ordered.loc[received.index]).all()


def test_inventory_snapshots_cover_simulation_dates(outputs):
    inventory = outputs["sim_inventory_snapshot"]

    dates = pd.to_datetime(inventory["date"])
    assert dates.notna().all()

    # Each simulated date should have one snapshot per simulated product.
    products_per_date = inventory.groupby("date")["product_id"].nunique()
    assert products_per_date.nunique() == 1


def test_inventory_movements_have_valid_balances(outputs):
    movements = outputs["sim_inventory_movements"]

    assert movements["date"].notna().all()
    assert movements["product_id"].notna().all()
    assert movements["movement_type"].notna().all()
    assert movements["quantity_change"].notna().all()
    assert movements["on_hand_after"].notna().all()
    assert (movements["on_hand_after"] >= 0).all()


def test_output_tables_are_nonempty(outputs):
    """Basic regression check that every expected output was generated."""
    for name, frame in outputs.items():
        assert len(frame) > 0, f"{name} contains no records"
