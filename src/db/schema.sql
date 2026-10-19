-- src/db/schema.sql
-- Star schema for the Cameroon FMCG Demand Forecasting & Inventory Intelligence Platform.

DROP TABLE IF EXISTS fact_sales CASCADE;
DROP TABLE IF EXISTS fact_market_price CASCADE;
DROP TABLE IF EXISTS fact_trade CASCADE;
DROP TABLE IF EXISTS dim_customer CASCADE;
DROP TABLE IF EXISTS dim_market CASCADE;
DROP TABLE IF EXISTS dim_product CASCADE;
DROP TABLE IF EXISTS dim_region CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;

-- =========================================================
-- Dimensions
-- =========================================================

CREATE TABLE dim_date (
    date_id     INTEGER PRIMARY KEY,
    date        DATE NOT NULL,
    month       INTEGER,
    quarter     INTEGER,
    year        INTEGER,
    week        INTEGER,
    is_holiday  INTEGER DEFAULT 0
);

CREATE TABLE dim_region (
    region_id   SERIAL PRIMARY KEY,
    region_name TEXT UNIQUE NOT NULL,
    latitude    NUMERIC(9,6),
    longitude   NUMERIC(9,6)
);

CREATE TABLE dim_market (
    market_id   SERIAL PRIMARY KEY,
    market_name TEXT NOT NULL,
    region_id   INTEGER REFERENCES dim_region(region_id),
    latitude    NUMERIC(9,6),
    longitude   NUMERIC(9,6),
    UNIQUE (market_name, region_id)
);

CREATE TABLE dim_product (
    product_id   SERIAL PRIMARY KEY,
    product_name TEXT NOT NULL,
    category     TEXT,
    unit         TEXT,
    brand        TEXT
);

CREATE TABLE dim_customer (
    customer_id   SERIAL PRIMARY KEY,
    customer_type TEXT,
    region_id     INTEGER REFERENCES dim_region(region_id),
    market_id     INTEGER REFERENCES dim_market(market_id)
);

CREATE TABLE fact_sales (
    sale_id     BIGSERIAL PRIMARY KEY,
    date_id     INTEGER REFERENCES dim_date(date_id),
    product_id  INTEGER REFERENCES dim_product(product_id),
    customer_id INTEGER REFERENCES dim_customer(customer_id),
    region_id   INTEGER REFERENCES dim_region(region_id),
    market_id   INTEGER REFERENCES dim_market(market_id),
    quantity    NUMERIC(12,3) CHECK (quantity >= 0),
    unit_price  NUMERIC(12,2) CHECK (unit_price >= 0),
    discount    NUMERIC(5,4)  CHECK (discount BETWEEN 0 AND 1),
    revenue     NUMERIC(14,2) GENERATED ALWAYS AS
                (quantity * unit_price * (1 - discount)) STORED
);

CREATE TABLE fact_market_price (
    market_id  INTEGER REFERENCES dim_market(market_id),
    product_id INTEGER REFERENCES dim_product(product_id),
    date_id    INTEGER REFERENCES dim_date(date_id),
    price      NUMERIC(12,2),
    trust      NUMERIC(5,2),
    PRIMARY KEY (market_id, product_id, date_id)
);

CREATE TABLE fact_trade (
    date_id          INTEGER REFERENCES dim_date(date_id),
    product_id       INTEGER REFERENCES dim_product(product_id),
    partner_country  TEXT,
    import_quantity  NUMERIC(16,3),
    import_value     NUMERIC(18,2),
    PRIMARY KEY (date_id, product_id, partner_country)
);

-- =========================================================
-- Indexes on foreign keys and common filters
-- =========================================================

CREATE INDEX idx_fact_sales_date          ON fact_sales(date_id);
CREATE INDEX idx_fact_sales_product       ON fact_sales(product_id);
CREATE INDEX idx_fact_sales_region        ON fact_sales(region_id);
CREATE INDEX idx_fact_sales_prod_region   ON fact_sales(product_id, region_id, date_id);

CREATE INDEX idx_fact_market_price_date   ON fact_market_price(date_id);
CREATE INDEX idx_fact_market_price_prod   ON fact_market_price(product_id);

CREATE INDEX idx_fact_trade_date          ON fact_trade(date_id);
CREATE INDEX idx_fact_trade_product       ON fact_trade(product_id);

CREATE INDEX idx_dim_market_region        ON dim_market(region_id);
CREATE INDEX idx_dim_customer_region      ON dim_customer(region_id);