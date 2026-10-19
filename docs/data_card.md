# Data Card: Cameroon FMCG Demand & Market Intelligence Platform

## 1. Overview & Provenance

This project implements a demand forecasting and inventory intelligence platform for an agro/FMCG distributor operating across Cameroon. 

**Data Provenance Statement:**
*   **External market-price, trade, and geographic variables are real.**
*   **Company-level transaction records (`fact_sales` and `dim_customer`) are synthetic** because commercial distributor sales data in Cameroon is proprietary. The synthetic sales engine is mathematically constrained by the real price paths, regional distributions, and published FMCG elasticities to ensure economic realism.

---

## 2. Dataset A: World Bank / WFP Real Time Prices (RTP)

**Source:** World Bank Microdata Library (Dataset ID: `CMR_2021_RTFP_v02_M`), derived from the World Food Programme (WFP) Vulnerability Analysis and Mapping (VAM) survey networks.
**Description:** Monthly food price estimates across multiple markets in Cameroon. It includes both observed prices and model-imputed values for missing market-months, alongside confidence scores.

### Data Dictionary: `fact_market_price` (Real)
| Column | Data Type | Description |
| :--- | :--- | :--- |
| `market_id` | Integer (PK) | Foreign key linking to the GADM geographic subdivision. |
| `product_id` | Integer (PK) | Foreign key linking to the commodity. |
| `date_id` | Integer (PK) | Foreign key linking to the calendar dimension (`YYYYMM01`). |
| `price` | Numeric | The observed or modeled price of the commodity in local currency (XAF). |
| `trust` | Numeric | The World Bank's model trust score (0–10 scale). Lower values indicate reliance on imputation. |

### Data Dictionary: `dim_product` (Real)
| Column | Data Type | Description |
| :--- | :--- | :--- |
| `product_id` | Integer (PK) | Unique identifier for the commodity. |
| `product_name` | String | The WFP ticker symbol (e.g., `rice`, `maize`, `cassava`). |
| `category` | String | Assigned project category (e.g., `staple`, `root`, `protein`, `oil`). |
| `unit` | String | The physical unit of measurement as defined by WFP (e.g., `KG`, `12 KG`, `L`). |
| `brand` | String | Always NULL, as these are generic commodities, not branded goods. |

---

## 3. Dataset B: UN Comtrade

**Source:** UN Comtrade Database (Reporter: Cameroon, Flow: Import, Classification: HS).
**Description:** Annual import volumes and values for specific agricultural commodities. 
**Scope Limitation:** Restricted to the 4 products that overlap with the WFP price data: Rice, Maize, Wheat Flour, and Edible Oils.

### Data Dictionary: `fact_trade` (Real)
| Column | Data Type | Description |
| :--- | :--- | :--- |
| `date_id` | Integer (FK) | Foreign key to calendar dimension (`YYYY0101`, representing the annual period). |
| `product_id` | Integer (FK) | Foreign key linking to the commodity. |
| `partner_country` | String | The origin country of the imports (or "World" for aggregate totals). |
| `import_quantity` | Numeric | The net weight of imports, normalized during ETL to match the `dim_product` unit scale. |
| `import_value` | Numeric | The total customs value of the imports in USD. |

---

## 4. Dataset C: GADM (Administrative Boundaries)

**Source:** Global Administrative Areas (GADM 4.1) for Cameroon (ISO3: CMR).
**Description:** Geographic boundaries and centroid coordinates for Cameroon's administrative hierarchy (Regions and Subdivisions/Markets).

### Data Dictionary: `dim_region` (Real)
| Column | Data Type | Description |
| :--- | :--- | :--- |
| `region_id` | Integer (PK) | Unique identifier for the region. |
| `region_name` | String | The 10 official regions of Cameroon (e.g., Centre, Littoral, Adamawa). |
| `latitude` | Numeric | Representative centroid latitude. |
| `longitude` | Numeric | Representative centroid longitude. |

### Data Dictionary: `dim_market` (Real)
| Column | Data Type | Description |
| :--- | :--- | :--- |
| `market_id` | Integer (PK) | Unique identifier for the subdivision. |
| `market_name` | String | The name of the subdivision (arrondissement). |
| `region_id` | Integer (FK) | Foreign key linking to the parent region. |
| `latitude` | Numeric | Centroid latitude of the subdivision. |
| `longitude` | Numeric | Centroid longitude of the subdivision. |

---

