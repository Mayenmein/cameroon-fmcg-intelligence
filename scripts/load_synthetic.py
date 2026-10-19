from sqlalchemy import text
import pandas as pd

from src.db.connection import get_engine


def load_parquet(parquet_path, table_name, chunksize=5000):
    df = pd.read_parquet(parquet_path)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE'))
    df.to_sql(table_name, engine, if_exists="append",
              index=False, chunksize=chunksize, method=None)
    print(f"Loaded {len(df):,} rows into {table_name}")


if __name__ == "__main__":
    #load_parquet("data/processed/dim_customer.parquet", "dim_customer")
    #load_parquet("data/processed/fact_sales.parquet", "fact_sales")

    import pandas as pd
    import numpy as np
    import statsmodels.api as sm

    df = pd.read_parquet("data/processed/fact_sales.parquet")
    df = df[df["product_id"] == 1]  # check one product at a time

    # Poisson GLM: quantity ~ log(price)
    X = sm.add_constant(np.log(df["unit_price"].to_numpy()))
    y = df["quantity"].to_numpy()
    model = sm.GLM(y, X, family=sm.families.Poisson()).fit()

    print(model.params)
    # params[1] should be approximately -0.60 for product 1.