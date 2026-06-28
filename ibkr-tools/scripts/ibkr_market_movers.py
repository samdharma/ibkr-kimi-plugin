#!/usr/bin/env python3
"""
ibkr-market-movers: Real-time market gainers, losers, and most active stocks.

Uses IBKR's market scanner to find top percentage gainers, top percentage losers,
and most actively traded stocks. Supports pre-market, regular hours, and after-hours.

Usage:
    python3 ibkr_market_movers.py [OPTIONS]

Parameters:
    --type           Mover type: gainers, losers, most_active, all (default: all)
    --count          Number of results per category (default: 20)
    --min-price      Minimum stock price (default: 5.0)
    --max-price      Maximum stock price (default: 1000.0)
    --min-volume     Minimum daily volume in thousands (default: 50)
    --session        Market session: pre_market, regular, after_hours, all_day (default: regular)
    --exchange       Exchange filter: nyse, nasdaq, all (default: all)
    --detailed       Include full quote details (default: false)
    --output-format  Output format: json, table (default: json)

Examples:
    python3 ibkr_market_movers.py --type gainers --count 10 --session pre_market
    python3 ibkr_market_movers.py --type all --min-volume 1000 --detailed
    python3 ibkr_market_movers.py --type losers --session after_hours --exchange nasdaq
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import (
    api_get, api_post, print_json, check_gateway,
    get_conid, fetch_batch_quotes, parse_quote_fields, BASE_URL
)


# ---------------------------------------------------------------------------
# IBKR Scanner Configuration
# ---------------------------------------------------------------------------

SCANNER_TYPES = {
    "gainers": {
        "code": "TOP_PERC_GAIN",
        "description": "Top percentage gainers",
        "sort_hint": "Top performers by % change"
    },
    "losers": {
        "code": "TOP_PERC_LOSE",
        "description": "Top percentage losers",
        "sort_hint": "Worst performers by % change"
    },
    "most_active": {
        "code": "MOST_ACTIVE",
        "description": "Most actively traded by volume",
        "sort_hint": "Highest volume today"
    },
    "hot_by_volume": {
        "code": "HOT_BY_VOLUME",
        "description": "Hot by volume relative to average",
        "sort_hint": "Volume spikes"
    },
    "hot_by_price": {
        "code": "HOT_BY_PRICE",
        "description": "Hot by price movement",
        "sort_hint": "Price momentum"
    }
}

# Exchange locations
EXCHANGE_LOCATIONS = {
    "nyse": "STK.NYSE",
    "nasdaq": "STK.NASDAQ",
    "all": "STK.US.MAJOR"
}

# Quote fields for detailed output
DETAILED_FIELDS = "31,83,84,85,86,7295,7633,7674,7675,7676"
BASIC_FIELDS = "31,85,86,7295,7676"


# ---------------------------------------------------------------------------
# Scanner Execution
# ---------------------------------------------------------------------------

def run_ibkr_scanner(scan_type: str, location: str, count: int,
                     min_price: float, max_price: float, min_volume: int) -> list:
    """Execute an IBKR market scanner."""

    scanner_config = SCANNER_TYPES.get(scan_type, SCANNER_TYPES["gainers"])

    # Build scanner request
    scan_body = {
        "instrument": "STK",
        "type": scanner_config["code"],
        "location": location,
        "size": min(count * 2, 500)
    }

    # Add filters
    filters = []
    if min_price > 0:
        filters.append({"code": "priceAbove", "value": min_price})
    if max_price > 0 and max_price < 100000:
        filters.append({"code": "priceBelow", "value": max_price})
    if min_volume > 0:
        filters.append({"code": "avgVolumeAbove", "value": min_volume})

    if filters:
        scan_body["filter"] = filters

    result = api_post("/iserver/scanner/run", scan_body)

    if "_error" in result:
        # Try GET fallback
        query_parts = [
            f"instrument={scan_body['instrument']}",
            f"type={scan_body['type']}",
            f"location={scan_body['location']}",
            f"size={scan_body['size']}"
        ]
        query = "&".join(query_parts)
        result = api_get("/iserver/scanner/run", query)

    # Parse response
    if isinstance(result, list):
        return result
    elif isinstance(result, dict):
        return result.get("result", result.get("contracts", result.get("data", [])))

    return []


def enrich_with_quotes(symbols_data: list, detailed: bool = False) -> list:
    """Enrich scanner results with real-time quote data."""
    if not symbols_data:
        return []

    # Build conid lookup
    conid_entries = []
    for item in symbols_data:
        if isinstance(item, dict):
            symbol = item.get("symbol", item.get("contractDesc", ""))
            conid = item.get("conid")
            if conid:
                conid_entries.append({"symbol": symbol, "conid": conid})

    # If no conids, try symbol lookup
    if not conid_entries:
        for item in symbols_data:
            if isinstance(item, dict):
                symbol = item.get("symbol", item.get("contractDesc", ""))
                if symbol:
                    conid = get_conid(symbol)
                    if conid:
                        conid_entries.append({"symbol": symbol, "conid": conid})

    if not conid_entries:
        return symbols_data  # Return raw if we can't enrich

    # Fetch quotes
    fields = DETAILED_FIELDS if detailed else BASIC_FIELDS
    quotes = {}

    conids = [str(e["conid"]) for e in conid_entries]
    batch_size = 25

    for i in range(0, len(conids), batch_size):
        batch = conids[i:i + batch_size]
        conid_str = ",".join(batch)

        result = api_get("/iserver/marketdata/snapshot", f"conids={conid_str}&fields={fields}")

        if isinstance(result, list):
            for entry in result:
                conid = str(entry.get("conid", ""))
                for e in conid_entries:
                    if str(e["conid"]) == conid:
                        quotes[e["symbol"].upper()] = parse_quote_fields(entry)
                        break

    # Merge data
    enriched = []
    for item in symbols_data:
        if isinstance(item, dict):
            symbol = item.get("symbol", item.get("contractDesc", "")).upper()
        else:
            symbol = str(item).upper()

        entry = {
            "symbol": symbol,
            "conid": item.get("conid") if isinstance(item, dict) else None,
            "exchange": item.get("listingExchange", "") if isinstance(item, dict) else "",
            "scanner_raw": item if isinstance(item, dict) else {}
        }

        if symbol in quotes:
            q = quotes[symbol]
            entry["current_price"] = q.get("last") or q.get("mid")
            entry["prev_close"] = q.get("prev_close")
            entry["change_pct"] = q.get("change_pct")
            entry["change"] = q.get("change")
            entry["volume"] = q.get("volume", 0)
            entry["bid"] = q.get("bid")
            entry["ask"] = q.get("ask")

            # Calculate gap if we have both current and prev close
            if entry.get("current_price") and entry.get("prev_close") and entry["prev_close"] > 0:
                gap = round(((entry["current_price"] - entry["prev_close"]) / entry["prev_close"]) * 100, 2)
                entry["gap_pct"] = gap

            if detailed:
                entry["high"] = q.get("high")
                entry["low"] = q.get("low")
                entry["open"] = q.get("open")
                entry["close"] = q.get("close")

        enriched.append(entry)

    return enriched


def run_movers_scan(args) -> dict:
    """Run the market movers scan."""
    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "detail": conn.get("_message", "")}

    location = EXCHANGE_LOCATIONS.get(args.exchange, EXCHANGE_LOCATIONS["all"])

    # Determine which scans to run
    if args.type == "all":
        scan_types = ["gainers", "losers", "most_active"]
    else:
        scan_types = [args.type]

    results = {}

    for scan_type in scan_types:
        scanner_info = SCANNER_TYPES.get(scan_type, SCANNER_TYPES["gainers"])

        raw_results = run_ibkr_scanner(
            scan_type=scan_type,
            location=location,
            count=args.count,
            min_price=args.min_price,
            max_price=args.max_price,
            min_volume=args.min_volume
        )

        # Enrich with quote data
        enriched = enrich_with_quotes(raw_results[:args.count * 2], args.detailed)

        # Sort by change % for gainers/losers
        if scan_type in ("gainers",):
            enriched.sort(key=lambda x: x.get("change_pct") or x.get("gap_pct", 0), reverse=True)
        elif scan_type in ("losers",):
            enriched.sort(key=lambda x: x.get("change_pct") or x.get("gap_pct", 0), reverse=False)
        elif scan_type == "most_active":
            enriched.sort(key=lambda x: x.get("volume", 0), reverse=True)

        # Limit results
        results[scan_type] = enriched[:args.count]

    return {
        "session": args.session,
        "exchange_filter": args.exchange,
        "scans_run": scan_types,
        "results": results
    }


def main():
    parser = argparse.ArgumentParser(
        description="Market gainers, losers, and most active stocks via IBKR Gateway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --type gainers --count 10 --session pre_market
  %(prog)s --type all --min-volume 1000 --detailed
  %(prog)s --type losers --session after_hours --exchange nasdaq
  %(prog)s --type most_active --count 5 --output-format table
        """
    )

    parser.add_argument("--type", choices=["gainers", "losers", "most_active", "all"],
                        default="all",
                        help="Type of movers to scan (default: all)")
    parser.add_argument("--count", type=int, default=20,
                        help="Number of results per category (default: 20)")
    parser.add_argument("--min-price", type=float, default=5.0,
                        help="Minimum stock price (default: 5.0)")
    parser.add_argument("--max-price", type=float, default=1000.0,
                        help="Maximum stock price (default: 1000.0)")
    parser.add_argument("--min-volume", type=int, default=50,
                        help="Minimum daily volume in thousands (default: 50)")
    parser.add_argument("--session", choices=["pre_market", "regular", "after_hours", "all_day"],
                        default="regular",
                        help="Market session context (default: regular)")
    parser.add_argument("--exchange", choices=["nyse", "nasdaq", "all"],
                        default="all",
                        help="Exchange filter (default: all)")
    parser.add_argument("--detailed", action="store_true", default=False,
                        help="Include full quote details")
    parser.add_argument("--output-format", choices=["json", "table"], default="json",
                        help="Output format (default: json)")

    args = parser.parse_args()

    result = run_movers_scan(args)

    if "_error" in result:
        print_json({
            "status": "ERROR",
            "message": result["_error"],
            "detail": result.get("detail", "")
        })
        sys.exit(1)

    output = {"status": "OK", **result}

    if args.output_format == "table":
        print_table_output(output)
    else:
        print_json(output)


