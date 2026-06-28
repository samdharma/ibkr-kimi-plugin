#!/usr/bin/env python3
"""
ibkr-analyze-finnhub: News, earnings, sentiment, and analyst data enrichment.

Fetches from Finnhub API (free tier: 60 calls/min, 500K/month):
- Company news with sentiment scoring
- Upcoming earnings dates
- EPS surprise history
- Analyst recommendations and price targets
- Company profile (sector, market cap, peers)

Requires FINNHUB_API_KEY environment variable.
Gracefully degrades when no API key or rate limit hit.

Usage:
    python3 ibkr_analyze_finnhub.py <SYMBOL> [OPTIONS]

Options:
    --news-count   Number of news items to fetch (default: 10)
    --from-date    News from date YYYY-MM-DD (default: 7 days ago)
    --sentiment    Enable sentiment analysis on headlines (default: true)

Examples:
    python3 ibkr_analyze_finnhub.py AAPL
    python3 ibkr_analyze_finnhub.py TSLA --news-count 20
    python3 ibkr_analyze_finnhub.py NVDA --from-date 2026-06-25
"""

import sys
import os
import json
import ssl
import urllib.request
import urllib.error
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import print_json


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FINNHUB_BASE = "https://finnhub.io/api/v1"
API_KEY = os.getenv("FINNHUB_API_KEY", "")

# ---------------------------------------------------------------------------
# Sentiment Keywords (rule-based, no NLP library needed)
# ---------------------------------------------------------------------------

BULLISH_KEYWORDS = [
    "beat", "beats", "surge", "surges", "rally", "rallies", "soar", "soars", "jump", "jumps",
    "gain", "gains", "rise", "rises", "strong", "strength", "growth", "record", "breakout",
    "upgrade", "upgrades", "outperform", "buy", "bullish", "moon", "rocket", "partnership",
    "contract", "deal", "expansion", "innovation", "milestone", "profit", "profitable",
    "dividend", "buyback", "exceeds", "outlook", "guidance", "raised", "approval",
    "launch", "launches", " breakthrough"
]

BEARISH_KEYWORDS = [
    "miss", "misses", "plunge", "plunges", "crash", "crashes", "tumble", "tumbles",
    "drop", "drops", "fall", "falls", "decline", "declines", "weak", "weakness",
    "downgrade", "downgrades", "underperform", "sell", "bearish", "loss", "losses",
    "debt", "lawsuit", "investigation", "recall", "delay", "delays", "cut", "cuts",
    "layoff", "layoffs", "restructuring", "bankruptcy", "warning", "concern",
    "risk", "risks", "shortfall", "disappoint", "disappoints", "fraud"
]


def score_sentiment(headline: str) -> dict:
    """Simple keyword-based sentiment scoring."""
    headline_lower = headline.lower()
    bullish_count = sum(1 for word in BULLISH_KEYWORDS if word in headline_lower)
    bearish_count = sum(1 for word in BEARISH_KEYWORDS if word in headline_lower)

    if bullish_count > bearish_count:
        sentiment = "positive"
        score = min(bullish_count * 0.25, 1.0)
    elif bearish_count > bullish_count:
        sentiment = "negative"
        score = -min(bearish_count * 0.25, 1.0)
    else:
        sentiment = "neutral"
        score = 0.0

    return {
        "sentiment": sentiment,
        "score": round(score, 2),
        "bullish_keywords": bullish_count,
        "bearish_keywords": bearish_count
    }


# ---------------------------------------------------------------------------
# Finnhub API Client
# ---------------------------------------------------------------------------

def _ssl_ctx():
    ctx = ssl.create_default_context()
    return ctx


def finnhub_get(endpoint: str, params: str = "") -> dict:
    """Make a GET request to Finnhub API."""
    if not API_KEY:
        return {"_error": "FINNHUB_API_KEY not set", "_detail": "Export FINNHUB_API_KEY=your_key"}

    url = f"{FINNHUB_BASE}{endpoint}?token={API_KEY}"
    if params:
        url = f"{url}&{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ibkr-tools/1.0"})
        with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return {"_error": "Rate limited", "_detail": "Finnhub free tier: 60 calls/min. Wait and retry."}
        return {"_error": f"HTTP {e.code}", "_detail": e.read().decode("utf-8", errors="replace")[:200]}
    except Exception as e:
        return {"_error": "Request failed", "_detail": str(e)}


# ---------------------------------------------------------------------------
# Data Fetchers
# ---------------------------------------------------------------------------

