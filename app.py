"""
Streamlit frontend for the AI Stock Market Research Assistant.
"""
import streamlit as st
from agent import run_agent
from agent_tools import _get_connection

st.set_page_config(page_title="Stock Research Assistant", page_icon="📈", layout="wide")

def get_watch_list_tickers() -> list[str]:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("Select distinct ticker from watchlist_tickers order by ticker")
            return[row[0] for row in cur.fetchall()]
    finally:
        conn.close()

def get_recent_notes(limit: int = 5) -> list[tuple]:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ticker, note_text, created_at
                FROM research_notes
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()
    finally:
        conn.close()
# ---- Sidebar: watchlist + recent notes ----
with st.sidebar:
    st.header("📋 Watchlist")
    try:
        tickers = get_watchlist_tickers()
        for ticker in tickers:
            st.markdown(f"**{ticker}**")
    except Exception as e:
        st.error(f"Couldn't load watchlist: {e}")
 
    st.divider()
    st.header("📝 Recent Notes")
    try:
        notes = get_recent_notes()
        if not notes:
            st.caption("No notes saved yet.")
        for ticker, note_text, created_at in notes:
            with st.expander(f"{ticker} — {created_at.strftime('%b %d, %I:%M %p')}"):
                st.write(note_text)
    except Exception as e:
        st.error(f"Couldn't load notes: {e}")
# ---- Main: chat ----
st.title("📈 AI Stock Market Research Assistant")
st.caption("Ask about prices, news, or say things like \"save a note on AAPL that...\"")