def print_table_output(data: dict):
    """Print results in readable table format."""
    results = data.get("results", {})
    session = data.get("session", "regular")
    exchange = data.get("exchange_filter", "all")

    print(f"\n{'='*95}")
    print(f"  IBKR MARKET MOVERS — Session: {session.upper()} | Exchange: {exchange.upper()}")
    print(f"{'='*95}")

    for scan_type, stocks in results.items():
        type_label = scan_type.replace("_", " ").title()
        print(f"\n  [{'_'*30} {type_label} {'_'*30}]")

        if not stocks:
            print("  No results found.")
            continue

        print(f"  {'#':<4} {'Symbol':<8} {'Price':>10} {'Chg%':>10} {'Chg$':>10} {'Volume':>12} {'Gap%':>10}")
        print(f"  {'-'*70}")

        for i, stock in enumerate(stocks, 1):
            price = stock.get("current_price", 0) or 0
            change_pct = stock.get("change_pct", 0) or 0
            change = stock.get("change", 0) or 0
            volume = stock.get("volume", 0) or 0
            gap_pct = stock.get("gap_pct")

            gap_str = f"{gap_pct:+.2f}%" if gap_pct is not None else "N/A"

            indicator = "▲" if (change_pct or 0) > 0 else "▼" if (change_pct or 0) < 0 else "−"

            print(f"  {i:<4} {stock['symbol']:<8} ${price:>8.2f} "
                  f"{change_pct:>+8.2f}% ${change:>+8.2f} "
                  f"{volume:>10,} {gap_str:>10} {indicator}")

    print(f"\n{'='*95}\n")


if __name__ == "__main__":
    main()
