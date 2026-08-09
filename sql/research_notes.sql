CREATE TABLE research_notes (
    note_id         SERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL DEFAULT 'demo_user',
    ticker          TEXT NOT NULL,
    note_text       TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);