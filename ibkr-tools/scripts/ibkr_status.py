#!/usr/bin/env python3
"""
ibkr-status: Check IB Gateway connection and session status.
Usage: python3 ibkr_status.py
"""
import sys
import os

# Allow importing ibkr_core from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import check_gateway, get_accounts, print_json, BASE_URL, IB_PAPER_TRADING


def main():
    result = check_gateway()

    if "_error" in result:
        print_json({
            "status": "DISCONNECTED",
            "connected": False,
            "message": "Cannot connect to IB Gateway. Is it running?",
            "detail": result.get("_message", "Unknown error"),
            "endpoint": BASE_URL,
            "hint": "Start IB Gateway, enable API connections (Settings > API > Enable), and ensure port matches."
        })
        sys.exit(1)

    # Get accounts if connected
    accounts = get_accounts()
    mode = "PAPER" if IB_PAPER_TRADING else "LIVE"

    output = {
        "status": "CONNECTED",
        "connected": True,
        "mode": mode,
        "endpoint": BASE_URL,
        "sso_validation": result,
        "accounts": accounts,
        "account_count": len(accounts),
        "next_steps": [
            "Test quotes: ibkr-quote symbol=AAPL",
            "View positions: ibkr-positions",
            "Check account: ibkr-account"
        ]
    }

    if not accounts:
        output["warning"] = "No accounts found. Log in to IB Gateway and ensure API is enabled."

    print_json(output)


if __name__ == "__main__":
    main()
