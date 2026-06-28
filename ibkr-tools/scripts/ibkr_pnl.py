#!/usr/bin/env python3
"""
ibkr-pnl: Get daily P&L summary including realized and unrealized P&L.
Usage: python3 ibkr_pnl.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import api_get, print_json, check_gateway


def get_pnl() -> dict:
    """Fetch P&L summary."""
    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "_detail": conn.get("_message", "")}

    # Try the P&L endpoint
    result = api_get("/iserver/account/pnl/partitioned")

    if "_error" in result:
        # Fallback to account MMA (market value aggregation)
        result = api_get("/iserver/account/mma")

    if "_error" in result:
        return result

    # Parse P&L data
    pnl = {}

    if isinstance(result, dict):
        pnl["dpl"] = result.get("dpl")  # Daily P&L
        pnl["upl"] = result.get("upl")  # Unrealized P&L
        pnl["rpl"] = result.get("rpl")  # Realized P&L
        pnl["nl"] = result.get("nl")    # Net liquidation
        pnl["total"] = result.get("total")

        # Try to get from nested structures
        if "partition" in result:
            for part in result["partition"] if isinstance(result["partition"], list) else []:
                if isinstance(part, dict):
                    pnl["by_asset_class"] = pnl.get("by_asset_class", [])
                    pnl["by_asset_class"].append({
                        "asset_class": part.get("assetClass", ""),
                        "unrealized_pnl": part.get("upl", 0),
                        "realized_pnl": part.get("rpl", 0),
                        "market_value": part.get("mv", 0)
                    })

        pnl["raw"] = result

    return pnl


def main():
    result = get_pnl()

    if "_error" in result:
        print_json({
            "status": "ERROR",
            "message": result["_error"],
            "detail": result.get("_detail", "")
        })
        sys.exit(1)

    # Clean numeric fields
    for key in ["dpl", "upl", "rpl", "nl", "total"]:
        if key in result and result[key] is not None:
            try:
                result[key] = float(result[key])
            except (ValueError, TypeError):
                pass

    print_json({"status": "OK", "pnl": result})


if __name__ == "__main__":
    main()
