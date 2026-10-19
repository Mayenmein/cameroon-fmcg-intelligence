from src.etl.build_dimensions import build_dim_customer
from src.etl.build_facts import build_fact_market_price
from src.synthetic.sales_simulator import simulate_sales


if __name__ == "__main__":
    # Ensure prerequisites are built in correct dependency order
    build_dim_customer()
    build_fact_market_price()
    simulate_sales(n_transactions=200_000)