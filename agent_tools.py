import base64
from databricks.sdk import WorkspaceClient
import psycopg2
from sentence_transformers import SentenceTransformer

_w = WorkspaceClient()

_SECRET_SCOPE = "database"
_SECRET_URL = "lakebase-url"

def _get_connection():
    url = _w.secrets.get_secret(scope=_SECRET_SCOPE, key=_SECRET_URL)
    conn = base64.b64decode(url.value).decode("utf-8")
    return psycopg2.connect(conn)

def _get_embedding_model() -> SentenceTransformer:
    model = SentenceTransformer('all-MiniLM-L6-v2')
    return model

def get_price_summary(ticker:str) -> str:
    """
    Return a recent price snapshot for a ticker
    """
    ticker = ticker.strip().upper()
    conn = _get_connection()
    try:
        with conn.cursor() as curr:
            curr.execute(
            """
            Select snapshot_date, open_price, close_price, high_price, low_price, volume
            from price_snapshots
            where ticker =%s
            order by snapshot_date desc
            limit 1
            """,
            (ticker,)
        )
            row = curr.fetchone()
    finally:
        curr.close()
    if row is None:
        return f"No price data found for ticker:{ticker}"
    snapshot_date, open_price, close_price, high_price, low_price, volume = row 
    change = close_price - open_price
    direction = "up" if change>=0 else "down"
    pct_change = (change/open_price*100) if open_price else 0
    return(
        f"{ticker} on {snapshot_date}: closed at {close_price} "
        f"({direction} {abs(pct_change):.2f}% from open of {open_price}). "
        f"Day range: {low_price}-{high_price}. Volume: {volume:,}."
    )

def search_news(query:str, ticker:str | None = None, top_k:int=5) -> str:
    """
    Semantic search over article_chunks using pgvector cosine distance.
    Embeds `query` with the same model used at ingest time (all-MiniLM-L6-v2)
    so the vector space matches. Optionally filters to a single ticker.
    Returns a formatted string of the top matches, joined back to
    news_articles for headline/source/date — the agent reads this as
    context, so it's plain text, not raw rows.
    """
    embeddings_model = _get_embedding_model()
    query_embeddings = embeddings_model.encode(query).tolist()
    conn = _get_connection()
    try:
        with conn.cursor() as curr:
            if ticker:
                curr.execute(
                """
                Select a.headline, a.ticker, a.source, a.published_at, c.chunk_text,
                   c.embedding <-> %s::vector as distance
                from article_chunks as c
                inner join news_articles as a
                on c.article_id = a.article_id
                where a.ticker = %s
                order by distance asc
                limit %s
                """,
                (query_embeddings, ticker.strip().upper(), top_k),
                )
            else:
                curr.execute(
                """
                Select a.headline, a.ticker, a.source, a.published_at, c.chunk_text,
                   c.embedding <-> %s::vector as distance
                from article_chunks as c
                inner join news_articles as a
                on c.article_id = a.article_id
                order by distance asc
                limit %s
                """,
                (query_embeddings, top_k)
                )
            rows = curr.fetchall()
    finally:
        conn.close()
    if rows is None:
        return f"No news found for the: {query}"
    results = []
    for row in rows:
        headline, row_ticker, source, published_at, chunk_text, distance = row
        results.append(
            f"[{row_ticker}] {headline} ({source} {published_at})\n{chunk_text}"
        )
    return "\n\n".join(results)

def save_research_notes(ticker:str, notes_text:str, user:str="demo_user") -> str:
    """
    Save a research note tied to a ticker. This is a WRITE tool, so unlike
    the read tools above, inputs are validated before touching the database
    rather than trusted as-is from the model's arguments.
    """
    if ticker is None or ticker.strip()=="":
        return "ticker is required"
    if len(notes_text) == 0:
        return "Notes is empty"
    if len(notes_text)>5000:
        return "note text is too long (max 5000 characters)."
    conn = _get_connection()
    with conn.cursor() as curr:
        try:
            curr.execute(
                """
                Insert into research_notes(user_id, ticker, note_text)
                values( %s, %s, %s)
                RETURNING note_id
                """,
                (user, ticker.strip().upper(), notes_text)
            )
            note_id = curr.fetchone()[0]
            conn.commit()
        finally:
           conn.close()
    return f"Note saved successfully for {ticker.strip().upper()} (ID: {note_id})"

    
        

if __name__ == "__main__":
    # print(get_price_summary("AAPL"))
    # print()
    # print(search_news("rising interest rates impact on banking sector", "AAPL"))
    print(save_research_notes("AAPL", "Bank of America remains one of Berkshire's largest holdings"))
    # print(_get_connection())