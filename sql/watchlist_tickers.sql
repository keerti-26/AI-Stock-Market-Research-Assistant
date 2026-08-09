
CREATE TABLE watchlist_tickers (
    watchlist_ticker_id SERIAL PRIMARY KEY,
    user_id             TEXT NOT NULL DEFAULT 'demo_user',
    ticker              TEXT NOT NULL,
    added_at            TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, ticker)
);