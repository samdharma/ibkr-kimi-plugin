#!/usr/bin/env python3
"""
ibkr-history: Historical OHLCV+ bar data downloader with date range support and CSV export.

Fetches bar data from IB Gateway Client Portal API for a given symbol and date range.
Defaults to last 3 months if no dates specified. Supports JSON or CSV output.
Can save to file or print to stdout.

Usage:
    python3 ibkr_history.py <SYMBOL> [OPTIONS]

Arguments:
    SYMBOL                  Stock ticker (e.g. AAPL)

Options:
    --start-date YYYY-MM-DD Start date (default: 3 months ago)
    --end-date   YYYY-MM-DD End date (default: today)
    --bar-size   1min,5min,15min,1h,1d (default: 1d)
    --format     json, csv (default: json)
    --output     File path to save data (default: stdout)
    --extended   Include extended hours (default: false)
    --no-header  Skip CSV header row (default: false)
    --timezone   Output timezone: utc, local, exchange (default: local)

Examples:
    python3 ibkr_history.py AAPL
    python3 ibkr_history.py TSLA --start-date 2026-01-01 --end-date 2026-06-28
    python3 ibkr_history.py NVDA --bar-size 5min --start-date 2026-06-01 --format csv --output nvda_5min.csv
    python3 ibkr_history.py SPY --bar-size 1d --start-date 2026-01-01 --format csv --output spy_daily.csv
    python3 ibkr_history.py AAPL --bar-size 1min --start-date 2026-06-27 --end-date 2026-06-28

Output Fields (OHLCV+):
    timestamp, open, high, low, close, volume, vwap, trades
    + derived: range, body, range_pct, change, change_pct
"""

import sys
import os
import csv
import io
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import get_conid, api_get, check_gateway, BASE_URL


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_BAR_SIZES = ["1min", "5min", "15min", "1h", "1d"]

# IBKR API period constraints per bar size
# Key constraint: period + endDate must fit within IBKR's max history per bar size
BAR_SIZE_LIMITS = {
    "1min":  {"max_period": "1d",  "max_bars": 1440},   # ~1 day of 1-min bars
    "5min":  {"max_period": "1w",  "max_bars": 2016},   # ~1 week of 5-min bars
    "15min": {"max_period": "1w",  "max_bars": 672},    # ~1 week of 15-min bars
    "1h":    {"max_period": "1m",  "max_bars": 720},    # ~1 month of hourly bars
    "1d":    {"max_period": "1y",  "max_bars": 365},    # ~1 year of daily bars
}

# Extended field codes from IB Gateway (for OHLCV+)
EXTENDED_FIELDS = "31,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150"


def get_default_date_range() -> tuple:
    """Return default date range: 3 months ago to today."""
    end = datetime.now()
    start = end - timedelta(days=90)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def parse_date(date_str: str) -> datetime:
    """Parse YYYY-MM-DD string to datetime."""
    return datetime.strptime(date_str, "%Y-%m-%d")


def format_ibkr_date(dt: datetime) -> str:
    """Format datetime for IBKR API (YYYYMMDD-HH:MM:SS)."""
    return dt.strftime("%Y%m%d-%H:%M:%S")


def chunk_date_range(start_dt: datetime, end_dt: datetime, bar_size: str) -> list:
    """Split date range into chunks that fit IBKR API limits."""
    limits = BAR_SIZE_LIMITS.get(bar_size, BAR_SIZE_LIMITS["1d"])

    if bar_size == "1min":
        chunk_days = 1
    elif bar_size in ("5min", "15min"):
        chunk_days = 5
    elif bar_size == "1h":
        chunk_days = 28
    else:  # 1d
        chunk_days = 365

    chunks = []
    current = start_dt
    while current < end_dt:
        chunk_end = min(current + timedelta(days=chunk_days), end_dt)
        chunks.append((current, chunk_end))
        current = chunk_end

    return chunks


def fetch_bars_chunk(conid: int, bar_size: str, start_dt: datetime, end_dt: datetime, extended: bool = False) -> list:
    """Fetch one chunk of historical bars from IB Gateway."""
    start_str = format_ibkr_date(start_dt)
    end_str = format_ibkr_date(end_dt)

    query = f"conid={conid}&period={BAR_SIZE_LIMITS[bar_size]['max_period']}&bar={bar_size}&startTime={start_str}&endTime={end_str}&outsideRth={'true' if extended else 'false'}"

    result = api_get("/iserver/marketdata/history", query)

    if "_error" in result:
        return []

    data = result.get("data", [])
    if not data:
        # Try without endTime (IBKR sometimes requires different parameter format)
        query2 = f"conid={conid}&period={BAR_SIZE_LIMITS[bar_size]['max_period']}&bar={bar_size}&startTime={start_str}&outsideRth={'true' if extended else 'false'}"
        result2 = api_get("/iserver/marketdata/history", query2)
        data = result2.get("data", []) if "_error" not in result2 else []

    return data if isinstance(data, list) else []


