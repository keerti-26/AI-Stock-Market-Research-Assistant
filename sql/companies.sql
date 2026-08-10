--Companies — reference data from Massive's Ticker Overview endpoint
-- (GET /v3/reference/tickers/{ticker}).
CREATE TABLE IF NOT EXISTS companies (
    ticker              TEXT PRIMARY KEY,
    company_name        TEXT,
    description         TEXT,
    sic_code            TEXT,
    sic_description     TEXT,
    market_cap          NUMERIC(20,2),
    homepage_url        TEXT,
    primary_exchange    TEXT,
    total_employees     INTEGER,
    list_date           DATE,
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);