# src/ingestion/comtrade_trade.py
import json, time
import requests
from src.config.settings import Settings
from dotenv import load_dotenv
import os
load_dotenv()
settings = Settings()

# UN Comtrade API endpoint and Cameroon's numeric reporter code.
API_URL = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
REPORTER_CODE = 120  # Cameroon

# The six product categories to query.
HS_CODES = {
    "fertilizers": "31",
    "rice": "1006",
    "wheat": "1001",
    "maize": "1005",
    "sugar": "1701",
    "edible_oils": "15",
}

def fetch_comtrade_imports(start_year: int =2000, end_year: int =2025):
    """Download Cameroon imports for each HS code and cache as JSON."""
    raw_dir = settings.comtrade_raw_path
    raw_dir.mkdir(parents=True, exist_ok=True)

    for label, hs in HS_CODES.items():
        target = raw_dir / f"cmr_imports_{label}.json"
        if target.exists():
            print(f"Already exists: {target.name}")
            continue

        records = []
        for year in range(start_year, end_year + 1):
            params = {
                "reporterCode": REPORTER_CODE,
                "period": str(year),
                "cmdCode": hs,
                "flowCode": "M",        # M = imports
                "partnerCode": 0,       # 0 = World (all partners)
                "subscription-key": os.environ["COMTRADE_API_KEY"],
            }
            r = requests.get(API_URL, params=params, timeout=30)
            if r.status_code == 200:
                records.extend(r.json().get("data", []))
            # Free tier allows ~1 request/second, 500 calls/day.
            time.sleep(1)

        target.write_text(json.dumps(records, indent=2))
        print(f"Saved {len(records)} records to {target.name}")

if __name__ == "__main__":
    print("Fetching Cameroon imports from UN Comtrade...")
    fetch_comtrade_imports()