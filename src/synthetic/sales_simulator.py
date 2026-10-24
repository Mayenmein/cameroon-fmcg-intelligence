
import json
from pathlib import Path

import pandas as pd
import simpy
import numpy as np
from src.config.settings import Settings


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = Settings().data_processed_dir
CONFIG_PATH = ROOT / "src/config" / "inventory_scenario.json"
OUTPUT_DIR = PROCESSED / "inventory_full_run_revised1"


def load_config(products):
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)

    settings = config["products"]
    actual_names = set(products["product_name"])
    configured_names = set(settings)

    if actual_names != configured_names:
        raise ValueError(
            f"Product configuration mismatch. "
            f"Missing: {sorted(actual_names - configured_names)}; "
            f"unknown: {sorted(configured_names - actual_names)}"
        )

    for name, p in settings.items():
        if not (
            0 <= p["reorder_point"] < p["order_up_to"]
            and 0 <= p["opening_stock"]
            and p["lead_time_days"] >= 1
        ):
            raise ValueError(f"Invalid inventory parameters for {name}")

    return config


def run_inventory_simulation():
    demand = pd.read_parquet(PROCESSED / "sim_demand.parquet")
    products = pd.read_parquet(PROCESSED / "dim_product.parquet")

    demand["date"] = pd.to_datetime(demand["date"]).dt.normalize()

    if demand["demand_qty"].isna().any() or (demand["demand_qty"] < 0).any():
        raise ValueError("Demand contains missing or negative quantities.")

    if not np.all(demand["demand_qty"] == demand["demand_qty"].astype(int)):
        raise ValueError("This simulator expects integer demand quantities.")

    config = load_config(products)
    rng = np.random.default_rng(config["seed"])

    product_names = products.set_index("product_id")["product_name"].to_dict()
    product_ids = list(product_names)
    product_config = {
        pid: config["products"][product_names[pid]]
        for pid in product_ids
    }

    dates = sorted(demand["date"].unique())
    if not dates:
        raise ValueError("Demand dataset contains no dates.")

    # Verify one row per customer-product-day.
    key = ["date", "customer_id", "product_id"]
    if demand.duplicated(key).any():
        raise ValueError("Duplicate customer-product-day demand records.")

    # Pre-group once to avoid rescanning millions of rows each day.
    demand_by_date = {
        pd.Timestamp(date): frame
        for date, frame in demand.groupby("date", sort=True)
    }

    env = simpy.Environment()
    stock = {
        pid: product_config[pid]["opening_stock"]
        for pid in product_ids
    }
    on_order = {pid: 0 for pid in product_ids}
    scheduled_arrivals = {}

    sales_rows = []
    stockout_rows = []
    snapshot_rows = []
    order_rows = []
    delivery_rows = []
    movement_rows = []

    order_id = 0

    # Record initial stock as the opening movement.
    first_date = pd.Timestamp(dates[0])
    for pid in product_ids:
        movement_rows.append({
            "date": first_date,
            "product_id": pid,
            "movement_type": "opening_balance",
            "quantity_change": stock[pid],
            "reference_id": None,
            "on_hand_after": stock[pid],
        })

    def process_days():
        nonlocal order_id

        for day_idx, raw_date in enumerate(dates):
            date = pd.Timestamp(raw_date)

            # Opening stock is measured before today's receipts.
            opening = stock.copy()

            arrivals_today = scheduled_arrivals.pop(day_idx, [])
            received = {pid: 0 for pid in product_ids}

            # 1. Receive deliveries due today.
            for order in arrivals_today:
                pid = order["product_id"]
                qty = order["quantity"]

                stock[pid] += qty
                on_order[pid] -= qty
                received[pid] += qty

                delivery_rows.append({
                    "order_id": order["order_id"],
                    "product_id": pid,
                    "arrival_date": date,
                    "quantity_received": qty,
                })

                movement_rows.append({
                    "date": date,
                    "product_id": pid,
                    "movement_type": "receipt",
                    "quantity_change": qty,
                    "reference_id": order["order_id"],
                    "on_hand_after": stock[pid],
                })

            # 2. Fulfil customer demand in a seeded random order.
            today = demand_by_date[date]
            today = today.iloc[rng.permutation(len(today))]

            daily_demand = {pid: 0 for pid in product_ids}
            daily_sales = {pid: 0 for pid in product_ids}
            daily_lost = {pid: 0 for pid in product_ids}

            for row in today.itertuples(index=False):
                pid = row.product_id
                requested = int(row.demand_qty)
                sold = min(requested, stock[pid])
                lost = requested - sold

                stock[pid] -= sold
                daily_demand[pid] += requested
                daily_sales[pid] += sold
                daily_lost[pid] += lost

                sales_rows.append({
                    "date": date,
                    "date_id": int(row.date_id),
                    "customer_id": row.customer_id,
                    "product_id": pid,
                    "product_name": product_names[pid],
                    "demand_qty": requested,
                    "sales_qty": sold,
                    "lost_sales_qty": lost,
                })

                if sold:
                    movement_rows.append({
                        "date": date,
                        "product_id": pid,
                        "movement_type": "sale",
                        "quantity_change": -sold,
                        "reference_id": None,
                        "on_hand_after": stock[pid],
                    })

                if lost:
                    stockout_rows.append({
                        "date": date,
                        "customer_id": row.customer_id,
                        "product_id": pid,
                        "demand_qty": requested,
                        "fulfilled_qty": sold,
                        "lost_sales_qty": lost,
                    })

            # 3. Reorder based on stock plus outstanding orders.
            for pid in product_ids:
                p = product_config[pid]
                position = stock[pid] + on_order[pid]

                if position <= p["reorder_point"]:
                    qty = p["order_up_to"] - position

                    if qty > 0:
                        order_id += 1
                        lead = p["lead_time_days"]
                        arrival_idx = day_idx + lead

                        # If arrival falls beyond the horizon, it remains
                        # outstanding and is not added to on-hand stock.
                        if arrival_idx < len(dates):
                            arrival_date = pd.Timestamp(dates[arrival_idx])
                        else:
                            arrival_date = (
                                date + pd.Timedelta(days=lead)
                            )

                        order = {
                            "order_id": order_id,
                            "order_date": date,
                            "arrival_date": arrival_date,
                            "arrival_day_idx": arrival_idx,
                            "product_id": pid,
                            "quantity": qty,
                            "lead_time_days": lead,
                        }

                        order_rows.append({
                            k: v for k, v in order.items()
                            if k != "arrival_day_idx"
                        })

                        on_order[pid] += qty
                        scheduled_arrivals.setdefault(
                            arrival_idx, []
                        ).append(order)

            # 4. Record daily inventory and validate conservation.
            for pid in product_ids:
                expected = opening[pid] + received[pid] - daily_sales[pid]

                if stock[pid] != expected:
                    raise AssertionError(
                        f"Inventory conservation failed: "
                        f"date={date}, product={product_names[pid]}, "
                        f"opening={opening[pid]}, receipts={received[pid]}, "
                        f"sales={daily_sales[pid]}, closing={stock[pid]}, "
                        f"expected={expected}"
                    )

                if stock[pid] < 0 or on_order[pid] < 0:
                    raise AssertionError(
                        f"Negative inventory or outstanding orders: "
                        f"{date}, {product_names[pid]}"
                    )

                snapshot_rows.append({
                    "date": date,
                    "product_id": pid,
                    "opening_stock": opening[pid],
                    "arrivals_qty": received[pid],
                    "demand_qty": daily_demand[pid],
                    "sales_qty": daily_sales[pid],
                    "lost_sales_qty": daily_lost[pid],
                    "closing_stock": stock[pid],
                    "on_order_qty": on_order[pid],
                    "inventory_position": stock[pid] + on_order[pid],
                })

            if day_idx < len(dates) - 1:
                yield env.timeout(1)

    env.process(process_days())
    env.run()

    outputs = {
        "sim_sales": pd.DataFrame(sales_rows),
        "sim_stockout_events": pd.DataFrame(stockout_rows),
        "sim_inventory_snapshot": pd.DataFrame(snapshot_rows),
        "sim_purchase_orders": pd.DataFrame(order_rows),
        "sim_delivery_events": pd.DataFrame(delivery_rows),
        "sim_inventory_movements": pd.DataFrame(movement_rows),
    }

    # Final validations.
    sales = outputs["sim_sales"]
    snapshots = outputs["sim_inventory_snapshot"]

    assert (sales["sales_qty"] <= sales["demand_qty"]).all()
    assert (
        sales["sales_qty"] + sales["lost_sales_qty"]
        == sales["demand_qty"]
    ).all()
    assert snapshots["closing_stock"].ge(0).all()

    daily_sales = (
        sales.groupby(["date", "product_id"], as_index=False)
        .agg(
            demand_check=("demand_qty", "sum"),
            sales_check=("sales_qty", "sum"),
            lost_check=("lost_sales_qty", "sum"),
        )
    )
    reconciled = snapshots.merge(
        daily_sales,
        on=["date", "product_id"],
        how="left",
        validate="one_to_one",
    )

    assert (reconciled["demand_qty"] == reconciled["demand_check"]).all()
    assert (reconciled["sales_qty"] == reconciled["sales_check"]).all()
    assert (
        reconciled["lost_sales_qty"] == reconciled["lost_check"]
    ).all()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, frame in outputs.items():
        frame.to_parquet(OUTPUT_DIR / f"{name}.parquet", index=False)

    metadata = {
        "scenario_name": config["scenario_name"],
        "seed": config["seed"],
        "start_date": str(pd.Timestamp(dates[0]).date()),
        "end_date": str(pd.Timestamp(dates[-1]).date()),
        "demand_rows": len(demand),
        "customers": int(demand["customer_id"].nunique()),
        "products": int(demand["product_id"].nunique()),
        "days": len(dates),
        "total_demand": int(sales["demand_qty"].sum()),
        "total_sales": int(sales["sales_qty"].sum()),
        "total_lost_sales": int(sales["lost_sales_qty"].sum()),
        "orders_placed": len(outputs["sim_purchase_orders"]),
        "deliveries_received": len(outputs["sim_delivery_events"]),
        "orders_outstanding_at_horizon": (
            len(outputs["sim_purchase_orders"])
            - outputs["sim_delivery_events"]["order_id"].nunique()
        ),
        "config": config,
    }

    with (OUTPUT_DIR / "sim_run_metadata.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(metadata, f, indent=2)

    print(f"Output directory: {OUTPUT_DIR.resolve()}")
    print(f"Demand rows: {len(demand):,}")
    print(f"Days: {len(dates)}")
    print(f"Total demand: {metadata['total_demand']:,}")
    print(f"Total fulfilled: {metadata['total_sales']:,}")
    print(f"Total lost sales: {metadata['total_lost_sales']:,}")
    print(f"Orders placed: {metadata['orders_placed']:,}")
    print(f"Deliveries received: {metadata['deliveries_received']:,}")
    print(
        "Orders outstanding at horizon: "
        f"{metadata['orders_outstanding_at_horizon']:,}"
    )
    print("Inventory and demand reconciliation checks passed.")

    return outputs

