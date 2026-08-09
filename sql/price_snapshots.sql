-- 2. Price snapshots (pulled from Massive API by the Spark job)
CREATE TABLE price_snapshots (
    snapshot_id     SERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    snapshot_date   DATE NOT NULL,
    open_price      NUMERIC(12,4),
    close_price     NUMERIC(12,4),
    high_price      NUMERIC(12,4),
    low_price       NUMERIC(12,4),
    volume          BIGINT,
    market_cap      NUMERIC(20,2),
    pe_ratio        NUMERIC(10,2),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, snapshot_date)
);