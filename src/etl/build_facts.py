import pandas as pd
import json

from src.config.settings import Settings
from src.config.constants import TRADE_PRODUCT_MAP


def _load_wfp_main() -> pd.DataFrame:
    """Load the newest main WFP price file."""
    path = sorted(
        (Settings().wfp_interim_path).glob("CMR_RTFP_mkt_*.csv")
    )[-1]
    df = pd.read_csv(path, low_memory=False)
    df = df[df["mkt_name"] != "Market Average"].reset_index(drop=True)
    return df



def _map_markets_to_subdivisions(
    wfp_markets: pd.DataFrame
) -> pd.DataFrame:
    """Preserve WFP source-market identity without geographic reassignment.

    dim_market is retained as an optional argument for compatibility
    with existing callers, but is deliberately not used.
    """
    required = ["geo_id", "mkt_name", "adm1_name", "adm2_name", "lat", "lon"]
    missing = [col for col in required if col not in wfp_markets.columns]
    if missing:
        raise ValueError(f"WFP market data is missing columns: {missing}")

    markets = wfp_markets[required].copy()
    markets = markets.drop_duplicates()

    # A geo_id must identify exactly one source market.
    identity_counts = markets.groupby("geo_id")["mkt_name"].nunique()
    conflicts = identity_counts[identity_counts > 1]
    if not conflicts.empty:
        raise ValueError(
            "A WFP geo_id maps to multiple market names: "
            f"{conflicts.index.tolist()[:10]}"
        )

    markets = markets.drop_duplicates(subset="geo_id").copy()
    markets["lat"] = pd.to_numeric(markets["lat"], errors="coerce")
    markets["lon"] = pd.to_numeric(markets["lon"], errors="coerce")

    # Stable IDs: the same geo_id receives the same ID across rebuilds.
    markets = markets.sort_values("geo_id").reset_index(drop=True)
    markets.insert(0, "wfp_market_id", range(1, len(markets) + 1))

    return markets[
        [
            "wfp_market_id",
            "geo_id",
            "mkt_name",
            "adm1_name",
            "adm2_name",
            "lat",
            "lon",
        ]
    ]


def build_fact_market_price() -> pd.DataFrame:
    """Build WFP market prices using original source-market identities."""
    out_dir = Settings().data_processed_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    wfp = _load_wfp_main()
    dim_product = pd.read_parquet(out_dir / "dim_product.parquet")
    dim_date = pd.read_parquet(out_dir / "dim_date.parquet")

    # Build the WFP market dimension.
    market_cols = ["geo_id", "mkt_name", "adm1_name", "adm2_name", "lat", "lon"]
    markets = wfp[market_cols].drop_duplicates()

    if markets["geo_id"].isna().any() or markets["geo_id"].duplicated().any():
        raise ValueError("Each WFP geo_id must identify exactly one market.")

    markets = markets.sort_values("geo_id").reset_index(drop=True)
    markets.insert(0, "wfp_market_id", range(1, len(markets) + 1))
    markets = markets.rename(columns={
        "mkt_name": "market_name",
        "lat": "latitude",
        "lon": "longitude",
    })

    markets.to_parquet(out_dir / "dim_wfp_market.parquet", index=False)

    # Reshape prices and trust scores from wide to long format.
    products = dim_product["product_name"].tolist()
    price_cols = [f"o_{p}" for p in products]
    trust_cols = [f"trust_{p}" for p in products]
    base = ["geo_id", "price_date"]

    missing_cols = [c for c in base + price_cols + trust_cols if c not in wfp.columns]
    if missing_cols:
        raise ValueError(f"WFP file is missing required columns: {missing_cols}")

    wide = wfp[base + price_cols + trust_cols].copy()
    wide["price_date"] = pd.to_datetime(wide["price_date"], errors="raise")

    if wide.duplicated(base).any():
        raise ValueError("Duplicate WFP geo_id/date records.")

    prices = wide.melt(
        id_vars=base, value_vars=price_cols,
        var_name="product_name", value_name="price",
    )
    prices["product_name"] = prices["product_name"].str.removeprefix("o_")

    trust = wide.melt(
        id_vars=base, value_vars=trust_cols,
        var_name="product_name", value_name="trust",
    )
    trust["product_name"] = trust["product_name"].str.removeprefix("trust_")

    df = prices.merge(
        trust,
        on=base + ["product_name"],
        how="left",
        validate="one_to_one",
    )
    df = df.dropna(subset=["price"]).copy()
    df["date_id"] = df["price_date"].dt.strftime("%Y%m%d").astype("int64")

    # Join to the WFP market dimension, never the subdivision dim_market.
    df = df.merge(
        markets[["wfp_market_id", "geo_id"]],
        on="geo_id",
        how="left",
        validate="many_to_one",
    )
    if df["wfp_market_id"].isna().any():
        raise ValueError("Some WFP price records have no matching WFP market.")

    # Join products.
    df = df.merge(
        dim_product[["product_id", "product_name"]],
        on="product_name",
        how="left",
        validate="many_to_one",
    )
    if df["product_id"].isna().any():
        raise ValueError("Some WFP price records have no matching product.")

    # Validate date foreign keys.
    valid_dates = set(dim_date["date_id"].astype("int64"))
    if not df["date_id"].isin(valid_dates).all():
        raise ValueError("Some WFP dates are missing from dim_date.")

    keys = ["wfp_market_id", "product_id", "date_id"]
    if df.duplicated(keys).any():
        raise ValueError("Duplicate market-price fact keys.")

    df = df[keys + ["price", "trust"]].reset_index(drop=True)
    df.to_parquet(out_dir / "fact_market_price.parquet", index=False)

    print(
        f"WFP markets: {len(markets):,}; "
        f"price rows: {len(df):,}"
    )
    return df

def build_fact_trade() -> pd.DataFrame:
    """Flatten Comtrade JSON files into rows of fact_trade."""
    dim_product = pd.read_parquet(Settings().data_processed_dir / "dim_product.parquet")
    dim_date = pd.read_parquet(Settings().data_processed_dir / "dim_date.parquet")

    frames = []
    for path in sorted(Settings().comtrade_raw_path.glob("cmr_imports_*.json")):
        label = path.stem.replace("cmr_imports_", "")
        if label not in TRADE_PRODUCT_MAP:
            continue
        rows = json.loads(path.read_text())
        if rows:
            df = pd.DataFrame(rows)
            df["product_name"] = TRADE_PRODUCT_MAP[label]
            frames.append(df)

    if not frames:
        raise RuntimeError("No Comtrade files matched dim_product.")

    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={
        "partnerDesc": "partner_country",
        "primaryValue": "import_value",
        "netWgt": "import_quantity",
    })
    df = df.merge(dim_product[["product_id", "product_name"]], on="product_name")
    df["date_id"] = df["period"].astype(int) * 10000 + 101
    df = df[df["date_id"].isin(dim_date["date_id"])]

    df["partner_country"] = df["partner_country"].fillna("Unknown")
    df["import_quantity"] = pd.to_numeric(
    df["import_quantity"], errors="coerce" )

    df["import_value"] = pd.to_numeric(
        df["import_value"], errors="coerce")

    df = df[["date_id", "product_id", "partner_country",
             "import_quantity", "import_value"]]
    df = df.drop_duplicates(["date_id", "product_id", "partner_country"]).reset_index(drop=True)

    out = Settings().data_processed_dir / "fact_trade.parquet"
    df.to_parquet(out, index=False)
    print(f"fact_trade: {len(df):,} rows -> {out}")
    return df