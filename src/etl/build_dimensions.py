import numpy as np
import pandas as pd
from src.config.settings import settings
from src.config.constants import PRODUCT_CATEGORIES, EXCLUDE, DROP_FAO_DUPLICATES

def build_dim_date(start: str = "2005-01-01", end: str = "2026-12-31") -> pd.DataFrame:
    """Generate a daily calendar dimension."""
    dates = pd.date_range(start, end, freq="D")
    df = pd.DataFrame({"date": dates})
    df["date_id"] = df["date"].dt.strftime("%Y%m%d").astype(int)
    df["month"] = df["date"].dt.month
    df["quarter"] = df["date"].dt.quarter
    df["year"] = df["date"].dt.year
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["is_holiday"] = 0

    out = settings.data_processed_dir / "dim_date.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"dim_date: {len(df):,} rows -> {out}")
    return df

def build_dim_region() -> pd.DataFrame:
    """Build dim_region by taking unique regions from the subdivision lookup."""
    subdiv_path = settings.dim_region_path 
    if not subdiv_path.exists():
        raise FileNotFoundError(f"Missing subdivision file: {subdiv_path}")

    subdiv = pd.read_csv(subdiv_path)

    # One row per region, with centroid at the mean of its subdivisions.
    df = (
        subdiv.groupby("region_name", as_index=False)
              .agg(latitude=("latitude", "mean"),
                   longitude=("longitude", "mean"))
    )

    df.insert(0, "region_id", range(1, len(df) + 1))

    out = settings.data_processed_dir / "dim_region.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    assert len(df) == 10, f"Expected 10 regions, got {len(df)}"
    assert df["region_name"].is_unique, "Region names are not unique"
    print(f"dim_region: {len(df)} rows -> {out}")
    return df

def build_dim_market() -> pd.DataFrame:
    """Build dim_market from the 360-subdivision lookup, joined to dim_region."""
    subdiv_path = settings.dim_region_path
    if not subdiv_path.exists():
        raise FileNotFoundError(f"Missing subdivision file: {subdiv_path}")

    subdiv = pd.read_csv(subdiv_path)

    # Load the region dimension we already built to get region_id per region.
    region_path = settings.data_processed_dir / "dim_region.parquet"
    if not region_path.exists():
        raise FileNotFoundError(
            f"dim_region not found: {region_path}. Run build_dim_region() first."
        )
    dim_region = pd.read_parquet(region_path)

    # Start with the subdivision rows we want to keep for dim_market.
    df = subdiv[["subdivision_name", "division_name", "region_name",
                 "latitude", "longitude"]].copy()

    # Attach region_id by joining on region_name.
    df = df.merge(
        dim_region[["region_id", "region_name"]],
        on="region_name",
        how="left",
        validate="many_to_one",
    )

    # Fail loudly if any subdivision could not be matched to a region.
    missing = df["region_id"].isna().sum()
    if missing:
        bad = df[df["region_id"].isna()]["region_name"].unique()
        raise ValueError(f"{missing} rows have unmatched region_name: {bad}")

    df["region_id"] = df["region_id"].astype(int)

    # Assign the market primary key: unique per subdivision.
    df = df.rename(columns={"subdivision_name": "market_name"})
    df.insert(0, "market_id", range(1, len(df) + 1))

    # Reorder columns to match the schema.
    df = df[["market_id", "market_name", "region_id", "latitude", "longitude"]]

    out = settings.data_processed_dir / "dim_market.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"dim_market: {len(df)} rows -> {out}")
    return df

def build_dim_product() -> pd.DataFrame:
    """Build dim_product from the WFP ticker info file."""
    ticker_path = sorted(
        (settings.wfp_interim_path).glob("CMR_RTP_ticker_info_mkt_*.csv")
    )[-1]
    ticker = pd.read_csv(ticker_path)

    df = ticker[["ticker", "full_name", "units"]].copy()
    df = df[~df["ticker"].isin(EXCLUDE)]
    df = df[~df["ticker"].isin(DROP_FAO_DUPLICATES)]

    df["category"] = df["ticker"].map(PRODUCT_CATEGORIES).fillna("other")
    df["brand"] = None

    df = df.rename(columns={
        "ticker": "product_name",
        "units": "unit",
    })
    df.insert(0, "product_id", range(1, len(df) + 1))
    df = df[["product_id", "product_name", "category", "unit", "brand"]]

    out = settings.data_processed_dir / "dim_product.parquet"
    df.to_parquet(out, index=False)
    print(f"dim_product: {len(df)} rows -> {out}")
    return df


def build_dim_customer(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic customers assigned to markets.

    Regional allocation uses population as a documented proxy.
    Markets are sampled uniformly within each selected region.
    Customer-type proportions are simulation assumptions, not
    observed estimates of Cameroon distributor composition.
    """
    if n <= 0:
        raise ValueError("n must be greater than zero.")

    rng = np.random.default_rng(seed)

    dim_market = pd.read_parquet(
        settings.data_processed_dir / "dim_market.parquet"
    )
    dim_region = pd.read_parquet(
        settings.data_processed_dir / "dim_region.parquet"
    )

    required_market = {"market_id", "region_id"}
    required_region = {"region_id", "population"}

    if not required_market.issubset(dim_market.columns):
        raise ValueError("dim_market is missing required columns.")

    if not required_region.issubset(dim_region.columns):
        raise ValueError(
            "dim_region must contain region_id and population."
        )

    if dim_market["market_id"].duplicated().any():
        raise ValueError("market_id must be unique in dim_market.")

    # Only allocate customers to regions that have markets.
    available_regions = dim_region[
        dim_region["region_id"].isin(dim_market["region_id"])
    ].copy()

    if available_regions.empty:
        raise ValueError("No regions have matching market records.")

    if (
        available_regions["population"].isna().any()
        or (available_regions["population"] <= 0).any()
    ):
        raise ValueError(
            "Available regions must have positive, non-missing population."
        )

    # Population-based regional allocation: a proxy, not observed
    # distributor counts or measured product demand.
    region_ids = available_regions["region_id"].to_numpy()
    region_probs = (
        available_regions["population"].to_numpy(dtype=float)
    )
    region_probs /= region_probs.sum()

    sampled_regions = rng.choice(
        region_ids, size=n, p=region_probs
    )

    # Sample a market within each customer's assigned region.
    markets_by_region = {
        region_id: group["market_id"].to_numpy()
        for region_id, group in dim_market.groupby("region_id")
    }

    sampled_markets = np.empty(n, dtype=dim_market["market_id"].dtype)

    for region_id in np.unique(sampled_regions):
        mask = sampled_regions == region_id
        market_ids = markets_by_region[region_id]
        sampled_markets[mask] = rng.choice(
            market_ids, size=mask.sum(), replace=True
        )

    customer_types = ["supermarket", "wholesaler", "retailer", "kiosk"]
    type_probs = [0.10, 0.30, 0.45, 0.15]

    df = pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "customer_type": rng.choice(
            customer_types, size=n, p=type_probs
        ),
        "region_id": sampled_regions,
        "market_id": sampled_markets,
    })

    out = settings.data_processed_dir / "dim_customer.parquet"
    df.to_parquet(out, index=False)

    print(f"dim_customer: {len(df)} rows -> {out}")
    return df
