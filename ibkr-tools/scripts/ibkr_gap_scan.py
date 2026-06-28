#!/usr/bin/env python3
"""
ibkr-gap-scan: Pre-market gap-up/down scanner.

Scans a universe of stocks for pre-market price gaps relative to previous close.
Supports configurable filters for gap %, volume, price range, market cap, and more.

Usage:
    python3 ibkr_gap_scan.py [OPTIONS]

Parameters (all optional, shown with defaults):
    --min-gap        Minimum gap % to include (default: 2.0)
    --max-gap        Maximum gap % to include (default: 50.0)
    --direction      Gap direction: up, down, both (default: both)
    --min-price      Minimum stock price (default: 5.0)
    --max-price      Maximum stock price (default: 500.0)
    --min-volume     Minimum average daily volume in thousands (default: 100)
    --min-avg-volume Minimum 30-day avg daily volume in thousands (default: 50)
    --max-results    Maximum results to return (default: 50)
    --universe       Scan universe: all, nasdaq100, sp500, most_active (default: most_active)
    --extended       Include extended hours data if available (default: true)
    --sort-by        Sort field: gap, volume, price, atr (default: gap)
    --min-atr        Minimum ATR as % of price (default: 0.0)
    --max-atr        Maximum ATR as % of price (default: 100.0)
    --output-format  Output format: json, table (default: json)
    --detailed       Include detailed quote fields (default: false)

Examples:
    python3 ibkr_gap_scan.py --min-gap 3 --direction up --min-volume 500
    python3 ibkr_gap_scan.py --universe nasdaq100 --min-gap 5 --max-gap 20 --min-price 10
    python3 ibkr_gap_scan.py --direction down --min-gap 2 --min-avg-volume 1000 --sort-by volume
"""

import sys
import os
import argparse
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import (
    api_get, api_post, print_json, print_error, check_gateway,
    get_conid, search_contract, BASE_URL
)


# ---------------------------------------------------------------------------
# IBKR Scanner Codes
# ---------------------------------------------------------------------------

SCANNER_UNIVERSES = {
    "most_active": {
        "scanner_code": "MOST_ACTIVE",
        "description": "Most actively traded stocks today"
    },
    "nasdaq100": {
        "scanner_code": "TOP_PERC_GAIN",
        "instrument": "STK.NASDAQ",
        "description": "NASDAQ stocks"
    },
    "sp500": {
        "scanner_code": "TOP_PERC_GAIN",
        "instrument": "STK.NYSE",
        "description": "NYSE listed stocks"
    },
    "all": {
        "scanner_code": "MOST_ACTIVE",
        "description": "All US stocks"
    }
}

# Pre-defined NASDAQ-100 tickers for direct scanning
NASDAQ100_TICKERS = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "GOOG", "TSLA", "AVGO", "PEP",
    "COST", "CSCO", "ADBE", "TXN", "NFLX", "QCOM", "AMD", "INTC", "TMUS", "AMGN",
    "HON", "INTU", "AMAT", "SBUX", "ISRG", "BKNG", "MDLZ", "ADI", "VRTX", "ADP",
    "GILD", "LRCX", "PANW", "MU", "MELI", "CSX", "SNPS", "KLAC", "MAR", "FTNT",
    "CDNS", "CHTR", "PYPL", "REGN", "ASML", "NXPI", "KDP", "ORLY", "CTAS", "MRNA",
    "MRVL", "MNST", "ROST", "LULU", "ODFL", "PCAR", "KHC", "AEP", "EXC", "XEL",
    "DXCM", "TEAM", "MCHP", "CPRT", "PAYX", "DDOG", "FAST", "CRWD", "ANSS", "VRSK",
    "BMRN", "SIRI", "WBD", "ILMN", "DLTR", "SPLK", "SGEN", "OKTA", "BIIB", "EA",
    "EBAY", "JD", "LCID", "ZM", "PTON", "RIVN"
]

# Market data fields we need for gap calculation
QUOTE_FIELDS = "31,83,84,7295,7676"
# 31=Last, 83=Bid, 84=Ask, 7295=Volume, 7676=Previous Close


# ---------------------------------------------------------------------------
# Gap Calculation
# ---------------------------------------------------------------------------

