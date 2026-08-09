-- 3. News articles (pulled)
CREATE TABLE news_articles (
    article_id      SERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    headline        TEXT NOT NULL,
    body_text       TEXT NOT NULL,
    source          TEXT,
    published_at    TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);