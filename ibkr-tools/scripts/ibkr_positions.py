#!/usr/bin/env python3
"""
ibkr-positions: List all current portfolio positions.
Usage: python3 ibkr_positions.py

Returns: symbol, quantity, average cost, market price, market value, unrealized P&L, P&L %
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import api_get, print_json, check_gateway


def get_positions() -> dict:
    """Fetch portfolio positions."""
    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "_detail": conn.get("_message", "")}

    result = api_get("/portfolio/positions")

    if "_error" in result:
        return result

    # Response can be a list of positions directly or wrapped
    positions = result if isinstance(result, list) else result.get("positions", [])

    clean_positions = []
    total_mkt_value = 0.0
    total_unrealized_pnl = 0.0
    total_realized_pnl = 0.0

    for pos in positions if isinstance(positions, list) else []:
        qty = pos.get("position", 0)
        avg_cost = pos.get("avgCost", 0) or pos.get("avgCostPrice", 0)
        mkt_price = pos.get("mktPrice", 0)
        mkt_value = pos.get("mktValue", 0)
        unrealized = pos.get("unrealizedPnl", 0)
        realized = pos.get("realizedPnl", 0)

        pnl_percent = 0.0
        if avg_cost and avg_cost > 0 and qty != 0:
            pnl_percent = round(((mkt_price - avg_cost) / avg_cost) * 100, 2)

        clean = {
            "symbol": pos.get("contractDesc", pos.get("symbol", "")),
            "conid": pos.get("conid"),
            "security_type": pos.get("assetType", pos.get("secType", "STK")),
            "quantity": qty,
            "avg_cost": round(avg_cost, 4) if avg_cost else 0,
            "market_price": round(mkt_price, 4) if mkt_price else 0,
            "market_value": round(mkt_value, 2) if mkt_value else 0,
            "unrealized_pnl": round(unrealized, 2) if unrealized else 0,
            "realized_pnl": round(realized, 2) if realized else 0,
            "pnl_percent": pnl_percent,
            "currency": pos.get("currency", "USD"),
            "exchange": pos.get("listingExchange", "")
        }
        clean_positions.append(clean)

        total_mkt_value += mkt_value or 0
        total_unrealized_pnl += unrealized or 0
        total_realized_pnl += realized or 0

    return {
        "positions": clean_positions,
        "position_count": len(clean_positions),
        "total_market_value": round(total_mkt_value, 2),
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        "total_realized_pnl": round(total_realized_pnl, 2),
        "combined_pnl": round(total_unrealized_pnl + total_realized_pnl, 2)
    }


def main():
    result = get_positions()

    if "_error" in result:
        print_json({
            "status": "ERROR",
            "message": result["_error"],
            "detail": result.get("_detail", "")
        })
        sys.exit(1)

    if result["position_count"] == 0:
        result["message"] = "No open positions found."

    print_json({"status": "OK", **result})


if __name__ == "__main__":
    main()
