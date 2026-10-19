
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import nbinom


class CameroonianDemandSimulator:
    """
    Hierarchical synthetic sales simulator.

    Required quantity convention:
        fact_trade.import_quantity and fact_sales.quantity must use
        the same physical unit. Sales quantities are integer units.

    The national constraint is an import-based supply proxy, not a
    complete national food-balance model.

    If fact_market_price has market_id, prices are matched by market.
    Otherwise, product-year-month prices are used as a documented
    fallback.

    Regional and market weights are assumptions unless estimated
    from reliable external data.
    """

    REQUIRED_CUSTOMER = {
        "customer_id", "region_id", "market_id", "customer_type"
    }
    REQUIRED_MARKET = {"market_id", "region_id"}
    REQUIRED_PRICE = {"product_id", "date_id", "price"}
    REQUIRED_TRADE = {"product_id", "import_quantity"}
    REQUIRED_PRODUCT = {"product_id"}

    CHANNEL_MULTIPLIERS = {
        "wholesaler": 3.0,
        "supermarket": 2.0,
        "retailer": 1.0,
        "kiosk": 0.4,
    }
    DISCOUNTS = {
        "wholesaler": 0.10,
        "supermarket": 0.05,
        "retailer": 0.02,
        "kiosk": 0.00,
    }

    def __init__(
        self,
        dim_customer: pd.DataFrame,
        dim_product: pd.DataFrame,
        dim_region: pd.DataFrame,
        dim_market: pd.DataFrame,
        fact_market_price: pd.DataFrame,
        fact_trade: pd.DataFrame,
        *,
        region_weights: Optional[dict] = None,
        market_weights: Optional[dict] = None,
        seasonal_weights: Optional[dict] = None,
        price_elasticity: float = -0.75,
        base_transactions_per_batch: float = 15.0,
        base_transaction_mean: float = 15.0,
        random_state: int = 42,
    ):
        self.dim_customer = dim_customer.copy()
        self.dim_product = dim_product.copy()
        self.dim_region = dim_region.copy()
        self.dim_market = dim_market.copy()
        self.fact_market_price = fact_market_price.copy()
        self.fact_trade = fact_trade.copy()

        self.region_weights = region_weights
        self.market_weights = market_weights
        self.seasonal_weights = seasonal_weights

        if price_elasticity > 0:
            raise ValueError(
                "price_elasticity must be <= 0 for the "
                "assumed downward-sloping demand model."
            )
        if base_transactions_per_batch <= 0:
            raise ValueError("base_transactions_per_batch must be positive.")
        if base_transaction_mean <= 0:
            raise ValueError("base_transaction_mean must be positive.")

        self.price_elasticity = float(price_elasticity)
        self.base_transactions_per_batch = float(
            base_transactions_per_batch
        )
        self.base_transaction_mean = float(base_transaction_mean)
        self.rng = np.random.default_rng(random_state)

        self.national_supply = None
        self.regional_monthly_targets = None
        self.market_targets = None
        self.sales_targets = None
        self._price_table = None

        self._validate_inputs()

    # ---------------------------------------------------------------
    # General validation and utilities
    # ---------------------------------------------------------------

    @staticmethod
    def _require_columns(df, columns, name):
        missing = set(columns) - set(df.columns)
        if missing:
            raise ValueError(
                f"{name} is missing required columns: {sorted(missing)}"
            )

    @staticmethod
    def _check_unique(df, columns, name):
        if df.duplicated(columns).any():
            raise ValueError(
                f"{name} contains duplicate keys: {columns}"
            )

    @staticmethod
    def _year_month(series, name):
        """
        Accept YYYYMMDD integer/string date keys or date-like values.
        Returns integer year and month.
        """
        values = series.astype("string").str.strip()
        compact = values.str.fullmatch(r"\d{8}", na=False)

        parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

        if compact.any():
            parsed.loc[compact] = pd.to_datetime(
                values.loc[compact],
                format="%Y%m%d",
                errors="coerce",
            )

        if (~compact).any():
            parsed.loc[~compact] = pd.to_datetime(
                series.loc[~compact],
                errors="coerce",
            )

        if parsed.isna().any():
            bad = series.loc[parsed.isna()].head(5).tolist()
            raise ValueError(
                f"Cannot parse {name} as dates. Examples: {bad}"
            )

        return parsed.dt.year.astype(int), parsed.dt.month.astype(int)

    def _validate_inputs(self):
        self._require_columns(
            self.dim_customer, self.REQUIRED_CUSTOMER, "dim_customer"
        )
        self._require_columns(
            self.dim_product, self.REQUIRED_PRODUCT, "dim_product"
        )
        self._require_columns(
            self.dim_region, {"region_id"}, "dim_region"
        )
        self._require_columns(
            self.dim_market, self.REQUIRED_MARKET, "dim_market"
        )
        self._require_columns(
            self.fact_market_price, self.REQUIRED_PRICE, "fact_market_price"
        )
        self._require_columns(
            self.fact_trade, self.REQUIRED_TRADE, "fact_trade"
        )

        for df, key, name in [
            (self.dim_customer, "customer_id", "dim_customer"),
            (self.dim_product, "product_id", "dim_product"),
            (self.dim_region, "region_id", "dim_region"),
            (self.dim_market, "market_id", "dim_market"),
        ]:
            if df[key].isna().any():
                raise ValueError(f"{name}.{key} contains null keys.")

        self._check_unique(self.dim_customer, ["customer_id"], "dim_customer")
        self._check_unique(self.dim_product, ["product_id"], "dim_product")
        self._check_unique(self.dim_region, ["region_id"], "dim_region")
        self._check_unique(self.dim_market, ["market_id"], "dim_market")

        if self.dim_region.empty or self.dim_market.empty:
            raise ValueError("Region and market dimensions cannot be empty.")
        if self.dim_customer.empty or self.dim_product.empty:
            raise ValueError("Customer and product dimensions cannot be empty.")

        known_regions = set(self.dim_region["region_id"])
        if not set(self.dim_market["region_id"]).issubset(known_regions):
            raise ValueError("dim_market contains unknown region_id values.")

        customer_markets = self.dim_customer.merge(
            self.dim_market[["market_id", "region_id"]],
            on="market_id",
            how="left",
            suffixes=("_customer", "_market"),
            validate="many_to_one",
            indicator=True,
        )
        if (customer_markets["_merge"] != "both").any():
            raise ValueError("Some customers reference unknown markets.")

        if (
            customer_markets["region_id_customer"]
            != customer_markets["region_id_market"]
        ).any():
            raise ValueError(
                "Some customers have a region_id inconsistent "
                "with their market's region."
            )

        trade = self.fact_trade
        if "year" in trade.columns:
            years = pd.to_numeric(trade["year"], errors="coerce")
            if years.isna().any() or (years % 1 != 0).any():
                raise ValueError("fact_trade.year must contain integer years.")
            trade_year = years.astype(int)
        elif "date_id" in trade.columns:
            trade_year, _ = self._year_month(
                trade["date_id"], "fact_trade.date_id"
            )
        else:
            raise ValueError(
                "fact_trade must contain either 'year' or 'date_id'."
            )

        quantities = pd.to_numeric(
            trade["import_quantity"], errors="coerce"
        )
        if quantities.isna().any() or not np.isfinite(quantities).all():
            raise ValueError("Trade quantities must be finite numeric values.")
        if (quantities < 0).any():
            raise ValueError("Trade quantities cannot be negative.")

        # Store normalized trade data for Stage 1.
        self._trade_clean = trade.copy()
        self._trade_clean["trade_year"] = trade_year.to_numpy()
        self._trade_clean["import_quantity"] = quantities.to_numpy()

        prices = self.fact_market_price.copy()
        prices["price"] = pd.to_numeric(prices["price"], errors="coerce")
        if prices["price"].isna().any() or not np.isfinite(
            prices["price"]
        ).all():
            raise ValueError("Market prices must be finite numeric values.")
        if (prices["price"] <= 0).any():
            raise ValueError("Market prices must be strictly positive.")

        prices["year"], prices["month"] = self._year_month(
            prices["date_id"], "fact_market_price.date_id"
        )
        self._price_table = prices

        if "market_id" in prices.columns:
            if not set(prices["market_id"]).issubset(
                set(self.dim_market["market_id"])
            ):
                raise ValueError(
                    "Price table contains market_id values absent "
                    "from dim_market."
                )

        if not set(self._trade_clean["product_id"]).issubset(
            set(self.dim_product["product_id"])
        ):
            raise ValueError(
                "Trade data contains product IDs absent from dim_product."
            )
        if not set(prices["product_id"]).issubset(
            set(self.dim_product["product_id"])
        ):
            raise ValueError(
                "Price data contains product IDs absent from dim_product."
            )

    @staticmethod
    def _allocate_integer(total, weights):
        """
        Largest-remainder allocation.

        Returns nonnegative integers whose sum is exactly `total`.
        """
        total = int(total)
        weights = np.asarray(weights, dtype=float)

        if total < 0:
            raise ValueError("Allocation total cannot be negative.")
        if len(weights) == 0:
            if total:
                raise ValueError("Cannot allocate a positive total to no rows.")
            return np.zeros(0, dtype=int)
        if not np.isfinite(weights).all() or (weights < 0).any():
            raise ValueError("Allocation weights must be finite and nonnegative.")

        if total == 0:
            return np.zeros(len(weights), dtype=int)

        if weights.sum() <= 0:
            weights = np.ones(len(weights), dtype=float)

        exact = total * weights / weights.sum()
        result = np.floor(exact).astype(int)
        remainder = total - int(result.sum())

        if remainder:
            order = np.argsort(-(exact - result), kind="stable")
            result[order[:remainder]] += 1

        assert int(result.sum()) == total
        return result

    @staticmethod
    def _weights_for_ids(ids, configured_weights, key_name):
        if configured_weights is None:
            return np.ones(len(ids), dtype=float)

        weights = np.array(
            [float(configured_weights.get(key, 0.0)) for key in ids],
            dtype=float,
        )
        if (
            not np.isfinite(weights).all()
            or (weights < 0).any()
            or weights.sum() <= 0
        ):
            raise ValueError(
                f"Invalid {key_name}: weights must be finite, "
                "nonnegative and sum to a positive value."
            )
        return weights

    # ---------------------------------------------------------------
    # Stage 1: national import-based supply caps
    # ---------------------------------------------------------------

    def stage_1_national_supply_bounds(self):
        trade = self._trade_clean

        supply = (
            trade.groupby(["product_id", "trade_year"], as_index=False)
            ["import_quantity"]
            .sum()
            .rename(
                columns={
                    "trade_year": "year",
                    "import_quantity": "national_supply_cap",
                }
            )
        )

        # Sales quantities are integer units. Floor caps to avoid
        # claiming more integer units than the source quantity supports.
        supply["national_supply_cap"] = np.floor(
            supply["national_supply_cap"] + 1e-10
        ).astype("int64")

        self.national_supply = supply
        return supply.copy()

    # ---------------------------------------------------------------
    # Stage 2: allocate national supply to regions, then months
    # ---------------------------------------------------------------

    def stage_2_regional_monthly_allocation(self):
        if self.national_supply is None:
            self.stage_1_national_supply_bounds()

        regions = self.dim_region[["region_id"]].copy()
        region_ids = regions["region_id"].tolist()
        region_weights = self._weights_for_ids(
            region_ids, self.region_weights, "region_weights"
        )

        seasonal = self.seasonal_weights or {
            month: 1.0 for month in range(1, 13)
        }
        month_ids = list(range(1, 13))
        month_weights = self._weights_for_ids(
            month_ids, seasonal, "seasonal_weights"
        )

        records = []
        for supply in self.national_supply.itertuples(index=False):
            region_totals = self._allocate_integer(
                supply.national_supply_cap, region_weights
            )

            for region_id, region_total in zip(region_ids, region_totals):
                monthly_totals = self._allocate_integer(
                    region_total, month_weights
                )
                for month, target in zip(month_ids, monthly_totals):
                    records.append({
                        "product_id": supply.product_id,
                        "year": int(supply.year),
                        "region_id": region_id,
                        "month": month,
                        "regional_monthly_target": int(target),
                    })

        result = pd.DataFrame(records)
        self.regional_monthly_targets = result

        # Hard check: monthly/regional allocation conserves national supply.
        check = (
            result.groupby(["product_id", "year"])
            ["regional_monthly_target"].sum()
        )
        expected = self.national_supply.set_index(
            ["product_id", "year"]
        )["national_supply_cap"]

        if not check.reindex(expected.index, fill_value=0).equals(expected):
            raise AssertionError(
                "Regional/monthly allocation does not conserve national supply."
            )

        return result.copy()

    # ---------------------------------------------------------------
    # Stage 3: allocate regional-monthly ceilings to markets
    # ---------------------------------------------------------------

    def stage_3_market_disaggregation(self):
        if self.regional_monthly_targets is None:
            self.stage_2_regional_monthly_allocation()

        market_dim = self.dim_market[["market_id", "region_id"]].copy()
        records = []

        for row in self.regional_monthly_targets.itertuples(index=False):
            markets = market_dim[
                market_dim["region_id"] == row.region_id
            ].reset_index(drop=True)

            if markets.empty:
                if row.regional_monthly_target > 0:
                    raise ValueError(
                        f"Region {row.region_id!r} has positive supply "
                        "but no markets."
                    )
                continue

            market_ids = markets["market_id"].tolist()
            configured = (
                self.market_weights.get(row.region_id, {})
                if self.market_weights is not None
                else None
            )
            weights = self._weights_for_ids(
                market_ids, configured, "market_weights"
            )
            targets = self._allocate_integer(
                row.regional_monthly_target, weights
            )

            for market_id, target in zip(market_ids, targets):
                records.append({
                    "product_id": row.product_id,
                    "year": int(row.year),
                    "region_id": row.region_id,
                    "market_id": market_id,
                    "month": int(row.month),
                    "market_monthly_target": int(target),
                })

        result = pd.DataFrame(records)
        self.market_targets = result

        # Every region-month's market ceilings must add up exactly.
        parent = self.regional_monthly_targets.set_index(
            ["product_id", "year", "region_id", "month"]
        )["regional_monthly_target"]
        child = (
            result.groupby(["product_id", "year", "region_id", "month"])
            ["market_monthly_target"].sum()
        )

        if not child.reindex(parent.index, fill_value=0).equals(parent):
            raise AssertionError(
                "Market allocation does not conserve regional targets."
            )

        return result.copy()

    # ---------------------------------------------------------------
    # Stage 4: price-adjusted targets and transaction simulation
    # ---------------------------------------------------------------

    def _prepare_market_prices(self):
        prices = self._price_table.copy()

        # Use true market-level prices when available.
        if "market_id" in prices.columns:
            grouped = (
                prices.groupby(
                    ["product_id", "market_id", "year", "month"],
                    as_index=False,
                )["price"]
                .median()
                .rename(columns={"price": "market_price"})
            )
            join_keys = ["product_id", "market_id", "year", "month"]
        else:
            grouped = (
                prices.groupby(["product_id", "year", "month"], as_index=False)
                ["price"]
                .median()
                .rename(columns={"price": "market_price"})
            )
            join_keys = ["product_id", "year", "month"]

        # Reference price per product. Used to make elasticity scale-stable.
        reference = (
            grouped.groupby("product_id", as_index=False)["market_price"]
            .median()
            .rename(columns={"market_price": "reference_price"})
        )
        self._price_join_keys = join_keys
        self._product_reference_prices = reference
        return grouped

    def stage_4_conditional_transaction_simulation(self):
        if self.market_targets is None:
            self.stage_3_market_disaggregation()

        prices = self._prepare_market_prices()
        join_keys = self._price_join_keys

        sim_base = self.market_targets.merge(
            prices,
            on=join_keys,
            how="left",
            validate="many_to_one",
        )
        sim_base = sim_base.merge(
            self._product_reference_prices,
            on="product_id",
            how="left",
            validate="many_to_one",
        )

        missing = sim_base["market_price"].isna()
        # Explicit fallback: product's observed median across available
        # markets/months. Do not invent a universal price such as 500.
        sim_base.loc[missing, "market_price"] = sim_base.loc[
            missing, "reference_price"
        ]

        if sim_base["market_price"].isna().any():
            bad_products = sim_base.loc[
                sim_base["market_price"].isna(), "product_id"
            ].unique().tolist()
            raise ValueError(
                "No observed or imputable market price for products: "
                f"{bad_products}"
            )

        if (sim_base["market_price"] <= 0).any():
            raise ValueError("Prices must be positive.")

        # The allocated market target is a ceiling. Adjust demand downward
        # or upward relative to the product reference price, but never above
        # the available market-level supply allocation.
        ratio = (
            sim_base["market_price"] / sim_base["reference_price"]
        ).to_numpy(dtype=float)

        demand_multiplier = np.power(ratio, self.price_elasticity)
        demand_multiplier = np.clip(demand_multiplier, 0.0, 1.0)

        sim_base["sales_target"] = np.floor(
            sim_base["market_monthly_target"].to_numpy(dtype=float)
            * demand_multiplier
            + 1e-10
        ).astype("int64")

        self.sales_targets = sim_base[
            [
                "product_id", "year", "region_id", "market_id",
                "month", "market_monthly_target", "sales_target",
                "market_price", "reference_price",
            ]
        ].copy()

        transactions = []

        for row in sim_base.itertuples(index=False):
            target_qty = int(row.sales_target)
            if target_qty == 0:
                continue

            # Customers must belong to the actual market. Do not use OR
            # logic that silently assigns customers from other markets.
            eligible = self.dim_customer[
                self.dim_customer["market_id"] == row.market_id
            ]

            if eligible.empty:
                raise ValueError(
                    f"Positive sales target {target_qty} for market "
                    f"{row.market_id!r}, but no customers belong to it."
                )

            n_transactions = min(
                target_qty,
                max(
                    1,
                    int(round(
                        target_qty / self.base_transactions_per_batch
                    )),
                ),
            )

            sampled = eligible.iloc[
                self.rng.integers(0, len(eligible), size=n_transactions)
            ].reset_index(drop=True)

            # Draw negative-binomial provisional weights. Their parameters
            # govern transaction-size heterogeneity; exact reconciliation
            # below guarantees the aggregate target is not exceeded.
            multipliers = sampled["customer_type"].map(
                self.CHANNEL_MULTIPLIERS
            ).fillna(1.0).to_numpy(dtype=float)

            price_ratio = float(
                row.market_price / row.reference_price
            )
            means = (
                self.base_transaction_mean
                * multipliers
                * price_ratio ** self.price_elasticity
            )
            means = np.clip(means, 0.1, 1e6)

            dispersion = 2.0
            probabilities = dispersion / (dispersion + means)
            raw_weights = self.rng.negative_binomial(
                n=dispersion, p=probabilities
            ).astype(float)

            # Ensure positive weights, reserve one unit per transaction,
            # then distribute the remaining integer target. This produces
            # positive quantities summing EXACTLY to target_qty.
            raw_weights = np.maximum(raw_weights, 1.0)
            remaining = target_qty - n_transactions
            extra = self.rng.multinomial(
                remaining, raw_weights / raw_weights.sum()
            )
            quantities = extra + 1

            assert int(quantities.sum()) == target_qty
            assert (quantities > 0).all()

            discount = (
                sampled["customer_type"]
                .map(self.DISCOUNTS)
                .fillna(0.0)
                .to_numpy(dtype=float)
            )

            unit_prices = (
                float(row.market_price)
                * self.rng.uniform(0.95, 1.05, size=n_transactions)
            )

            # First day of the month, YYYYMMDD. If you have dim_date,
            # replace this with a validated date_id from that dimension.
            date_id = int(f"{int(row.year):04d}{int(row.month):02d}01")

            for i, cust in sampled.iterrows():
                qty = int(quantities[i])
                price = float(unit_prices[i])
                disc = float(discount[i])

                transactions.append({
                    "customer_id": cust["customer_id"],
                    "region_id": row.region_id,
                    "market_id": row.market_id,
                    "product_id": row.product_id,
                    "date_id": date_id,
                    "quantity": qty,
                    "unit_price": price,
                    "discount": disc,
                    "revenue": qty * price * (1.0 - disc),
                })

        columns = [
            "customer_id", "region_id", "market_id", "product_id",
            "date_id", "quantity", "unit_price", "discount", "revenue",
        ]
        sales_df = pd.DataFrame(transactions, columns=columns)
        return sales_df

    # ---------------------------------------------------------------
    # Stage 5: validate exact reconciliation and data integrity
    # ---------------------------------------------------------------

    def stage_5_validate_and_reconcile(self, sales_df: pd.DataFrame) -> bool:
        if self.market_targets is None or self.sales_targets is None:
            raise RuntimeError(
                "Run Stage 4 before validating sales."
            )

        if sales_df.empty:
            expected_positive = self.sales_targets["sales_target"].sum() > 0
            if expected_positive:
                raise AssertionError(
                    "Sales are empty despite positive sales targets."
                )

        required = {
            "customer_id", "region_id", "market_id", "product_id",
            "date_id", "quantity", "unit_price", "discount", "revenue",
        }
        self._require_columns(sales_df, required, "sales_df")

        if sales_df[list(required)].isna().any().any():
            raise AssertionError("Sales contain missing required values.")

        qty = pd.to_numeric(sales_df["quantity"], errors="coerce")
        price = pd.to_numeric(sales_df["unit_price"], errors="coerce")
        revenue = pd.to_numeric(sales_df["revenue"], errors="coerce")
        discount = pd.to_numeric(sales_df["discount"], errors="coerce")

        if not np.isfinite(qty).all() or (qty <= 0).any():
            raise AssertionError("Quantities must be finite positive integers.")
        if not np.equal(qty, np.floor(qty)).all():
            raise AssertionError("Sales quantities must be integers.")
        if not np.isfinite(price).all() or (price <= 0).any():
            raise AssertionError("Unit prices must be finite and positive.")
        if not np.isfinite(discount).all() or (
            (discount < 0) | (discount >= 1)
        ).any():
            raise AssertionError("Discounts must be in [0, 1).")
        if not np.isfinite(revenue).all() or (revenue < 0).any():
            raise AssertionError("Revenue must be finite and nonnegative.")

        expected_revenue = qty * price * (1.0 - discount)
        if not np.allclose(
            revenue.to_numpy(dtype=float),
            expected_revenue.to_numpy(dtype=float),
            rtol=1e-9,
            atol=1e-7,
        ):
            raise AssertionError("Revenue does not match quantity, price and discount.")

        customer_lookup = self.dim_customer[
            ["customer_id", "market_id", "region_id"]
        ]
        checked = sales_df.merge(
            customer_lookup,
            on="customer_id",
            how="left",
            suffixes=("", "_customer"),
            validate="many_to_one",
            indicator=True,
        )
        if (checked["_merge"] != "both").any():
            raise AssertionError("Sales contain unknown customer IDs.")
        if (
            (checked["market_id"] != checked["market_id_customer"])
            | (checked["region_id"] != checked["region_id_customer"])
        ).any():
            raise AssertionError(
                "Sales market/region does not match the sampled customer's location."
            )

        market_keys = [
            "product_id", "year", "region_id", "market_id", "month"
        ]

        if not sales_df.empty:
            years, months = self._year_month(
                sales_df["date_id"], "sales_df.date_id"
            )
            checked_sales = sales_df.copy()
            checked_sales["year"] = years.to_numpy()
            checked_sales["month"] = months.to_numpy()
            actual = (
                checked_sales.groupby(market_keys, as_index=False)["quantity"]
                .sum()
                .rename(columns={"quantity": "actual_quantity"})
            )
        else:
            actual = pd.DataFrame(
                columns=market_keys + ["actual_quantity"]
            )

        expected = self.sales_targets[
            market_keys + ["sales_target", "market_monthly_target"]
        ].copy()

        comparison = expected.merge(
            actual,
            on=market_keys,
            how="left",
            validate="one_to_one",
        )
        comparison["actual_quantity"] = (
            comparison["actual_quantity"].fillna(0).astype("int64")
        )

        if not (
            comparison["actual_quantity"].to_numpy()
            == comparison["sales_target"].to_numpy()
        ).all():
            bad = comparison[
                comparison["actual_quantity"] != comparison["sales_target"]
            ].head(10)
            raise AssertionError(
                "Sales do not reconcile to price-adjusted market targets:\n"
                + bad.to_string(index=False)
            )

        if (
            comparison["actual_quantity"]
            > comparison["market_monthly_target"]
        ).any():
            raise AssertionError("A market's sales exceed its supply ceiling.")

        # Regional-monthly sales cannot exceed their allocated supply.
        regional_actual = (
            comparison.groupby(
                ["product_id", "year", "region_id", "month"],
                as_index=False,
            )
            .agg(actual_quantity=("actual_quantity", "sum"))
        )
        regional_caps = self.regional_monthly_targets.rename(
            columns={"regional_monthly_target": "regional_cap"}
        )
        regional_check = regional_caps.merge(
            regional_actual,
            on=["product_id", "year", "region_id", "month"],
            how="left",
            validate="one_to_one",
        )
        regional_check["actual_quantity"] = (
            regional_check["actual_quantity"].fillna(0)
        )

        if (
            regional_check["actual_quantity"]
            > regional_check["regional_cap"]
        ).any():
            raise AssertionError("Regional-monthly supply ceiling exceeded.")

        # National annual sales cannot exceed the import-based cap.
        annual_actual = (
            comparison.assign(
                year=comparison["year"].astype(int)
            )
            .groupby(["product_id", "year"], as_index=False)
            .agg(actual_quantity=("actual_quantity", "sum"))
        )
        national_check = self.national_supply.merge(
            annual_actual,
            on=["product_id", "year"],
            how="left",
            validate="one_to_one",
        )
        national_check["actual_quantity"] = (
            national_check["actual_quantity"].fillna(0)
        )

        if (
            national_check["actual_quantity"]
            > national_check["national_supply_cap"]
        ).any():
            raise AssertionError("National annual supply cap exceeded.")

        print(
            "Validation passed: exact sales-target reconciliation, "
            "valid customer locations, valid financials, and no "
            "market, regional or national supply-ceiling violations."
        )
        return True

    def run(self):
        """Execute the complete pipeline and return validated sales."""
        self.stage_1_national_supply_bounds()
        self.stage_2_regional_monthly_allocation()
        self.stage_3_market_disaggregation()
        sales = self.stage_4_conditional_transaction_simulation()
        self.stage_5_validate_and_reconcile(sales)
        return sales