#!/usr/bin/env python3
"""
ibkr-account: Get account summary including balances, buying power, and available funds.
Usage: python3 ibkr_account.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import api_get, print_json, check_gateway


def get_account_summary() -> dict:
    """Fetch account summary."""
    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "_detail": conn.get("_message", "")}

    result = api_get("/iserver/account/summary")

    if "_error" in result:
        # Try alternative endpoint
        result = api_get("/portfolio/accounts")
        if "_error" in result:
            return result

    # Parse account summary fields
    summary = {}

    if isinstance(result, dict):
        # Extract key fields if available in various formats
        summary["net_liquidation"] = result.get("netliquidation", result.get("NetLiquidation"))
        summary["buying_power"] = result.get("buyingpower", result.get("BuyingPower"))
        summary["available_funds"] = result.get("availablefunds", result.get("AvailableFunds"))
        summary["cash_balance"] = result.get("totalcashvalue", result.get("TotalCashValue"))
        summary["equity_with_loan"] = result.get("equitywithloanvalue", result.get("EquityWithLoanValue"))
        summary["gross_position_value"] = result.get("grosspositionvalue", result.get("GrossPositionValue"))
        summary["maintenance_margin"] = result.get("maintenancemarginreq", result.get("MaintenanceMarginReq"))
        summary["day_trades_remaining"] = result.get("daytradesremaining", result.get("DayTradesRemaining"))
        summary["currency"] = result.get("currency", "USD")
        summary["account_type"] = result.get("type", "")
        summary["account_id"] = result.get("accountId", result.get("id", ""))
        summary["raw"] = result  # Include full response for debugging

    elif isinstance(result, list) and len(result) > 0:
        # Sometimes returned as list of account summaries
        acct = result[0]
        summary["net_liquidation"] = acct.get("netliquidation", acct.get("NetLiquidation"))
        summary["buying_power"] = acct.get("buyingpower", acct.get("BuyingPower"))
        summary["available_funds"] = acct.get("availablefunds", acct.get("AvailableFunds"))
        summary["cash_balance"] = acct.get("totalcashvalue", acct.get("TotalCashValue"))
        summary["account_id"] = acct.get("accountId", acct.get("id", ""))
        summary["raw"] = acct

    return summary


def main():
    result = get_account_summary()

    if "_error" in result:
        print_json({
            "status": "ERROR",
            "message": result["_error"],
            "detail": result.get("_detail", "")
        })
        sys.exit(1)

    # Convert numeric strings to numbers for key fields
    for key in ["net_liquidation", "buying_power", "available_funds", "cash_balance",
                "equity_with_loan", "gross_position_value", "maintenance_margin"]:
        if key in result and result[key] is not None:
            try:
                result[key] = float(result[key])
            except (ValueError, TypeError):
                pass

    print_json({"status": "OK", "account": result})


if __name__ == "__main__":
    main()
