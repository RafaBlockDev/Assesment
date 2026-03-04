"""Financial tools for the Stock Query Agent.

Each function is decorated with @tool so LangGraph / LangChain can
invoke them automatically during tool_use steps.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import yfinance as yf
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── In-memory document store (populated by load_documents) ──────────

_document_chunks: list[str] = []


# ── Real-time price ─────────────────────────────────────────────────


@tool
def retrieve_realtime_stock_price(ticker: str) -> dict:
    """Retrieve the current real-time stock price for a given ticker symbol.

    Uses Yahoo Finance (yfinance) to fetch the latest market data.

    Args:
        ticker: Stock ticker symbol (e.g. "AMZN", "AAPL", "GOOGL").

    Returns:
        A dictionary with keys:
            - ticker: The requested ticker symbol.
            - price: Current market price (regular market price).
            - currency: Currency of the price (e.g. "USD").
            - timestamp: ISO-8601 UTC timestamp of when the data was fetched.
            - change_percent: Percentage change from the previous close.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if not info or "regularMarketPrice" not in info:
            return {"error": f"No data found for ticker '{ticker}'."}

        price = info["regularMarketPrice"]
        prev_close = info.get("regularMarketPreviousClose", price)
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0

        return {
            "ticker": ticker.upper(),
            "price": round(price, 2),
            "currency": info.get("currency", "USD"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "change_percent": round(change_pct, 2),
        }
    except Exception as e:
        logger.error("Error fetching real-time price for %s: %s", ticker, e)
        return {"error": f"Failed to retrieve price for '{ticker}': {e}"}


# ── Historical prices ──────────────────────────────────────────────


@tool
def retrieve_historical_stock_price(
    ticker: str, start_date: str, end_date: str
) -> dict:
    """Retrieve historical stock prices for a given ticker and date range.

    Uses Yahoo Finance (yfinance) to download daily OHLCV data and computes
    a simple trend summary.

    Args:
        ticker: Stock ticker symbol (e.g. "AMZN").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.

    Returns:
        A dictionary with keys:
            - ticker: The requested ticker symbol.
            - start_date / end_date: The queried date range.
            - prices: List of daily records, each containing
              date, open, close, high, low, volume.
            - trend_direction: "up", "down", or "flat" based on first
              vs last closing price.
            - avg_price: Average closing price over the period.
    """
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date, end=end_date)

        if df.empty:
            return {
                "error": f"No historical data for '{ticker}' between {start_date} and {end_date}."
            }

        prices = [
            {
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "close": round(row["Close"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "volume": int(row["Volume"]),
            }
            for idx, row in df.iterrows()
        ]

        first_close = prices[0]["close"]
        last_close = prices[-1]["close"]
        avg_close = round(sum(p["close"] for p in prices) / len(prices), 2)

        if last_close > first_close * 1.005:
            trend = "up"
        elif last_close < first_close * 0.995:
            trend = "down"
        else:
            trend = "flat"

        return {
            "ticker": ticker.upper(),
            "start_date": start_date,
            "end_date": end_date,
            "prices": prices,
            "trend_direction": trend,
            "avg_price": avg_close,
        }
    except Exception as e:
        logger.error("Error fetching historical data for %s: %s", ticker, e)
        return {"error": f"Failed to retrieve historical data for '{ticker}': {e}"}


# ── Document search ────────────────────────────────────────────────


def load_documents(chunks: list[str]) -> None:
    """Populate the in-memory document store with text chunks.

    Call this at startup after splitting PDF documents with
    langchain-text-splitters.
    """
    global _document_chunks
    _document_chunks = chunks
    logger.info("Loaded %d document chunks into search index.", len(chunks))


@tool
def search_financial_documents(query: str) -> list[str]:
    """Search the financial knowledge base for relevant document chunks.

    Performs a simple keyword overlap search over pre-loaded PDF text
    chunks.  For production use, swap this with a vector store retriever.

    Args:
        query: Natural-language search query (e.g. "Amazon Q3 revenue").

    Returns:
        A list of the top-5 most relevant text chunks from the
        knowledge base, ranked by keyword overlap score.
    """
    if not _document_chunks:
        return ["No documents loaded in knowledge base."]

    query_tokens = set(query.lower().split())

    scored = []
    for chunk in _document_chunks:
        chunk_tokens = set(chunk.lower().split())
        overlap = len(query_tokens & chunk_tokens)
        if overlap > 0:
            scored.append((overlap, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [text for _, text in scored[:5]]

    return results if results else ["No relevant documents found for your query."]