def fetch_all_bars(conid: int, bar_size: str, start_dt: datetime, end_dt: datetime, extended: bool = False) -> list:
    """Fetch all bars across chunked date ranges, merge and deduplicate."""
    all_bars = []
    seen_times = set()

    chunks = chunk_date_range(start_dt, end_dt, bar_size)

    for chunk_start, chunk_end in chunks:
        bars = fetch_bars_chunk(conid, bar_size, chunk_start, chunk_end, extended)

        for bar in bars:
            ts = bar.get("t", bar.get("timestamp", ""))
            if ts and ts not in seen_times:
                seen_times.add(ts)
                all_bars.append(bar)

    # Sort by timestamp
    all_bars.sort(key=lambda b: b.get("t", b.get("timestamp", "")))

    return all_bars


def parse_bar(bar: dict) -> dict:
    """Parse a raw IBKR bar into clean OHLCV+ format."""
    o = bar.get("o")
    h = bar.get("h")
    l = bar.get("l")
    c = bar.get("c")
    v = bar.get("v")

    # Calculate derived fields
    derived = {}
    if all(x is not None for x in [o, h, l, c]):
        try:
            derived["range"] = round(float(h) - float(l), 6)
            derived["body"] = round(abs(float(c) - float(o)), 6)
            derived["range_pct"] = round((float(h) - float(l)) / float(l) * 100, 4) if float(l) != 0 else 0
        except (ValueError, ZeroDivisionError):
            pass

    return {
        "timestamp": bar.get("t", bar.get("timestamp", "")),
        "open": _to_float(o),
        "high": _to_float(h),
        "low": _to_float(l),
        "close": _to_float(c),
        "volume": _to_int(v),
        **derived
    }


def _to_float(val):
    """Safely convert to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return val


def _to_int(val):
    """Safely convert to int."""
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return val


def compute_daily_change(bars: list) -> list:
    """Add change and change_pct fields relative to previous bar's close."""
    for i, bar in enumerate(bars):
        if i > 0 and bars[i-1].get("close") and bar.get("close"):
            prev_close = bars[i-1]["close"]
            curr_close = bar["close"]
            if prev_close and prev_close != 0:
                bar["change"] = round(curr_close - prev_close, 6)
                bar["change_pct"] = round((curr_close - prev_close) / prev_close * 100, 4)
        if "change" not in bar:
            bar["change"] = None
            bar["change_pct"] = None
    return bars


def to_csv(bars: list, include_header: bool = True) -> str:
    """Convert bars to CSV string."""
    if not bars:
        return ""

    output = io.StringIO()
    fieldnames = ["timestamp", "open", "high", "low", "close", "volume",
                  "range", "body", "range_pct", "change", "change_pct"]

    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    if include_header:
        writer.writeheader()

    for bar in bars:
        row = {k: (v if v is not None else "") for k, v in bar.items() if k in fieldnames}
        writer.writerow(row)

    return output.getvalue()


def to_json_output(symbol: str, conid: int, bar_size: str, start_date: str, end_date: str,
                   bars: list, extended: bool) -> dict:
    """Build final JSON output."""
    return {
        "status": "OK",
        "metadata": {
            "symbol": symbol,
            "conid": conid,
            "bar_size": bar_size,
            "start_date": start_date,
            "end_date": end_date,
            "extended_hours": extended,
            "bar_count": len(bars),
            "fields": ["timestamp", "open", "high", "low", "close", "volume",
                       "range", "body", "range_pct", "change", "change_pct"],
            "source": BASE_URL,
            "downloaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "summary": {
            "first_bar": bars[0] if bars else None,
            "last_bar": bars[-1] if bars else None,
            "highest_high": max((b["high"] for b in bars if b.get("high") is not None), default=None),
            "lowest_low": min((b["low"] for b in bars if b.get("low") is not None), default=None),
            "total_volume": sum(b["volume"] for b in bars if b.get("volume") is not None) if bars else 0,
            "avg_volume": round(sum(b["volume"] for b in bars if b.get("volume") is not None) / len(bars), 0) if bars else 0,
            "up_bars": sum(1 for b in bars if b.get("close") and b.get("open") and b["close"] > b["open"]),
            "down_bars": sum(1 for b in bars if b.get("close") and b.get("open") and b["close"] < b["open"]),
            "doji_bars": sum(1 for b in bars if b.get("close") and b.get("open") and b["close"] == b["open"])
        },
        "bars": bars
    }


