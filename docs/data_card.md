# Data Card — Cameroon FMCG Demand & Market Intelligence Dataset

## 1. World Bank / WFP Market Food Prices

**Source:** [World Bank Microdata Library — Cameroon Real Time Food Prices, 2021](https://microdata.worldbank.org/catalog/4487)

**Dataset identifier:** `CMR_2021_RTFP_v02_M`

**Data type:** External market-price observations, including source-imputed values where applicable.

**Coverage:** Cameroon food prices at market level, with temporal coverage and product availability determined by the source records.

### Variables

Document the actual source columns in the raw file. Relevant fields may include:

| Field | Description | Unit / type |
|---|---|---|
| Market | Market associated with the price record | Categorical |
| Product / commodity | Food product priced | Categorical |
| Date / month | Observation period | Date or period |
| Price | Recorded or imputed market price | Source-defined currency and unit |
| Trust / confidence field, if present | Source-provided quality indicator | Source-defined; verify semantics |

The table above is a field guide, not a claim that every named column exists verbatim in the downloaded file.

### Data-quality notes

- Observed and imputed price values must remain distinguishable wherever the source provides that information.

- Verify the meaning and allowed values of the `trust` or confidence field against the dataset documentation.

- Market coverage and the number of observations can vary by commodity and period.

- Preserve the original currency, measurement unit, product label and date when creating transformed tables.

- Monthly market prices must not be represented as independently observed daily prices.

## 2. UN Comtrade International Trade Data

**Source:** [UN Comtrade](https://comtradeplus.un.org/)

**Data type:** International merchandise trade statistics.

**Coverage:** Cameroon imports and exports for selected commodities and years. The exact reporting years, trade flows, partner coverage and units depend on the downloaded records.

### Fields to retain

| Field | Description |
|---|---|
| Reporter | Country reporting the trade flow |
| Partner | Trading partner |
| Period | Reporting year or period |
| Trade flow | Import or export |
| Commodity code | Harmonized System (HS) code |
| Commodity description | Product description associated with the code |
| Trade value | Reported trade value and currency |
| Net weight / quantity | Reported quantity and its measurement unit |

Confirm exact column names against the downloaded files.

### Commodity mapping and limitations

- **HS 1001:** Wheat and meslin grain; not wheat flour.

- **HS 1101:** Wheat or meslin flour, where that product definition is relevant.

- **HS 1006:** Rice, covering multiple forms and processing states.

- **HS Chapter 15:** A broad category of animal or vegetable fats and oils; it does not uniquely represent palm oil.

- Do not add a World aggregate to its individual partner records.

- Missing trade quantities must remain missing unless the source explicitly reports zero.

- Preserve HS code, code revision, product description, year, partner, trade flow and quantity unit during extraction.

Trade statistics describe reported international flows. They are not direct measurements of local market availability, company purchases or company inventory.

## 3. GADM Administrative Boundaries

**Source:** [GADM — Download Country-Level Data](https://gadm.org/download_country.html)

**Version:** GADM 4.1

**Country:** Cameroon

**Data type:** Geographic polygon boundaries.

### Geographic coverage

The country-level administrative data include Cameroon’s regional subdivisions. The project uses regional and lower-level administrative boundaries to associate market records with geographic areas.

### Relevant fields

| Field | Description |
|---|---|
| Administrative identifiers | Source identifiers for geographic units |
| Administrative names | Names of regions and lower-level subdivisions |
| Geometry | Polygon geometry |
| Administrative level | Level of subdivision represented |

Exact field names depend on the downloaded GADM file.

### Geographic limitations

- A market-to-subdivision association based on the nearest geographic feature is an approximation, not confirmation that the market lies within that subdivision.

- Record the coordinate reference system and the method used for any spatial transformation.

- Preserve source administrative names and identifiers before applying project-specific mappings.

- Review GADM’s licensing terms before redistributing the geographic data or using them commercially.

## 4. MINADER AGRISTAT No. 18

**Source:** [MINADER AGRISTAT No. 18 — English report](https://www.minader.cm/wp-content/uploads/2023/11/AGRISTAT_NEW_18_ANG.pdf)

**Data type:** Agricultural production, trade, population and regional price statistics extracted from published tables.

**Reference period:** Primarily 2016–2020 for the production and trade series listed below. Regional population and agricultural prices have their own reference periods.

### 4.1 Domestic agricultural production

**Source tables:** Table 3, page 28; Table 4, page 29; Table 28, page 43.

| Commodity | Measure | Unit | Coverage |
|---|---|---|---|
| Paddy rice | Domestic production | Tonnes | 2016–2020 |
| Maize | Domestic production | Tonnes | 2016–2020 |
| Palm oil | Domestic production | Tonnes | 2016–2020 |

Reported national totals transcribed from the tables:

| Commodity | 2016 | 2017 | 2018 | 2019 | 2020 |
|---|---:|---:|---:|---:|---:|
| Paddy rice | 277,796.8 | 287,099 | 327,365.9 | 292,850.1 | 290,449.1 |
| Maize | Verify against extracted CSV | Verify | Verify | Verify | Verify |
| Palm oil | 318,773 | 361,995 | 352,195.5 | 336,466 | 373,464.9 |

The maize national totals should be transcribed from the extracted source table and checked against `domestic_production.csv` before publication. The palm oil table supplied figures for eight regions; Far North and North were not supplied as regional rows. This absence must not be interpreted as zero production.

**File:** `data/raw/minader/domestic_production.csv`

### 4.2 Agricultural imports

**Source table:** Table 165, page 124.

**File:** `data/raw/minader/minader_imports.csv`

| Commodity | Unit | 2016 | 2017 | 2018 | 2019 | 2020 |
|---|---|---:|---:|---:|---:|---:|
| Wheat and meslin | Tonnes | 616,676 | 681,778 | 745,664 | 857,940 | Missing |
| Maize | Tonnes | 31,959 | 45,968 | 13,711 | 14,679 | Missing |
| Rice | Tonnes | 614,400 | 728,443 | 561,112 | 894,486 | 591,600 |

**Data-quality note:** The blank 2020 entries for wheat and maize are missing values, not zero imports. Wheat and meslin grain should not be conflated with wheat flour. Rice import definitions should be checked before comparison with paddy rice production.

### 4.3 Agricultural exports

**Source table:** Table 167, page 124.

**File:** `data/raw/minader/minader_exports.csv`

| Commodity | Unit | 2016 | 2017 | 2018 | 2019 | 2020 |
|---|---|---:|---:|---:|---:|---:|
| Palm oil | Tonnes | 1,574 | 1,144 | 1,544 | 1,643 | 0 |

The 2020 zero is transcribed as reported and should be checked against the original table. Do not replace it with a missing value or interpret it as proof that no exports occurred without confirming the source definition.

### 4.4 Regional population

**Source table:** Table 147, page 111.

**Reference period:** Fourth quarter of 2020.

**Unit:** Persons.

**File:** `data/raw/minader/regional_population.csv`

| Region | Population |
|---|---:|
| Adamawa | 1,370,196 |
| Centre | 4,553,525 |
| East | 1,134,314 |
| Far North | 4,482,731 |
| Littoral | 3,689,546 |
| North | 2,764,579 |
| North-West | 2,541,188 |
| West | 2,528,099 |
| South-West | 932,806 |
| South | 1,934,352 |

These are regional population figures for the stated reference period, not current population estimates.

## 5. Cameroon INS Consumer Price Indicators

**Source:** Cameroon National Institute of Statistics (INS), *Note d'informations rapides — Publication Mensuelle N°05/26: Note mensuelle sur l'évolution des prix à la consommation finale des ménages au Cameroun — Mois de mai 2026*, page 7.

**Data type:** Indicators extracted from a published consumer-price report.

**Reference period:** May 2026, with year-on-year and month-on-month comparisons as specified below.

| Indicator | Reported value | Comparison / definition |
|---|---:|---|
| Food inflation | +5.6% | Year-on-year |
| Fresh produce inflation | +8.5% | Year-on-year |
| Oils and fats | −2.5% | Month-on-month |
| Oils and fats | −0.3% | Year-on-year |
| Bread and cereals | −0.5% | Month-on-month |
| Bread and cereals | +1.3% | Year-on-year |
| Fish and seafood | +4.6% | Month-on-month |
| Fish and seafood | +13.4% | Year-on-year |
| Diesel import cost | 489 to 786 XAF/L | February to May 2026; reported increase +60.7% |

Reported city indicators from the extraction:

| City | Reported indicator |
|---|---:|
| Maroua | −0.7% |
| Bertoua | +4.2% |
| Douala | +2.4% |
| Yaoundé | +3.0% |

## 6. Synthetic Customer Demand

**File:** data/processed/sim_demand.parquet

**Data type:** Synthetic daily customer-product demand generated for the simulation.

**Current row count:** 2,190,000 rows.

**Generation scope:** 500 customers × 12 products × 365 days.

### Variables

The exact column names should be confirmed against the current Parquet file before publication. The demand dataset represents generated demand quantities, not observed customer purchases. Its quantities have not been verified as consistent with the commercial units recorded in dim_product.

## 7. Simulated Sales

**File:** data/processed/inventory_full_run_revised1/sim_sales.parquet

**Data type:** Synthetic daily customer-product demand, fulfilled sales and lost sales.

**Current row count:** 2,190,000 rows.

### Columns

| Column | Description | Unit / type |
|---|---|---|
| date | Simulation date for the customer-product record | Date |
| date_id | Date identifier | Integer |
| customer_id | Simulated customer identifier | Integer |
| product_id | Product identifier | Integer |
| product_name | Product label carried in the simulator output | Text |
| demand_qty | Quantity requested | Numeric; unit depends on product configuration |
| sales_qty | Quantity fulfilled | Numeric; unit depends on product configuration |
| lost_sales_qty | Quantity requested but not fulfilled | Numeric; unit depends on product configuration |

### Data-quality notes

- The simulator does not generate selling prices; unit_price is not present in this file.
- The quantity fields are synthetic and should not be presented as observed company sales.
- The project has not yet verified that quantities use consistent commercial units across all products.

## 8. Simulated Inventory Snapshots

**File:** data/processed/inventory_full_run_revised1/sim_inventory_snapshot.parquet

**Data type:** Synthetic daily inventory state by product.

### Columns

| Column | Description | Unit / type |
|---|---|---|
| date | Simulation date | Date |
| product_id | Product identifier | Integer |
| product_name | Product label carried in the simulator output | Text |
| opening_stock | Stock at the start of the day | Numeric; product-specific unit |
| arrivals_qty | Quantity received during the day | Numeric; product-specific unit |
| demand_qty | Quantity requested during the day | Numeric; product-specific unit |
| sales_qty | Quantity fulfilled during the day | Numeric; product-specific unit |
| lost_sales_qty | Unfulfilled demand during the day | Numeric; product-specific unit |
| closing_stock | Stock remaining at the end of the day | Numeric; product-specific unit |
| on_order_qty | Quantity in outstanding purchase orders | Numeric; product-specific unit |
| inventory_position | Inventory position recorded by the simulator | Numeric; product-specific unit |

## 9. Simulated Inventory Movements

**File:** data/processed/inventory_full_run_revised1/sim_inventory_movements.parquet

**Data type:** Synthetic inventory movement ledger.

### Columns

| Column | Description | Unit / type |
|---|---|---|
| date | Movement date | Date |
| product_id | Product identifier | Integer |
| movement_type | Type of stock movement | Text |
| quantity_change | Quantity added to or removed from stock | Numeric; product-specific unit |
| reference_id | Reference associated with the movement, where provided | Text |
| on_hand_after | On-hand stock after the movement | Numeric; product-specific unit |

## 10. Simulated Purchase Orders and Deliveries

**Data type:** Synthetic supplier orders and delivery records.

### Purchase orders

**File:** data/processed/inventory_full_run_revised1/sim_purchase_orders.parquet

| Column | Description | Unit / type |
|---|---|---|
| order_id | Purchase-order identifier | Integer |
| order_date | Date the order was placed | Date |
| arrival_date | Scheduled arrival date | Date |
| product_id | Product identifier | Integer |
| product_name | Product label carried in the simulator output | Text |
| quantity | Quantity ordered | Numeric; product-specific unit |
| lead_time_days | Configured lead time | Days |

### Delivery events

**File:** data/processed/inventory_full_run_revised1/sim_delivery_events.parquet

| Column | Description | Unit / type |
|---|---|---|
| order_id | Purchase-order identifier | Integer |
| product_id | Product identifier | Integer |
| product_name | Product label carried in the simulator output | Text |
| arrival_date | Date the delivery arrived | Date |
| quantity_received | Quantity received | Numeric; product-specific unit |

## 11. Simulated Stockout Events

**File:** data/processed/inventory_full_run_revised1/sim_stockout_events.parquet

**Data type:** Synthetic customer-product records where some demand was unfulfilled.

### Columns

| Column | Description | Unit / type |
|---|---|---|
| date | Date of the stockout event | Date |
| customer_id | Customer identifier | Integer |
| product_id | Product identifier | Integer |
| product_name | Product label carried in the simulator output | Text |
| demand_qty | Quantity requested | Numeric; product-specific unit |
| fulfilled_qty | Quantity fulfilled | Numeric; product-specific unit |
| lost_sales_qty | Quantity not fulfilled | Numeric; product-specific unit |

### Simulation metadata

The simulation run also produces sim_run_metadata.json. Consult the file for the run's recorded configuration and metadata; its exact fields depend on the saved output.

## 12. Data Quality and Limitations

1. **Mixed provenance:** Source observations, report-extracted values, derived fields and synthetic records must be distinguishable.

2. **Missing values:** Preserve missingness; do not automatically substitute zero.

3. **Different time resolutions:** Source datasets may be monthly, annual, quarterly or tied to specific report periods.

4. **Different geographic resolutions:** National trade statistics, regional production, market prices and administrative boundaries do not share the same spatial unit.

5. **Measurement units:** Preserve original currencies, units and definitions; convert only through documented transformations.

6. **Geographic matching:** Approximate spatial assignments can introduce classification errors.

7. **Synthetic-data validity:** Synthetic records reflect configured assumptions and cannot be treated as evidence of actual company operations.

8. **Temporal relevance:** Historical figures must retain their original reference years and must not be presented as current measurements.

## 13. Source Register

| Source | Reference |
|---|---|
| World Bank / WFP | [Cameroon Real Time Food Prices, 2021](https://microdata.worldbank.org/catalog/4487) |
| UN Comtrade | [UN Comtrade Plus](https://comtradeplus.un.org/) |
| GADM | [GADM data download](https://gadm.org/download_country.html) |
| MINADER | [AGRISTAT No. 18, English report](https://www.minader.cm/wp-content/uploads/2023/11/AGRISTAT_NEW_18_ANG.pdf) |
| INS | May 2026 monthly consumer-price report; retain the original report file and page reference in the repository |
| Synthetic datasets | Project scripts and generation configurations; retain repository paths and version-control references |

## 14. Data Relationships

This section documents how datasets can be related. The preceding sections describe the individual datasets and their fields only.
- Product identifiers: product_id identifies products in simulated sales, inventory snapshots, inventory movements, purchase orders, delivery events, stockout events, and public market/trade fact tables. It is intended to match dim_product.product_id.
- Customer identifiers: customer_id identifies customers in simulated sales and stockout events. It is intended to match dim_customer.customer_id.
- Date identifiers and dates: fact_sales.date_id is intended to match dim_date.date_id. The simulator's date fields and the date field in inventory snapshots are calendar dates; they should be checked against the date dimension when date-level joins are needed.
- Purchase orders and deliveries: order_id identifies a purchase order and is used in delivery-event records to identify the order associated with a delivery. Orders can remain outstanding beyond the end of the simulation horizon.
- Geographic dimensions: dim_customer.region_id and dim_customer.market_id identify the region and market assigned to a customer. Public WFP price observations use wfp_market_id, which identifies a WFP market record; this is distinct from the project's market_id.
- Market prices: fact_market_price records prices by WFP market, product and date. The WFP market identifier is intended to match dim_wfp_market.wfp_market_id; product and date identifiers are intended to match dim_product.product_id and dim_date.date_id.
- Trade records: fact_trade contains date, product and partner-country fields. Its date and product identifiers are intended to match the corresponding dimensions.
- Public context versus synthetic operations: WFP prices, MINADER statistics, INS indicators, UN Comtrade trade statistics and GADM boundaries provide external context. They are not observed sales, company purchase orders, deliveries or inventory. Simulator outputs are synthetic and must remain labelled as such.
- Parquet-to-database column differences: simulator Parquet files may contain descriptive fields such as product_name that are not present in the corresponding PostgreSQL fact tables. The loader must map only columns defined by the destination table; product_id is the identifier used for product-level joins.
- Join validation: verify identifier coverage, date coverage, units and product mappings before joining datasets. A matching identifier does not by itself make measurements comparable across different time periods, geographic levels or units.