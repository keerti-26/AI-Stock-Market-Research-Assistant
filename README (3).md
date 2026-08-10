# AI Stock Market Research Assistant

A Databricks AI Bootcamp capstone project. Users track a personal watchlist of tickers, ask natural-language questions about prices and news, and the agent pulls real market data, retrieves relevant news via semantic search, and can act on the user's behalf — updating their watchlist and logging research notes.

## What it does

Ask things like:
- *"How has AAPL been doing recently?"*
- *"What's the latest news on regional banks and rising interest rates?"*
- *"Compare AAPL and MSFT for me."*
- *"Add TSLA to my watchlist."*
- *"Save a note on MSFT saying strong cloud growth this quarter."*

The agent decides which tool(s) to call, runs them against live Lakebase data, and responds in plain language.

## Architecture

```
Massive Stocks API ─┐
                     ├─► Spark/notebook ingest pipeline ─► Lakebase (Postgres-compatible)
News + trafilatura ──┘         │                                │
                                ▼                                │
                    sentence-transformers embeddings             │
                    (chunked, pgvector)                          │
                                │                                │
                                ▼                                ▼
                          article_chunks                  price_snapshots,
                                                            companies, etc.
                                          │
                                          ▼
                              Agent (Llama via Groq API)
                              5 tools: read + write against Lakebase
                                          │
                                          ▼
                              Streamlit chat UI (Databricks App)
```

**Stack:**
- **Ingestion:** Databricks notebook, Spark/pandas, pulling price + news data from the Massive Stocks API, with `trafilatura` scraping full article bodies beyond the API's short description field
- **Unstructured data processing:** news articles are chunked (~180 words, 40-word overlap) and embedded with `sentence-transformers` (`all-MiniLM-L6-v2`), stored as `vector` columns in Lakebase via pgvector
- **Data store:** Lakebase (Postgres-compatible) — 7 tables: `users`, `watchlist_tickers`, `price_snapshots`, `news_articles`, `article_chunks`, `research_notes`, `companies`
- **Agent:** Llama 3.1 8B Instant via Groq's OpenAI-compatible API, plain Python tool-calling loop (no framework) with 5 tools spanning read (price lookup, semantic news search, ticker comparison) and write (watchlist add/remove, research notes)
- **Frontend:** Streamlit, deployed as a Databricks App — chat interface plus a sidebar showing the live watchlist and recent notes

## Agent tools

| Tool | Type | What it does |
|---|---|---|
| `get_price_summary` | Read | Latest price snapshot + % change for a ticker, with company name/sector context |
| `search_news` | Read | Semantic search over embedded news chunks — matches by meaning, not keyword |
| `compare_tickers` | Read | Side-by-side price + fundamentals for 2+ tickers |
| `manage_watchlist` | Write | Add or remove a ticker from the user's watchlist |
| `save_research_note` | Write | Log a note tied to a ticker for later reference |

## Design decisions worth calling out

- **Chunked embeddings, not whole-article:** `all-MiniLM-L6-v2` silently truncates around 256 word-pieces. Embedding full articles as a single vector meant retrieval only ever "saw" the opening paragraph. Chunking fixed this — the schema was restructured mid-build to add `article_chunks` once this was caught.
- **Open-source model via Groq, not Databricks-native serving:** Databricks Free Edition's pay-per-token Foundation Model APIs are currently unreliable/blocked for this workspace tier. Groq (hosting Llama) was used instead — called as a plain external API from within the Databricks notebook/app, the same pattern used for the Massive API client, so the rest of the Databricks-native architecture is unaffected.
- **Model swapped from Llama 3.3 70B to Llama 3.1 8B Instant:** hit a known, documented Groq issue where Llama occasionally emits a malformed tool-call format that Groq's API rejects outright (`tool_use_failed`). The smaller model plus disabling parallel tool calls reduced how often this occurs; the agent loop also has retry + fallback recovery logic so a single bad generation doesn't surface as a raw error to the user.
- **pgvector inside Lakebase rather than a separate Databricks Vector Search index:** kept the whole system on one database connection instead of standing up a second retrieval system, given the project timeline.

## Future enhancements

Scope was deliberately trimmed to hit the build timeline. In priority order, what's next:

1. **`analysis_reports` table + tool** — a "generate and save a full analysis report" capability that orchestrates the existing price + news tools into a single synthesized, saved report, rather than one-off notes.
2. **"Notable moves since last visit"** — track a `last_viewed_at` timestamp per user, compare current price/news against that baseline, and proactively surface what changed. Needs a small schema addition and a new read tool.
3. **Historical price trends, not just latest snapshot** — currently `get_price_summary` only reads the most recent `price_snapshots` row. A real trend/performance-over-time view needs a different Massive API endpoint (an aggregates/range endpoint rather than `/prev`) and a richer summary that reasons over multiple days.
4. **Filings and earnings-call embeddings** — the semantic retrieval layer currently only covers news. Adding SEC filings excerpts and earnings-call summaries as additional embedded sources would round out the "context engineering" requirement more fully and give the agent deeper fundamental context.
5. **A proper `watchlists` parent table** — currently `watchlist_tickers` stands alone with a plain `user_id` string. A parent table would support multiple named watchlists per user (e.g. "Tech" vs. "Banking") rather than one flat list.
6. **Stricter watchlist validation** — `manage_watchlist` currently only checks that a ticker string looks well-formed; it doesn't verify the ticker actually exists via Massive before adding it.
7. **Model upgrade path** — re-evaluate Llama 3.3 70B (or another tool-calling-reliable model) for better reasoning quality on `compare_tickers` and synthesized summaries, once Groq's tool-call formatting issue is less of a risk, or once there's headroom to test more thoroughly.
8. **Distributed embedding** — the ingest pipeline currently embeds sequentially rather than via a distributed Spark Pandas UDF; fine at the current 3-ticker scale, but wouldn't hold up if the watchlist grows significantly.

## Known limitations

- Single hardcoded demo user (`demo_user`) — no real authentication/multi-user support
- Watchlist seeded with 3 tickers (AAPL, MSFT, ZION); tested at this scale, not validated for a large watchlist
- `manage_watchlist` doesn't verify a ticker is real before adding it
- Price data reflects the most recent snapshot only, not intraday or historical series