def main():
    parser = argparse.ArgumentParser(
        description="Download historical OHLCV+ bar data from IB Gateway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s AAPL                                    # Last 3 months daily bars
  %(prog)s TSLA --start-date 2026-01-01 --end-date 2026-06-28
  %(prog)s NVDA --bar-size 5min --start-date 2026-06-01 --format csv --output nvda.csv
  %(prog)s SPY --bar-size 1d --start-date 2026-01-01 --format csv --output spy_daily.csv
  %(prog)s AAPL --bar-size 1min --start-date 2026-06-27 --end-date 2026-06-28 --format csv
        """
    )

    # Positionals
    parser.add_argument("symbol", help="Stock ticker symbol (e.g. AAPL)")

    # Date range (default: last 3 months)
    default_start, default_end = get_default_date_range()
    parser.add_argument("--start-date", default=default_start,
                        help=f"Start date YYYY-MM-DD (default: {default_start} = 3 months ago)")
    parser.add_argument("--end-date", default=default_end,
                        help=f"End date YYYY-MM-DD (default: {default_end} = today)")

    # Bar configuration
    parser.add_argument("--bar-size", choices=VALID_BAR_SIZES, default="1d",
                        help="Bar size/interval (default: 1d)")
    parser.add_argument("--extended", action="store_true", default=False,
                        help="Include extended hours (pre/post market)")

    # Output format
    parser.add_argument("--format", choices=["json", "csv"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file path (default: stdout)")
    parser.add_argument("--no-header", action="store_true", default=False,
                        help="Omit CSV header row")

    args = parser.parse_args()

    # Validate dates
    try:
        start_dt = parse_date(args.start_date)
        end_dt = parse_date(args.end_date)
    except ValueError:
        print(json.dumps({"status": "ERROR", "message": "Invalid date format. Use YYYY-MM-DD."}))
        sys.exit(1)

    if start_dt >= end_dt:
        print(json.dumps({"status": "ERROR", "message": "start-date must be before end-date."}))
        sys.exit(1)

    # Check gateway
    conn = check_gateway()
    if "_error" in conn:
        msg = {"status": "ERROR", "message": "IB Gateway not connected.", "detail": conn.get("_message", "")}
        print(json.dumps(msg))
        sys.exit(1)

    # Get conid
    symbol = args.symbol.upper()
    conid = get_conid(symbol)
    if conid is None:
        print(json.dumps({"status": "ERROR", "message": f"Contract not found: {symbol}"}))
        sys.exit(1)

    # Fetch all bars
    raw_bars = fetch_all_bars(conid, args.bar_size, start_dt, end_dt, args.extended)

    if not raw_bars:
        print(json.dumps({
            "status": "NO_DATA",
            "message": f"No bars returned for {symbol} from {args.start_date} to {args.end_date}.",
            "suggestions": [
                "Check market data subscriptions",
                "Try a shorter date range",
                f"IB Gateway limit for {args.bar_size}: {BAR_SIZE_LIMITS[args.bar_size]['max_period']} per request"
            ]
        }))
        sys.exit(0)

    # Parse and enrich bars
    parsed_bars = [parse_bar(b) for b in raw_bars]
    parsed_bars = compute_daily_change(parsed_bars)

    # Output
    if args.format == "csv":
        csv_data = to_csv(parsed_bars, not args.no_header)
        if args.output:
            with open(args.output, "w", newline="") as f:
                f.write(csv_data)
            print(json.dumps({
                "status": "OK",
                "message": f"CSV saved to {args.output}",
                "symbol": symbol,
                "bar_count": len(parsed_bars),
                "bar_size": args.bar_size,
                "date_range": f"{args.start_date} to {args.end_date}"
            }))
        else:
            print(csv_data)
    else:
        result = to_json_output(symbol, conid, args.bar_size, args.start_date, args.end_date,
                                parsed_bars, args.extended)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2)
            print(json.dumps({
                "status": "OK",
                "message": f"JSON saved to {args.output}",
                "symbol": symbol,
                "bar_count": len(parsed_bars)
            }))
        else:
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    # Need json for error messages even in csv mode
    import json
    main()