def fetch_company_profile(symbol: str) -> dict:
    """Get company profile from Finnhub."""
    result = finnhub_get("/stock/profile2", f"symbol={symbol}")
    if "_error" in result:
        return result

    return {
        "name": result.get("name"),
        "sector": result.get("finnhubIndustry", result.get("sector")),
        "industry": result.get("industry"),
        "market_cap": result.get("marketCapitalization"),
        "employees": result.get("employeeTotal"),
        "website": result.get("weburl"),
        "country": result.get("country"),
        "currency": result.get("currency"),
        "exchange": result.get("exchange"),
        "ipo_date": result.get("ipo")
    }


def fetch_news(symbol: str, from_date: str, to_date: str, count: int = 10) -> list:
    """Fetch company news and score sentiment."""
    result = finnhub_get("/company-news", f"symbol={symbol}&from={from_date}&to={to_date}")
    if "_error" in result:
        return result

    if not isinstance(result, list):
        return []

    articles = []
    for item in result[:count]:
        headline = item.get("headline", "")
        sentiment = score_sentiment(headline)

        articles.append({
            "headline": headline,
            "source": item.get("source", ""),
            "datetime": datetime.fromtimestamp(item.get("datetime", 0)).strftime("%Y-%m-%d %H:%M:%S"),
            "url": item.get("url", ""),
            "sentiment": sentiment["sentiment"],
            "sentiment_score": sentiment["score"],
            "category": item.get("category", "")
        })

    return articles


def fetch_earnings(symbol: str) -> dict:
    """Fetch earnings calendar and EPS history."""
    today = datetime.now().strftime("%Y-%m-%d")
    future = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

    calendar = finnhub_get("/calendar/earnings", f"from={today}&to={future}&symbol={symbol}")
    eps_history = finnhub_get("/stock/earnings", f"symbol={symbol}")

    result = {"upcoming": None, "history": [], "days_to_next": None}

    # Parse upcoming earnings
    if isinstance(calendar, dict) and "earningsCalendar" in calendar:
        for event in calendar["earningsCalendar"]:
            if event.get("symbol") == symbol:
                date_str = event.get("date", "")
                if date_str:
                    try:
                        ed = datetime.strptime(date_str, "%Y-%m-%d")
                        days = (ed - datetime.now()).days
                        result["upcoming"] = {
                            "date": date_str,
                            "eps_estimate": event.get("epsEstimate"),
                            "revenue_estimate": event.get("revenueEstimate"),
                            "days_until": days
                        }
                        result["days_to_next"] = days
                    except ValueError:
                        pass
                break

    # Parse EPS history (last 4 quarters)
    if isinstance(eps_history, list):
        for entry in eps_history[:4]:
            result["history"].append({
                "period": entry.get("period", ""),
                "actual": entry.get("actual"),
                "estimate": entry.get("estimate"),
                "surprise": entry.get("surprise"),
                "surprise_pct": entry.get("surprisePercent")
            })

    return result


def fetch_analyst_data(symbol: str) -> dict:
    """Fetch analyst recommendations and price targets."""
    recommendations = finnhub_get("/stock/recommendation", f"symbol={symbol}")
    price_target = finnhub_get("/stock/price-target", f"symbol={symbol}")

    result = {
        "recommendation": "unknown",
        "consensus": {},
        "target_price": None,
        "current_price": None,
        "upside_pct": None
    }

    # Parse recommendations
    if isinstance(recommendations, list) and len(recommendations) > 0:
        latest = recommendations[0]
        total = sum(latest.get(k, 0) for k in ["strongBuy", "buy", "hold", "sell", "strongSell"])
        if total > 0:
            result["consensus"] = {
                "strong_buy": latest.get("strongBuy", 0),
                "buy": latest.get("buy", 0),
                "hold": latest.get("hold", 0),
                "sell": latest.get("sell", 0),
                "strong_sell": latest.get("strongSell", 0),
                "total": total,
                "period": latest.get("period", "")
            }

            # Determine consensus
            sb = result["consensus"]["strong_buy"]
            b = result["consensus"]["buy"]
            h = result["consensus"]["hold"]
            s = result["consensus"]["sell"]
            ss = result["consensus"]["strong_sell"]

            if (sb + b) / total >= 0.6:
                result["recommendation"] = "strong_buy" if sb > b else "buy"
            elif (sb + b) / total >= 0.4:
                result["recommendation"] = "buy"
            elif (s + ss) / total >= 0.4:
                result["recommendation"] = "sell" if s > ss else "strong_sell"
            else:
                result["recommendation"] = "hold"

    # Parse price target
    if isinstance(price_target, dict) and "_error" not in price_target:
        result["target_price"] = price_target.get("targetHigh")  # Use high target
        result["target_mean"] = price_target.get("targetMean")
        result["target_low"] = price_target.get("targetLow")
        result["target_high"] = price_target.get("targetHigh")
        result["number_of_analysts"] = price_target.get("numberOfAnalysts")

    return result


