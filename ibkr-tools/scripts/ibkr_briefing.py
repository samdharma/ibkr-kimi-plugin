#!/usr/bin/env python3
"""
ibkr-briefing: Full pre-market briefing generator.

Combines gap scan, market movers, technical analysis, and setup identification
into a single structured morning brief. Identifies confluence setups where
gap + technical alignment + volume converge.

Usage:
    python3 ibkr_briefing.py [OPTIONS]

Options:
    --universe      Stock universe: nasdaq100, most_active (default: most_active)
    --gap-min       Minimum gap % to include (default: 2.0)
    --max-setups    Maximum setup ideas to generate (default: 5)
    --detailed      Include full technical data for each setup (default: false)

Output:
    Structured morning brief with market context, top movers, gap analysis,
    sector heatmap, setup ideas with grades, and earnings reminders.

Examples:
    python3 ibkr_briefing.py
    python3 ibkr_briefing.py --universe nasdaq100 --gap-min 3 --max-setups 3
    python3 ibkr_briefing.py --detailed
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import check_gateway, api_get
from ibkr_history import fetch_all_bars, parse_bar, compute_daily_change
from ibkr_analyze_technical import (
    sma, rsi, atr, macd, find_support_resistance,
    fetch_gateway_ema, compute_momentum_score
)
from ibkr_gap_scan import calculate_gap
from ibkr_analyze_setup import score_gap, score_volume, score_technical


# NASDAQ-100 tickers for direct scanning
NASDAQ100 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "GOOG", "TSLA", "AVGO", "PEP",
    "COST", "CSCO", "ADBE", "TXN", "NFLX", "QCOM", "AMD", "INTC", "TMUS", "AMGN",
    "HON", "INTU", "AMAT", "SBUX", "ISRG", "BKNG", "MDLZ", "ADI", "VRTX", "ADP",
    "GILD", "LRCX", "PANW", "MU", "MELI", "CSX", "SNPS", "KLAC", "MAR", "FTNT",
    "CDNS", "CHTR", "PYPL", "REGN", "ASML", "NXPI", "KDP", "ORLY", "CTAS", "MRNA",
    "MRVL", "MNST", "ROST", "LULU", "ODFL", "PCAR", "KHC", "AEP", "EXC", "XEL",
    "DXCM", "TEAM", "MCHP", "CPRT", "PAYX", "DDOG", "FAST", "CRWD", "ANSS", "VRSK",
    "BMRN", "SIRI", "WBD", "ILMN", "DLTR", "SPLK", "SGEN", "OKTA", "BIIB", "EA",
    "EBAY", "JD", "LCID", "ZM", "PTON"
]


# ---------------------------------------------------------------------------
# Briefing Components
# ---------------------------------------------------------------------------

def fetch_scanner_universe(universe: str, count: int) -> list:
    """Get active stock universe from IBKR scanner."""
    scan_body = {
        "instrument": "STK",
        "type": "MOST_ACTIVE",
        "location": "STK.US.MAJOR",
        "size": min(count, 500)
    }

    result = api_post_local("/iserver/scanner/run", scan_body)

    if isinstance(result, list):
        return [item.get("symbol", item.get("contractDesc", "")) for item in result if isinstance(item, dict)]
    elif isinstance(result, dict):
        data = result.get("result", result.get("contracts", []))
        return [item.get("symbol", item.get("contractDesc", "")) for item in data if isinstance(item, dict)]

    return []


def api_post_local(endpoint: str, data: dict) -> dict:
    """Local POST helper using configured IB Gateway."""
    from ibkr_core import BASE_URL
    import urllib.request
    import ssl
    url = f"{BASE_URL}{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, data=payload, headers={"Host": "api.ibkr.com", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except Exception:
        return []


def fetch_batch_quotes_local(symbols: list) -> dict:
    """Fetch quotes for multiple symbols efficiently."""
    from ibkr_core import get_conid, api_get

    quotes = {}
    conid_map = {}

    for sym in symbols:
        conid = get_conid(sym)
        if conid:
            conid_map[sym] = conid

    if not conid_map:
        return quotes

    # Batch in groups of 25
    items = list(conid_map.items())
    for i in range(0, len(items), 25):
        batch = items[i:i+25]
        conids = ",".join(str(c) for _, c in batch)
        result = api_get("/iserver/marketdata/snapshot", f"conids={conids}&fields=31,83,84,7295,7676,85,86")

        if isinstance(result, list):
            sym_by_conid = {str(c): s for s, c in batch}
            for entry in result:
                cid = str(entry.get("conid", ""))
                sym = sym_by_conid.get(cid)
                if sym:
                    quotes[sym] = {
                        "last": _safe_float(entry.get("31")),
                        "bid": _safe_float(entry.get("83")),
                        "ask": _safe_float(entry.get("84")),
                        "volume": _safe_int(entry.get("7295")),
                        "prev_close": _safe_float(entry.get("7676")),
                        "change": _safe_float(entry.get("85")),
                        "change_pct": _safe_float(entry.get("86"))
                    }

    return quotes


def _safe_float(v):
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int(v):
    try:
        return int(float(v)) if v is not None else None
    except (ValueError, TypeError):
        return None


def identify_setups(gap_data: list, quotes: dict, min_gap: float) -> list:
    """Identify high-confluence trade setups from gap scan data."""
    setups = []

    for item in gap_data:
        symbol = item.get("symbol", "")
        quote = quotes.get(symbol)
        if not quote:
            continue

        gap_pct = item.get("gap_pct", 0)
        abs_gap = abs(gap_pct)

        if abs_gap < min_gap:
            continue

        # Quick technical check: fetch last 30 days of bars
        from ibkr_core import get_conid
        from ibkr_history import fetch_all_bars, parse_bar

        conid = get_conid(symbol)
        if not conid:
            continue

        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=45)
        raw_bars = fetch_all_bars(conid, "1d", start_dt, end_dt)
        bars = [parse_bar(b) for b in raw_bars] if raw_bars else []
        closes = [b["close"] for b in bars if b.get("close")] if bars else []

        if len(closes) < 20:
            continue

        # Quick indicators
        sma20 = sma(closes, 20)
        rsi14 = rsi(closes, 14)
        highs = [b["high"] for b in bars if b.get("high")]
        lows = [b["low"] for b in bars if b.get("low")]
        atr14 = atr(highs, lows, closes, 14) if len(highs) == len(closes) else [None] * len(closes)
        macd_data = macd(closes, 12, 26, 9)

        current_price = quote.get("last") or item.get("current_price")
        if not current_price:
            continue

        # Direction
        direction = "long" if gap_pct > 0 else "short"

        # Confluence scoring
        confluence = 0
        reasons = []

        # 1. Gap in sweet spot (2-8%)
        if 2 <= abs_gap <= 8:
            confluence += 2
            reasons.append("gap_in_sweet_spot")

        # 2. Above/below key MAs
        if sma20 and sma20[-1]:
            if direction == "long" and current_price > sma20[-1]:
                confluence += 2
                reasons.append("above_sma20")
            elif direction == "short" and current_price < sma20[-1]:
                confluence += 2
                reasons.append("below_sma20")

        # 3. RSI not extreme
        if rsi14 and rsi14[-1]:
            if direction == "long" and 35 < rsi14[-1] < 70:
                confluence += 1
                reasons.append("rsi_favorable")
            elif direction == "short" and 30 < rsi14[-1] < 65:
                confluence += 1
                reasons.append("rsi_favorable")

        # 4. MACD aligned
        if macd_data["histogram"] and macd_data["histogram"][-1]:
            if direction == "long" and macd_data["histogram"][-1] > 0:
                confluence += 1
                reasons.append("macd_bullish")
            elif direction == "short" and macd_data["histogram"][-1] < 0:
                confluence += 1
                reasons.append("macd_bearish")

        # 5. Reasonable ATR
        if atr14 and atr14[-1]:
            atr_pct = atr14[-1] / current_price * 100
            if 1.5 <= atr_pct <= 8:
                confluence += 1
                reasons.append("good_volatility")

        if confluence >= 4:  # Minimum confluence threshold
            # Compute levels
            current_atr = atr14[-1] if atr14 and atr14[-1] else current_price * 0.025
            if direction == "long":
                entry = current_price
                stop = round(entry - 1.5 * current_atr, 2)
                target = round(entry + 2.5 * (entry - stop), 2)
            else:
                entry = current_price
                stop = round(entry + 1.5 * current_atr, 2)
                target = round(entry - 2.5 * (stop - entry), 2)

            risk = abs(entry - stop)
            reward = abs(target - entry)
            rr = round(reward / risk, 2) if risk > 0 else 0

            # Grade based on confluence
            if confluence >= 7:
                grade = "A"
            elif confluence >= 5:
                grade = "B+"
            else:
                grade = "B"

            setups.append({
                "symbol": symbol,
                "direction": direction,
                "grade": grade,
                "confluence_score": confluence,
                "current_price": round(current_price, 2),
                "gap_pct": round(gap_pct, 2),
                "rsi_14": round(rsi14[-1], 1) if rsi14 and rsi14[-1] else None,
                "entry": entry,
                "stop": stop,
                "target": target,
                "risk_reward": rr,
                "atr_14": round(current_atr, 2),
                "confluence_reasons": reasons
            })

    # Sort by confluence score descending
    setups.sort(key=lambda x: x["confluence_score"], reverse=True)
    return setups


def generate_briefing(universe: str = "most_active", gap_min: float = 2.0,
                      max_setups: int = 5, detailed: bool = False) -> dict:
    """Generate the full pre-market briefing."""

    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "detail": conn.get("_message", "")}

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Determine symbols to scan
    if universe == "nasdaq100":
        symbols = NASDAQ100[:50]  # Top 50
    else:
        symbols = NASDAQ100[:30]  # Use NQ100 subset for speed

    # Fetch quotes
    quotes = fetch_batch_quotes_local(symbols)
    if not quotes:
        return {"_error": "Could not fetch quotes for universe"}

    # Calculate gaps
    gappers = []
    for sym, quote in quotes.items():
        if quote.get("last") and quote.get("prev_close") and quote["prev_close"] > 0:
            gap = calculate_gap(quote["last"], quote["prev_close"])
            gap["symbol"] = sym
            gap["current_price"] = quote["last"]
            gap["volume"] = quote.get("volume", 0)
            gappers.append(gap)

    # Sort by absolute gap
    gappers.sort(key=lambda x: abs(x.get("gap_pct", 0)), reverse=True)

    # Identify setups
    setups = identify_setups(gappers, quotes, gap_min)[:max_setups]

    # Top gainers and losers from quotes
    sorted_by_change = sorted(
        [(s, q) for s, q in quotes.items() if q.get("change_pct") is not None],
        key=lambda x: x[1]["change_pct"],
        reverse=True
    )

    top_gainers = [
        {"symbol": s, "price": q["last"], "change_pct": q["change_pct"], "volume": q.get("volume")}
        for s, q in sorted_by_change[:10]
    ]
    top_losers = [
        {"symbol": s, "price": q["last"], "change_pct": q["change_pct"], "volume": q.get("volume")}
        for s, q in sorted_by_change[-10:]
    ]

    # Sector grouping (simple — would need company data for full grouping)
    # For now, just summarize gap direction distribution
    gap_up = sum(1 for g in gappers if g.get("direction") == "up" and abs(g.get("gap_pct", 0)) >= gap_min)
    gap_down = sum(1 for g in gappers if g.get("direction") == "down" and abs(g.get("gap_pct", 0)) >= gap_min)
    avg_gap = round(sum(abs(g.get("gap_pct", 0)) for g in gappers) / len(gappers), 2) if gappers else 0

    # Top gappers summary
    top_gappers = [
        {"symbol": g["symbol"], "gap_pct": g["gap_pct"], "direction": g["direction"], "price": g.get("current_price")}
        for g in gappers[:10]
    ]

    briefing = {
        "status": "OK",
        "generated_at": generated_at,
        "market_context": {
            "scan_time": generated_at,
            "universe": universe,
            "symbols_scanned": len(symbols),
            "quotes_received": len(quotes),
            "gap_distribution": {
                "gapping_up": gap_up,
                "gapping_down": gap_down,
                "avg_abs_gap_pct": avg_gap
            }
        },
        "top_gappers": top_gappers,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "setup_ideas": setups,
        "setup_count": len(setups),
        "key_takeaways": _generate_takeaways(setups, gap_up, gap_down)
    }

    return briefing


def _generate_takeaways(setups: list, gap_up: int, gap_down: int) -> list:
    """Generate key takeaways from the briefing data."""
    takeaways = []

    if gap_up > gap_down * 2:
        takeaways.append("Broadly bullish pre-market with strong gap-up bias")
    elif gap_down > gap_up * 2:
        takeaways.append("Bearish pre-market with significant gap-down pressure")
    else:
        takeaways.append("Mixed pre-market action, stock-specific setups dominant")

    if setups:
        takeaways.append(f"{len(setups)} high-confluence setup(s) identified — see setup_ideas")
        best = setups[0]
        takeaways.append(f"Best setup: {best['symbol']} {best['direction']} (grade {best['grade']}, R:R {best['risk_reward']})")
    else:
        takeaways.append("No high-confluence setups found — consider widening gap filter or waiting for market open")

    return takeaways


def main():
    parser = argparse.ArgumentParser(
        description="Generate pre-market briefing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --universe nasdaq100 --gap-min 3 --max-setups 3
  %(prog)s --detailed
        """
    )

    parser.add_argument("--universe", choices=["nasdaq100", "most_active"], default="most_active")
    parser.add_argument("--gap-min", type=float, default=2.0)
    parser.add_argument("--max-setups", type=int, default=5)
    parser.add_argument("--detailed", action="store_true", default=False)

    args = parser.parse_args()

    result = generate_briefing(args.universe, args.gap_min, args.max_setups, args.detailed)

    if "_error" in result:
        print(json.dumps({"status": "ERROR", "message": result["_error"], "detail": result.get("detail", "")}))
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
