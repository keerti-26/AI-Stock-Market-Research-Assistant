--3b. Article chunks — one article splits into several overlapping ~200-word
-- chunks, each embedded separately. all-MiniLM-L6-v2 truncates at ~256
-- word-pieces, so embedding a full article whole silently drops everything
-- past the first paragraph. Chunking + storing multiple rows per article
-- fixes that: retrieval matches against whichever chunk is actually relevant,
-- not just the article's opening lines.
CREATE TABLE article_chunks (
    chunk_id        SERIAL PRIMARY KEY,
    article_id      INTEGER NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       VECTOR(384),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (article_id, chunk_index)
);

CREATE INDEX ON article_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);