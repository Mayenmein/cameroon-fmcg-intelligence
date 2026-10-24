
-- ============================================================
-- Cameroon FMCG Demand & Inventory Intelligence Platform
-- Complete PostgreSQL schema
-- WARNING: Re-running drops all tables and their data.
-- ============================================================

BEGIN;

-- 1. DROP TABLES IN DEPENDENCY ORDER
DROP TABLE IF EXISTS fact_stockout_events CASCADE;
DROP TABLE IF EXISTS fact_delivery_events CASCADE;
DROP TABLE IF EXISTS fact_purchase_orders CASCADE;
DROP TABLE IF EXISTS fact_inventory_movements CASCADE;
DROP TABLE IF EXISTS fact_inventory_snapshot CASCADE;
DROP TABLE IF EXISTS fact_sales CASCADE;
DROP TABLE IF EXISTS fact_market_price CASCADE;
DROP TABLE IF EXISTS fact_trade CASCADE;

DROP TABLE IF EXISTS dim_customer CASCADE;
DROP TABLE IF EXISTS dim_wfp_market CASCADE;
DROP TABLE IF EXISTS dim_market CASCADE;
DROP TABLE IF EXISTS dim_product CASCADE;
DROP TABLE IF EXISTS dim_region CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;

-- 2. DIMENSION TABLES
CREATE TABLE dim_date (
    date_id INTEGER PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    month INTEGER CHECK (month BETWEEN 1 AND 12),
    quarter INTEGER CHECK (quarter BETWEEN 1 AND 4),
    year INTEGER,
    week INTEGER CHECK (week BETWEEN 1 AND 53),
    is_holiday INTEGER DEFAULT 0
        CHECK (is_holiday IN (0, 1))
);

CREATE TABLE dim_region (
    region_id SERIAL PRIMARY KEY,
    region_name TEXT UNIQUE NOT NULL,
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6)
);

CREATE TABLE dim_market (
    market_id SERIAL PRIMARY KEY,
    market_name TEXT NOT NULL,
    region_id INTEGER REFERENCES dim_region(region_id),
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6),
    UNIQUE (market_name, region_id)
);

CREATE TABLE dim_wfp_market (
    wfp_market_id SERIAL PRIMARY KEY,
    geo_id TEXT UNIQUE NOT NULL,
    market_name TEXT NOT NULL,
    adm1_name TEXT,
    adm2_name TEXT,
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6)
);

CREATE TABLE dim_product (
    product_id SERIAL PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT,
    unit TEXT,
    brand TEXT
);

CREATE TABLE dim_customer (
    customer_id SERIAL PRIMARY KEY,
    customer_type TEXT,
    region_id INTEGER REFERENCES dim_region(region_id),
    market_id INTEGER REFERENCES dim_market(market_id)
);

-- 3. EXISTING PUBLIC-DATA FACT TABLES
CREATE TABLE fact_market_price (
    wfp_market_id INTEGER REFERENCES dim_wfp_market(wfp_market_id),
    product_id INTEGER REFERENCES dim_product(product_id),
    date_id INTEGER REFERENCES dim_date(date_id),
    price NUMERIC(12,2),
    trust NUMERIC(5,2),
    PRIMARY KEY (wfp_market_id, product_id, date_id)
);

CREATE TABLE fact_trade (
    date_id INTEGER REFERENCES dim_date(date_id),
    product_id INTEGER REFERENCES dim_product(product_id),
    partner_country TEXT,
    import_quantity NUMERIC(16,3),
    import_value NUMERIC(18,2),
    PRIMARY KEY (date_id, product_id, partner_country)
);

-- 4. SIMULATED SALES
-- quantity = fulfilled sales (maps from sales_qty)
-- Demand and lost sales are retained for analysis.
-- Price is nullable because the simulator does not generate it.
CREATE TABLE fact_sales (
    sale_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER REFERENCES dim_date(date_id),
    product_id INTEGER NOT NULL REFERENCES dim_product(product_id),
    customer_id INTEGER NOT NULL REFERENCES dim_customer(customer_id),
    region_id INTEGER REFERENCES dim_region(region_id),
    market_id INTEGER REFERENCES dim_market(market_id),

    demand_qty NUMERIC(16,3) NOT NULL
        CHECK (demand_qty >= 0),
    quantity NUMERIC(16,3) NOT NULL
        CHECK (quantity >= 0),
    lost_sales_qty NUMERIC(16,3) NOT NULL
        CHECK (lost_sales_qty >= 0),

    unit_price NUMERIC(12,2)
        CHECK (unit_price >= 0),
    discount NUMERIC(5,4) NOT NULL DEFAULT 0
        CHECK (discount BETWEEN 0 AND 1),

    revenue NUMERIC(14,2) GENERATED ALWAYS AS
        (quantity * unit_price * (1 - discount)) STORED,

    CHECK (demand_qty = quantity + lost_sales_qty)
);

