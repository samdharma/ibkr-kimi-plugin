#!/usr/bin/env python3
"""
ibkr-quote: Get real-time quote for a stock symbol.
Usage: python3 ibkr_quote.py <SYMBOL>

Returns: bid, ask, last price, volume, change, change percent, high, low, open, close
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import (
    get_conid, api_get, print_json, print_error,
    check_gateway, BASE_URL
)

# Market data field mapping (Client Portal API field codes)
# 31 = Last Price, 83 = Bid, 84 = Ask, 85 = Change, 86 = Change %
# 7295 = Volume, 7633 = High, 7674 = Low, 7675 = Open, 7676 = Close
QUOTE_FIELDS = "31,83,84,85,86,7295,7633,7674,7675,7676"
FIELD_NAMES = {
    "31": "last_price",
    "83": "bid",
    "84": "ask",
    "85": "change",
    "86": "change_percent",
    "7295": "volume",
    "7633": "high",
    "7674": "low",
    "7675": "open",
    "7676": "close"
}


def get_quote(symbol: str) -> dict:
    """Fetch real-time quote for a symbol."""
    # Check gateway first
    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "_detail": conn.get("_message", "")}

    # Get conid
    conid = get_conid(symbol.upper())
    if conid is None:
        return {"_error": f"Contract not found for symbol: {symbol}"}

    # Request market data snapshot
    result = api_get("/iserver/marketdata/snapshot", f"conids={conid}&fields={QUOTE_FIELDS}")

    if "_error" in result:
        return result

    # Parse the response (returns a list of dicts)
    if isinstance(result, list) and len(result) > 0:
        data = result[0]
    elif isinstance(result, dict):
        data = result
    else:
        return {"_error": "Unexpected response format", "_raw": result}

    # Map field codes to human-readable names
    quote = {
        "symbol": symbol.upper(),
        "conid": conid,
        "timestamp": None  # Will be populated if available
    }

    for field_code, field_name in FIELD_NAMES.items():
        if field_code in data:
            raw = data[field_code]
            # Try to convert to number
            try:
                if "." in str(raw):
                    quote[field_name] = float(raw)
                else:
                    quote[field_name] = int(raw)
            except (ValueError, TypeError):
                quote[field_name] = raw

    # Add spread if both bid and ask available
    if "bid" in quote and "ask" in quote:
        try:
            quote["spread"] = round(quote["ask"] - quote["bid"], 4)
            if quote["bid"] > 0:
                quote["spread_percent"] = round((quote["spread"] / quote["bid"]) * 100, 4)
        except (TypeError, ZeroDivisionError):
            pass

    # Add midpoint
    if "bid" in quote and "ask" in quote:
        try:
            quote["midpoint"] = round((quote["bid"] + quote["ask"]) / 2, 4)
        except TypeError:
            pass

    return quote


def main():
    if len(sys.argv) < 2:
        print_json({
            "status": "ERROR",
            "message": "Usage: ibkr-quote <SYMBOL>",
            "example": "ibkr-quote AAPL"
        })
        sys.exit(1)

    symbol = sys.argv[1]
    result = get_quote(symbol)

    if "_error" in result:
        print_json({
            "status": "ERROR",
            "message": result["_error"],
            "detail": result.get("_detail", ""),
            "symbol": symbol.upper()
        })
        sys.exit(1)

    print_json({"status": "OK", "quote": result})


if __name__ == "__main__":
    main()
