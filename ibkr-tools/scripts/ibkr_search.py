#!/usr/bin/env python3
"""
ibkr-search: Search for a contract by symbol to get conid and details.
Usage: python3 ibkr_search.py <SYMBOL>
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import search_contract, print_json


def main():
    if len(sys.argv) < 2:
        print_json({
            "status": "ERROR",
            "message": "Usage: ibkr-search <SYMBOL>",
            "example": "ibkr-search AAPL"
        })
        sys.exit(1)

    symbol = sys.argv[1].upper()
    contracts = search_contract(symbol)

    if not contracts:
        print_json({
            "status": "NOT_FOUND",
            "message": f"No contracts found for symbol: {symbol}",
            "suggestion": "Try a different symbol or check market data subscriptions."
        })
        sys.exit(1)

    # Clean up contract info
    clean_contracts = []
    for c in contracts:
        clean = {
            "conid": c.get("conid"),
            "symbol": c.get("symbol"),
            "company_name": c.get("companyHeader", c.get("companyName", "")),
            "security_type": c.get("secType", "STK"),
            "exchange": c.get("exchange", ""),
            "currency": c.get("currency", "USD"),
            "description": c.get("description", "")
        }
        clean_contracts.append(clean)

    print_json({
        "status": "OK",
        "query": symbol,
        "results_count": len(clean_contracts),
        "contracts": clean_contracts
    })


if __name__ == "__main__":
    main()