# ---------------------------------------------------------------------------
# Main Analysis
# ---------------------------------------------------------------------------

def analyze_finnhub(symbol: str, news_count: int = 10, from_date: str = None,
                    sentiment_enabled: bool = True) -> dict:
    """Run full Finnhub enrichment analysis."""

    if not API_KEY:
        return {
            "_degraded": True,
            "message": "FINNHUB_API_KEY not configured. Set it for news, earnings, and analyst data.",
            "setup": "export FINNHUB_API_KEY=your_free_key  # Get one at finnhub.io",
            "symbol": symbol,
            "company": {},
            "news": [],
            "sentiment": {"overall": "unknown", "score": 0},
            "earnings": {},
            "analysts": {}
        }

    to_date = datetime.now().strftime("%Y-%m-%d")
    if not from_date:
        from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    # Fetch all data
    profile = fetch_company_profile(symbol)
    news = fetch_news(symbol, from_date, to_date, news_count)
    earnings = fetch_earnings(symbol)
    analysts = fetch_analyst_data(symbol)

    # Aggregate sentiment
    if news and isinstance(news, list):
        scores = [a["sentiment_score"] for a in news]
        pos_count = sum(1 for a in news if a["sentiment"] == "positive")
        neg_count = sum(1 for a in news if a["sentiment"] == "negative")
        neu_count = sum(1 for a in news if a["sentiment"] == "neutral")
        avg_score = round(sum(scores) / len(scores), 3) if scores else 0

        if avg_score > 0.15:
            overall = "bullish"
        elif avg_score < -0.15:
            overall = "bearish"
        else:
            overall = "neutral"

        sentiment_summary = {
            "overall": overall,
            "score": avg_score,
            "bullish_count": pos_count,
            "bearish_count": neg_count,
            "neutral_count": neu_count,
            "total_articles": len(news)
        }
    else:
        sentiment_summary = {"overall": "unknown", "score": 0}

    # Calculate upside if we have target and current price
    upside = None
    if analysts.get("target_price") and profile.get("market_cap"):
        # We don't have current price here — user can compute from quote
        pass

    result = {
        "symbol": symbol,
        "data_source": "Finnhub (free tier)",
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "company": profile if "_error" not in profile else {},
        "news": news if isinstance(news, list) else [],
        "sentiment": sentiment_summary,
        "earnings": earnings if "_error" not in earnings else {},
        "analysts": analysts if "_error" not in analysts else {}
    }

    # Add any errors
    errors = []
    if isinstance(profile, dict) and "_error" in profile:
        errors.append(f"Profile: {profile['_error']}")
    if isinstance(news, dict) and "_error" in news:
        errors.append(f"News: {news['_error']}")
    if isinstance(earnings, dict) and "_error" in earnings:
        errors.append(f"Earnings: {earnings['_error']}")
    if isinstance(analysts, dict) and "_error" in analysts:
        errors.append(f"Analysts: {analysts['_error']}")

    if errors:
        result["_errors"] = errors
        result["_partial"] = True

    return result


def main():
    parser = argparse.ArgumentParser(
        description="News, earnings, and analyst data via Finnhub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s AAPL
  %(prog)s TSLA --news-count 20
  %(prog)s NVDA --from-date 2026-06-25

Note: Requires FINNHUB_API_KEY environment variable.
Get a free key at https://finnhub.io/register
        """
    )

    parser.add_argument("symbol", help="Stock ticker symbol")
    parser.add_argument("--news-count", type=int, default=10)
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--sentiment", type=lambda x: x.lower() == "true", default=True)

    args = parser.parse_args()

    result = analyze_finnhub(args.symbol.upper(), args.news_count, args.from_date, args.sentiment)

    # Degraded mode
    if result.get("_degraded"):
        print(json.dumps({"status": "DEGRADED", **result}, indent=2))
        sys.exit(0)

    if "_errors" in result:
        print(json.dumps({"status": "PARTIAL", **result}, indent=2))
        sys.exit(0)

    print(json.dumps({"status": "OK", **result}, indent=2))


if __name__ == "__main__":
    main()
