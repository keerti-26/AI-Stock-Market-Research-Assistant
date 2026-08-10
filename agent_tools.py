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
    summary = (
        f"{ticker} on {snapshot_date}: closed at {close_price} "
        f"({direction} {abs(pct_change):.2f}% from open of {open_price}). "
        f"Day range: {low_price}-{high_price}. Volume: {volume:,}."
    )
    conn = _get_connection()
    try:
        with conn.cursor() as curr:
            curr.execute(
                "Select company_name, description from companies where ticker = %s",
                (ticker,),
            )
            company_row = curr.fetchone()
    finally:
        conn.close()
    if company_row and company_row[0]:
        company_name, sector = company_row
        prefix = f"{company_name}"
        if sector:
            prefix += f" ({sector})"
        summary = f"{prefix} — {summary}"
    return summary

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

def manage_watchlist(action: str, ticker: str, user_id: str = "demo_user") -> str:
    """
    Add or remove a ticker from the user's watchlist. action must be
    "add" or "remove" — validated before touching the database, same
    pattern as save_research_note.
    """
    action = action.strip().lower()
    ticker = ticker.strip().upper()
 
    if action not in ("add", "remove"):
        return f"Rejected: action must be 'add' or 'remove', got '{action}'."
    if not ticker or not ticker.isalnum() or len(ticker) > 10:
        return f"Rejected: '{ticker}' doesn't look like a valid ticker symbol."
 
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            if action == "add":
                cur.execute(
                    """
                    INSERT INTO watchlist_tickers (user_id, ticker)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, ticker) DO NOTHING
                    """,
                    (user_id, ticker),
                )
                message = f"Added {ticker} to your watchlist."
            else:
                cur.execute(
                    "DELETE FROM watchlist_tickers WHERE user_id = %s AND ticker = %s",
                    (user_id, ticker),
                )
                message = (
                    f"Removed {ticker} from your watchlist."
                    if cur.rowcount > 0
                    else f"{ticker} wasn't on your watchlist."
                )
        conn.commit()
    finally:
        conn.close()
 
    return message

def compare_tickers(tickers: list[str]) -> str:
    """
    Compare price/fundamentals across multiple tickers side by side.
    Reuses the same price_snapshots + companies lookup as
    get_price_summary, just runs it for each ticker and formats a
    side-by-side comparison instead of a single summary.
    """
    tickers = [t.strip().upper() for t in tickers if t.strip()]
    if len(tickers) < 2:
        return "Need at least 2 tickers to compare."
 
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            rows = {}
            for ticker in tickers:
                cur.execute(
                    """
                    SELECT snapshot_date, open_price, close_price, high_price, low_price, volume
                    FROM price_snapshots
                    WHERE ticker = %s
                    ORDER BY snapshot_date DESC
                    LIMIT 1
                    """,
                    (ticker,),
                )
                price_row = cur.fetchone()
 
                cur.execute(
                    "SELECT company_name, sic_description, market_cap FROM companies WHERE ticker = %s",
                    (ticker,),
                )
                company_row = cur.fetchone()
 
                rows[ticker] = (price_row, company_row)
    finally:
        conn.close()
 
    lines = []
    for ticker, (price_row, company_row) in rows.items():
        if price_row is None:
            lines.append(f"{ticker}: no price data found.")
            continue
 
        snapshot_date, open_price, close_price, high_price, low_price, volume = price_row
        change = close_price - open_price
        pct_change = (change / open_price * 100) if open_price else 0
        direction = "up" if change >= 0 else "down"
 
        line = (
            f"{ticker}: close {close_price} ({direction} {abs(pct_change):.2f}%), "
            f"range {low_price}-{high_price}, volume {volume:,}"
        )
        if company_row and company_row[0]:
            company_name, sector, market_cap = company_row
            extras = [company_name]
            if sector:
                extras.append(sector)
            if market_cap:
                extras.append(f"market cap {market_cap:,.0f}")
            line = f"{line} — {', '.join(extras)}"
 
        lines.append(line)
 
    return "\n".join(lines)        

if __name__ == "__main__":
    print(get_price_summary("AAPL"))
    # print()
    # print(search_news("rising interest rates impact on banking sector", "AAPL"))
    # print(save_research_notes("AAPL", "Bank of America remains one of Berkshire's largest holdings"))
    # print(_get_connection())