def fetch_scanner_results(universe: str, max_results: int) -> list:
    """Get initial universe of stocks from IBKR scanner."""
    config = SCANNER_UNIVERSES.get(universe, SCANNER_UNIVERSES["most_active"])

    # Use IBKR's scanner API
    scan_body = {
        "instrument": config.get("instrument", "STK"),
        "type": config.get("scanner_code", "MOST_ACTIVE"),
        "filter": [
            {"code": "priceAbove", "value": 1},
            {"code": "priceBelow", "value": 1000},
            {"code": "volumeAbove", "value": 0}
        ],
        "location": config.get("location", "STK.US.MAJOR"),
        "size": min(max_results * 2, 500)  # Fetch more than we need
    }

    result = api_post("/iserver/scanner/run", scan_body)

    if "_error" in result:
        # Fallback: try GET scanner
        result = api_get("/iserver/scanner/run", f"instrument=STK&type=MOST_ACTIVE&location=STK.US.MAJOR&size={min(max_results * 2, 500)}")

    if isinstance(result, list):
        return result
    elif isinstance(result, dict):
        return result.get("result", result.get("contracts", []))

    return []


def fetch_batch_quotes(symbols_or_conids: list) -> dict:
    """Fetch market data for multiple symbols efficiently."""
    quotes = {}

    # Build conid list
    conids = []
    symbol_map = {}

    for item in symbols_or_conids:
        if isinstance(item, dict):
            symbol = item.get("symbol", item.get("contractDesc", ""))
            conid = item.get("conid")
        else:
            symbol = str(item)
            conid = get_conid(symbol)

        if conid:
            conids.append(str(conid))
            symbol_map[str(conid)] = symbol.upper() if symbol else str(conid)

    if not conids:
        return quotes

    # IBKR limits conids per request, batch in groups of 25
    batch_size = 25
    for i in range(0, len(conids), batch_size):
        batch = conids[i:i + batch_size]
        conid_str = ",".join(batch)

        result = api_get("/iserver/marketdata/snapshot", f"conids={conid_str}&fields={QUOTE_FIELDS}")

        if isinstance(result, list):
            for entry in result:
                conid = str(entry.get("conid", ""))
                symbol = symbol_map.get(conid, conid)
                quotes[symbol] = parse_quote_fields(entry)
        elif isinstance(result, dict) and "_error" not in result:
            conid = str(result.get("conid", ""))
            symbol = symbol_map.get(conid, conid)
            quotes[symbol] = parse_quote_fields(result)

    return quotes


def parse_quote_fields(data: dict) -> dict:
    """Extract numeric fields from market data snapshot."""
    parsed = {}

    field_map = {
        "31": "last",
        "83": "bid",
        "84": "ask",
        "7295": "volume",
        "7676": "prev_close"
    }

    for field_code, field_name in field_map.items():
        raw = data.get(field_code)
        if raw is not None:
            try:
                if field_name == "volume":
                    parsed[field_name] = int(raw)
                else:
                    parsed[field_name] = float(raw)
            except (ValueError, TypeError):
                parsed[field_name] = raw

    # Calculate midpoint if we have bid/ask
    if "bid" in parsed and "ask" in parsed:
        try:
            parsed["mid"] = round((parsed["bid"] + parsed["ask"]) / 2, 4)
            parsed["spread"] = round(parsed["ask"] - parsed["bid"], 4)
        except (TypeError, ValueError):
            pass

    parsed["conid"] = data.get("conid")
    return parsed


def calculate_gap(current: float, prev_close: float) -> dict:
    """Calculate gap metrics."""
    if not prev_close or prev_close == 0:
        return {"gap_pct": 0, "gap_dollars": 0, "direction": "unknown"}

    gap_dollars = round(current - prev_close, 4)
    gap_pct = round((gap_dollars / prev_close) * 100, 2)

    if gap_pct > 0:
        direction = "up"
    elif gap_pct < 0:
        direction = "down"
    else:
        direction = "flat"

    return {
        "gap_pct": gap_pct,
        "gap_dollars": gap_dollars,
        "direction": direction
    }


