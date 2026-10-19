import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import json

from src.config.settings import settings
from src.config.constants import TRADE_PRODUCT_MAP


def _load_wfp_main() -> pd.DataFrame:
    """Load the newest main WFP price file."""
    path = sorted(
        (settings.wfp_interim_path).glob("CMR_RTFP_mkt_*.csv")
    )[-1]
    df = pd.read_csv(path, low_memory=False)
    df = df[df["mkt_name"] != "Market Average"].reset_index(drop=True)
    return df


def _map_markets_to_subdivisions(wfp_markets: pd.DataFrame, dim_market: pd.DataFrame):
    """Assign each WFP market to its nearest subdivision by lat/lon."""
    wfp = wfp_markets[["geo_id", "lat", "lon"]].copy()
    wfp["lat"] = pd.to_numeric(wfp["lat"], errors="coerce")
    wfp["lon"] = pd.to_numeric(wfp["lon"], errors="coerce")
    wfp = wfp.drop_duplicates("geo_id").reset_index(drop=True)

    before = len(wfp)
    wfp = wfp[np.isfinite(wfp["lat"]) & np.isfinite(wfp["lon"])].reset_index(drop=True)
    if before != len(wfp):
        print(f"dropped {before - len(wfp)} markets with bad coords")

    tree = cKDTree(dim_market[["latitude", "longitude"]].to_numpy(dtype=float))
    _, idx = tree.query(wfp[["lat", "lon"]].to_numpy(dtype=float), k=1)
    wfp["market_id"] = dim_market.iloc[idx]["market_id"].to_numpy()
    return wfp[["geo_id", "market_id"]]

def build_fact_market_price() -> pd.DataFrame:
    """Melt the WFP wide file into long format and join to dimensions."""
    wfp = _load_wfp_main()
    dim_market = pd.read_parquet(settings.data_processed_dir / "dim_market.parquet")
    dim_product = pd.read_parquet(settings.data_processed_dir / "dim_product.parquet")
    dim_date = pd.read_parquet(settings.data_processed_dir / "dim_date.parquet")

    # Melt only the columns for products in dim_product.
    products = dim_product["product_name"].tolist()
    price_cols = [f"o_{p}" for p in products]
    trust_cols = [f"trust_{p}" for p in products]

    base = ["geo_id", "price_date"]
    wide = wfp[base + price_cols + trust_cols].copy()
    wide["price_date"] = pd.to_datetime(wide["price_date"], errors="coerce")

    # Melt prices and trust into long format, then merge.
    prices = wide.melt(base, price_cols, var_name="product_name", value_name="price")
    prices["product_name"] = prices["product_name"].str.removeprefix("o_")
    trust = wide.melt(base, trust_cols, var_name="product_name", value_name="trust")
    trust["product_name"] = trust["product_name"].str.removeprefix("trust_")
    df = prices.merge(trust, on=base + ["product_name"], how="left")
    df = df.dropna(subset=["price"]).reset_index(drop=True)

    # Attach foreign keys.
    geo_map = _map_markets_to_subdivisions(wfp[["geo_id", "lat", "lon"]], dim_market)
    df = df.merge(geo_map, on="geo_id", how="left")
    df = df.merge(dim_product[["product_id", "product_name"]], on="product_name", how="left")
    df["date_id"] = df["price_date"].dt.strftime("%Y%m%d").astype(int)
    df = df.merge(dim_date[["date_id"]], on="date_id", how="inner")

    # Clean, dedupe, save.
    df = df[["market_id", "product_id", "date_id", "price", "trust"]].dropna(
        subset=["market_id", "product_id", "date_id"]
    )
    df["market_id"] = df["market_id"].astype(int)
    df["product_id"] = df["product_id"].astype(int)
    df = df.drop_duplicates(["market_id", "product_id", "date_id"]).reset_index(drop=True)

    out = settings.data_processed_dir / "fact_market_price.parquet"
    df.to_parquet(out, index=False)
    print(f"fact_market_price: {len(df):,} rows -> {out}")
    return df

def build_fact_trade() -> pd.DataFrame:
    """Flatten Comtrade JSON files into rows of fact_trade."""
    dim_product = pd.read_parquet(settings.data_processed_dir / "dim_product.parquet")
    dim_date = pd.read_parquet(settings.data_processed_dir / "dim_date.parquet")

    frames = []
    for path in sorted(settings.comtrade_raw_path.glob("cmr_imports_*.json")):
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
    df["import_quantity"] = pd.to_numeric(df["import_quantity"], errors="coerce").fillna(0)
    df["import_value"] = pd.to_numeric(df["import_value"], errors="coerce").fillna(0)

    df = df[["date_id", "product_id", "partner_country",
             "import_quantity", "import_value"]]
    df = df.drop_duplicates(["date_id", "product_id", "partner_country"]).reset_index(drop=True)

    out = settings.data_processed_dir / "fact_trade.parquet"
    df.to_parquet(out, index=False)
    print(f"fact_trade: {len(df):,} rows -> {out}")
    return df