-- 5. SIMULATED INVENTORY SNAPSHOTS
CREATE TABLE fact_inventory_snapshot (
    date DATE NOT NULL,
    product_id INTEGER NOT NULL REFERENCES dim_product(product_id),
    opening_stock NUMERIC(16,3) NOT NULL CHECK (opening_stock >= 0),
    arrivals_qty NUMERIC(16,3) NOT NULL CHECK (arrivals_qty >= 0),
    demand_qty NUMERIC(16,3) NOT NULL CHECK (demand_qty >= 0),
    sales_qty NUMERIC(16,3) NOT NULL CHECK (sales_qty >= 0),
    lost_sales_qty NUMERIC(16,3) NOT NULL CHECK (lost_sales_qty >= 0),
    closing_stock NUMERIC(16,3) NOT NULL CHECK (closing_stock >= 0),
    on_order_qty NUMERIC(16,3) NOT NULL CHECK (on_order_qty >= 0),
    inventory_position NUMERIC(16,3) NOT NULL,
    PRIMARY KEY (date, product_id)
);

-- 6. SIMULATED INVENTORY MOVEMENTS
CREATE TABLE fact_inventory_movements (
    movement_id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    product_id INTEGER NOT NULL REFERENCES dim_product(product_id),
    movement_type TEXT NOT NULL,
    quantity_change NUMERIC(16,3) NOT NULL,
    reference_id TEXT,
    on_hand_after NUMERIC(16,3) NOT NULL
        CHECK (on_hand_after >= 0)
);

-- 7. SIMULATED PURCHASE ORDERS
CREATE TABLE fact_purchase_orders (
    order_id BIGINT PRIMARY KEY,
    order_date DATE NOT NULL,
    arrival_date DATE NOT NULL,
    product_id INTEGER NOT NULL REFERENCES dim_product(product_id),
    quantity NUMERIC(16,3) NOT NULL CHECK (quantity > 0),
    lead_time_days INTEGER NOT NULL CHECK (lead_time_days >= 0)
);

-- 8. SIMULATED DELIVERY EVENTS
CREATE TABLE fact_delivery_events (
    delivery_event_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES fact_purchase_orders(order_id),
    product_id INTEGER NOT NULL REFERENCES dim_product(product_id),
    arrival_date DATE NOT NULL,
    quantity_received NUMERIC(16,3) NOT NULL
        CHECK (quantity_received > 0)
);

-- 9. SIMULATED STOCKOUT EVENTS
CREATE TABLE fact_stockout_events (
    stockout_event_id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES dim_customer(customer_id),
    product_id INTEGER NOT NULL REFERENCES dim_product(product_id),
    demand_qty NUMERIC(16,3) NOT NULL CHECK (demand_qty > 0),
    fulfilled_qty NUMERIC(16,3) NOT NULL CHECK (fulfilled_qty >= 0),
    lost_sales_qty NUMERIC(16,3) NOT NULL CHECK (lost_sales_qty > 0),
    CHECK (demand_qty = fulfilled_qty + lost_sales_qty)
);

-- 10. INDEXES
CREATE INDEX idx_market_region
    ON dim_market (region_id);

CREATE INDEX idx_customer_region
    ON dim_customer (region_id);

CREATE INDEX idx_customer_market
    ON dim_customer (market_id);

CREATE INDEX idx_sales_date
    ON fact_sales (date_id);

CREATE INDEX idx_sales_product
    ON fact_sales (product_id);

CREATE INDEX idx_sales_region
    ON fact_sales (region_id);

CREATE INDEX idx_sales_product_region_date
    ON fact_sales (product_id, region_id, date_id);

CREATE INDEX idx_market_price_product_date
    ON fact_market_price (product_id, date_id);

CREATE INDEX idx_market_price_market_date
    ON fact_market_price (wfp_market_id, date_id);

CREATE INDEX idx_trade_product_date
    ON fact_trade (product_id, date_id);

CREATE INDEX idx_inventory_snapshot_product_date
    ON fact_inventory_snapshot (product_id, date);

CREATE INDEX idx_inventory_movements_product_date
    ON fact_inventory_movements (product_id, date);

CREATE INDEX idx_purchase_orders_product_date
    ON fact_purchase_orders (product_id, order_date);

CREATE INDEX idx_delivery_events_order
    ON fact_delivery_events (order_id);

CREATE INDEX idx_stockout_events_customer_date
    ON fact_stockout_events (customer_id, date);

CREATE INDEX idx_stockout_events_product_date
    ON fact_stockout_events (product_id, date);

COMMIT;