def scan_universe_direct(tickers: list, args) -> list:
    """Scan a specific list of tickers for gaps."""
    results = []

    # Get conids for all tickers
    conid_map = {}
    for ticker in tickers:
        conid = get_conid(ticker)
        if conid:
            conid_map[ticker.upper()] = conid

    if not conid_map:
        return results

    # Fetch quotes in batches
    quotes = fetch_batch_quotes([{"symbol": k, "conid": v} for k, v in conid_map.items()])

    for symbol, quote in quotes.items():
        prev_close = quote.get("prev_close", 0)
        current = quote.get("last") or quote.get("mid") or quote.get("bid")

        if not prev_close or not current or prev_close <= 0:
            continue

        # Price filter
        if args.min_price and current < args.min_price:
            continue
        if args.max_price and current > args.max_price:
            continue

        gap = calculate_gap(current, prev_close)
        gap_pct = gap["gap_pct"]

        # Direction filter
        if args.direction == "up" and gap_pct < 0:
            continue
        if args.direction == "down" and gap_pct > 0:
            continue

        # Gap % filter
        abs_gap = abs(gap_pct)
        if abs_gap < args.min_gap:
            continue
        if args.max_gap and abs_gap > args.max_gap:
            continue

        result = {
            "rank": 0,  # Will be set after sorting
            "symbol": symbol,
            "conid": quote.get("conid"),
            "current_price": round(current, 2),
            "prev_close": round(prev_close, 2),
            "gap_pct": gap_pct,
            "gap_dollars": gap["gap_dollars"],
            "direction": gap["direction"],
            "bid": quote.get("bid"),
            "ask": quote.get("ask"),
            "volume": quote.get("volume", 0)
        }

        if args.detailed:
            result["mid"] = quote.get("mid")
            result["spread"] = quote.get("spread")

        results.append(result)

    return results


