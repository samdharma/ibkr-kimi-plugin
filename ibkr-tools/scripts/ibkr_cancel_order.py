#!/usr/bin/env python3
"""
ibkr-cancel-order: Cancel an open order by order ID.
Usage: python3 ibkr_cancel_order.py <ORDER_ID>
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import api_delete, print_json, check_gateway


def cancel_order(order_id: str) -> dict:
    """Cancel an order by ID."""
    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "_detail": conn.get("_message", "")}

    return api_delete(f"/iserver/account/order/{order_id}")


def main():
    if len(sys.argv) < 2:
        print_json({
            "status": "ERROR",
            "message": "Usage: ibkr-cancel-order <ORDER_ID>",
            "example": "ibkr-cancel-order 123456789",
            "hint": "Use ibkr-orders to list open orders and their IDs."
        })
        sys.exit(1)

    order_id = sys.argv[1]
    result = cancel_order(order_id)

    if "_error" in result:
        print_json({
            "status": "ERROR",
            "message": f"Failed to cancel order {order_id}",
            "detail": result.get("_message", "")
        })
        sys.exit(1)

    print_json({
        "status": "CANCELLED",
        "order_id": order_id,
        "response": result
    })


if __name__ == "__main__":
    main()
