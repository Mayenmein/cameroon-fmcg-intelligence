import numpy as np
import pandas as pd
from src.config.settings import settings
from src.config.constants import PRODUCT_CATEGORIES, EXCLUDE, DROP_FAO_DUPLICATES, REGION_WEIGHTS

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
    """Build 500 distributors, each anchored to a real market."""
    rng = np.random.default_rng(seed)
    dim_market = pd.read_parquet(settings.data_processed_dir / "dim_market.parquet")

    # Weight markets by region size so Douala and Yaoundé carry more distributors.
    region_weights = {1: 0.22, 2: 0.20, 3: 0.10, 4: 0.09, 5: 0.08,
                      6: 0.08, 7: 0.07, 8: 0.06, 9: 0.05, 10: 0.05}
    market_weights = dim_market["region_id"].map(region_weights).to_numpy(dtype=float)
    market_probs = market_weights / market_weights.sum()

    sampled_markets = rng.choice(
        dim_market["market_id"].to_numpy(), size=n, p=market_probs,
    )
    customer_types = ["supermarket", "wholesaler", "retailer", "kiosk"]
    type_probs = [0.10, 0.30, 0.45, 0.15]

    df = pd.DataFrame({
        "customer_id": range(1, n + 1),
        "customer_type": rng.choice(customer_types, size=n, p=type_probs),
        "market_id": sampled_markets,
    })
    df = df.merge(dim_market[["market_id", "region_id"]], on="market_id")
    df = df[["customer_id", "customer_type", "region_id", "market_id"]]

    out = settings.data_processed_dir / "dim_customer.parquet"
    df.to_parquet(out, index=False)
    print(f"dim_customer: {len(df)} rows -> {out}")
    return df