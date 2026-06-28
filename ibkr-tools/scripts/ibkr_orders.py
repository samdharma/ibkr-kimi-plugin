#!/usr/bin/env python3
"""
ibkr-orders: List all open/live orders.
Usage: python3 ibkr_orders.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import api_get, print_json, check_gateway


def get_live_orders() -> dict:
    """Fetch all open orders."""
    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "_detail": conn.get("_message", "")}

    result = api_get("/iserver/account/orders")

    if "_error" in result:
        return result

    # Parse orders
    orders_raw = result if isinstance(result, list) else result.get("orders", [])

    clean_orders = []
    for order in orders_raw if isinstance(orders_raw, list) else []:
        clean = {
            "order_id": order.get("orderId", order.get("id", "")),
            "symbol": order.get("ticker", order.get("symbol", "")),
            "conid": order.get("conid"),
            "action": order.get("side", order.get("action", "")),
            "quantity": order.get("remainingQuantity", order.get("qty", 0)),
            "filled_quantity": order.get("filledQuantity", order.get("filled", 0)),
            "order_type": order.get("orderType", order.get("order_type", "")),
            "limit_price": order.get("price", order.get("lmtPrice", None)),
            "stop_price": order.get("stopPrice", None),
            "status": order.get("status", ""),
            "time_in_force": order.get("tif", order.get("timeInForce", "DAY")),
            "submitted_time": order.get("submitTime", order.get("order_time", "")),
            "account": order.get("account", "")
        }
        clean_orders.append(clean)

    return {
        "orders": clean_orders,
        "open_order_count": len(clean_orders)
    }


def main():
    result = get_live_orders()

    if "_error" in result:
        print_json({
            "status": "ERROR",
            "message": result["_error"],
            "detail": result.get("_detail", "")
        })
        sys.exit(1)

    if result["open_order_count"] == 0:
        result["message"] = "No open orders."

    print_json({"status": "OK", **result})


if __name__ == "__main__":
    main()