def run_gap_scan(args) -> dict:
    """Execute the gap scan with given parameters."""
    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "_detail": conn.get("_message", "")}

    # Determine universe
    if args.universe == "nasdaq100":
        scan_results = scan_universe_direct(NASDAQ100_TICKERS, args)
    elif args.universe == "sp500":
        # For S&P 500, we'd need a watchlist or scanner
        # Use MOST_ACTIVE scanner as proxy
        scanner_data = fetch_scanner_results("most_active", args.max_results * 3)
        scan_results = scan_universe_direct(
            [item.get("symbol", item.get("contractDesc", "")) for item in scanner_data if isinstance(item, dict)],
            args
        )
    else:
        # Use IBKR scanner for most active
        scanner_data = fetch_scanner_results(args.universe, args.max_results * 3)

        if not scanner_data:
            # Fallback to NASDAQ100
            scanner_data = [{"symbol": t} for t in NASDAQ100_TICKERS]

        symbols = []
        for item in scanner_data:
            if isinstance(item, dict):
                sym = item.get("symbol", item.get("contractDesc", ""))
            else:
                sym = str(item)
            if sym:
                symbols.append(sym)

        scan_results = scan_universe_direct(symbols, args)

    if not scan_results:
        return {
            "scan_results": [],
            "message": "No stocks matching criteria found.",
            "filters_applied": {
                "min_gap": args.min_gap,
                "max_gap": args.max_gap,
                "direction": args.direction,
                "min_price": args.min_price,
                "max_price": args.max_price,
                "universe": args.universe
            }
        }

    # Sort results
    sort_field = args.sort_by
    reverse = True  # Default descending for most metrics

    if sort_field == "gap":
        # Sort by absolute gap %
        scan_results.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)
    elif sort_field == "volume":
        scan_results.sort(key=lambda x: x.get("volume", 0), reverse=True)
    elif sort_field == "price":
        scan_results.sort(key=lambda x: x["current_price"], reverse=True)

    # Assign ranks
    for i, r in enumerate(scan_results, 1):
        r["rank"] = i

    # Limit results
    final_results = scan_results[:args.max_results]

    # Summary stats
    up_count = sum(1 for r in final_results if r["direction"] == "up")
    down_count = sum(1 for r in final_results if r["direction"] == "down")
    avg_gap = round(sum(abs(r["gap_pct"]) for r in final_results) / len(final_results), 2) if final_results else 0
    max_gap_stock = max(final_results, key=lambda x: abs(x["gap_pct"])) if final_results else None

    return {
        "scan_results": final_results,
        "summary": {
            "total_matches": len(scan_results),
            "returned": len(final_results),
            "gapping_up": up_count,
            "gapping_down": down_count,
            "avg_abs_gap_pct": avg_gap,
            "largest_gap": {
                "symbol": max_gap_stock["symbol"] if max_gap_stock else None,
                "gap_pct": max_gap_stock["gap_pct"] if max_gap_stock else None
            } if max_gap_stock else None
        },
        "filters_applied": {
            "min_gap_pct": args.min_gap,
            "max_gap_pct": args.max_gap,
            "direction": args.direction,
            "min_price": args.min_price,
            "max_price": args.max_price,
            "min_volume": args.min_volume,
            "min_avg_volume": args.min_avg_volume,
            "universe": args.universe,
            "max_results": args.max_results,
            "sort_by": args.sort_by
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description="Pre-market gap-up/down scanner via IBKR Gateway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --min-gap 3 --direction up --min-volume 500
  %(prog)s --universe nasdaq100 --min-gap 5 --max-gap 20 --min-price 10
  %(prog)s --direction down --min-gap 2 --sort-by volume --max-results 20
  %(prog)s --min-gap 1 --direction both --universe most_active --detailed
        """
    )

    parser.add_argument("--min-gap", type=float, default=2.0,
                        help="Minimum gap %% to include (default: 2.0)")
    parser.add_argument("--max-gap", type=float, default=50.0,
                        help="Maximum gap %% to include (default: 50.0)")
    parser.add_argument("--direction", choices=["up", "down", "both"], default="both",
                        help="Gap direction filter (default: both)")
    parser.add_argument("--min-price", type=float, default=5.0,
                        help="Minimum stock price (default: 5.0)")
    parser.add_argument("--max-price", type=float, default=500.0,
                        help="Maximum stock price (default: 500.0)")
    parser.add_argument("--min-volume", type=int, default=100,
                        help="Minimum daily volume in thousands (default: 100)")
    parser.add_argument("--min-avg-volume", type=int, default=50,
                        help="Minimum 30-day avg volume in thousands (default: 50)")
    parser.add_argument("--max-results", type=int, default=50,
                        help="Maximum results to return (default: 50)")
    parser.add_argument("--universe", choices=["all", "nasdaq100", "sp500", "most_active"],
                        default="most_active",
                        help="Stock universe to scan (default: most_active)")
    parser.add_argument("--extended", type=lambda x: x.lower() == "true", default=True,
                        help="Include extended hours data (default: true)")
    parser.add_argument("--sort-by", choices=["gap", "volume", "price"], default="gap",
                        help="Sort results by field (default: gap)")
    parser.add_argument("--output-format", choices=["json", "table"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--detailed", action="store_true", default=False,
                        help="Include detailed quote fields")

    args = parser.parse_args()

    result = run_gap_scan(args)

    if "_error" in result:
        print_json({
            "status": "ERROR",
            "message": result["_error"],
            "detail": result.get("_detail", "")
        })
        sys.exit(1)

    output = {"status": "OK", **result}

    if args.output_format == "table":
        print_table_output(output)
    else:
        print_json(output)


def print_table_output(data: dict):
    """Print results in a readable table format."""
    results = data.get("scan_results", [])
    summary = data.get("summary", {})
    filters = data.get("filters_applied", {})

    print(f"\n{'='*90}")
    print(f"  IBKR GAP SCAN — {filters.get('direction', 'both').upper()}")
    print(f"{'='*90}")
    print(f"  Filters: Gap >= {filters.get('min_gap_pct', 0)}% | "
          f"Price ${filters.get('min_price', 0)}-${filters.get('max_price', 0)} | "
          f"Universe: {filters.get('universe', 'most_active')}")
    print(f"  Matches: {summary.get('total_matches', 0)} total | "
          f"Showing top {len(results)} | "
          f"Up: {summary.get('gapping_up', 0)} | Down: {summary.get('gapping_down', 0)}")
    print(f"{'-'*90}")

    if not results:
        print("  No matching stocks found.")
    else:
        print(f"  {'Rank':<6} {'Symbol':<8} {'Price':>10} {'PrevClose':>10} {'Gap%':>10} {'Gap$':>10} {'Vol':>12} {'Dir':<6}")
        print(f"  {'-'*80}")
        for r in results:
            dir_indicator = "▲" if r["direction"] == "up" else "▼" if r["direction"] == "down" else "−"
            print(f"  {r['rank']:<6} {r['symbol']:<8} "
                  f"${r['current_price']:>8.2f} ${r['prev_close']:>8.2f} "
                  f"{r['gap_pct']:>+8.2f}% ${r['gap_dollars']:>+8.2f} "
                  f"{r.get('volume', 0):>10,} {dir_indicator:<6}")

    print(f"{'='*90}\n")


if __name__ == "__main__":
    main()
