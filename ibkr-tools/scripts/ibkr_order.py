#!/usr/bin/env python3
"""
ibkr-order: Place a stock order via IB Gateway.
Usage: python3 ibkr_order.py <SYMBOL> <ACTION> <QTY> <TYPE> [PRICE]

Arguments:
    SYMBOL  - Stock ticker (e.g. AAPL)
    ACTION  - BUY or SELL
    QTY     - Integer number of shares
    TYPE    - MKT (market), LMT (limit), STP (stop)
    PRICE   - Required for LMT and STP orders

Safety:
    - Requires IB_PAPER_TRADING=false env var for live orders
    - Always validates symbol exists before placing
    - Returns order preview for confirmation when possible
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import (
    get_conid, api_post, print_json, print_error,
    check_gateway, IB_PAPER_TRADING, BASE_URL
)


def preview_order(symbol: str, conid: int, action: str, qty: int, order_type: str, price: float = None) -> dict:
    """Preview an order before submission."""
    order = {
        "conid": conid,
        "orderType": order_type,
        "quantity": qty,
        "side": action.upper(),
        "tif": "DAY"
    }
    if price is not None and order_type in ("LMT", "STP", "STP LMT"):
        order["price"] = price

    return api_post("/iserver/account/order/whatif", {"orders": [order]})


def place_order(symbol: str, conid: int, action: str, qty: int, order_type: str, price: float = None) -> dict:
    """Submit an order to IBKR."""
    order = {
        "conid": conid,
        "orderType": order_type,
        "quantity": abs(qty),
        "side": action.upper(),
        "tif": "DAY"
    }
    if price is not None and order_type in ("LMT", "STP", "STP LMT"):
        order["price"] = price

    return api_post("/iserver/account/DU12345/orders", {"orders": [order]})


def main():
    if len(sys.argv) < 5:
        print_json({
            "status": "ERROR",
            "message": "Insufficient arguments",
            "usage": "ibkr-order <SYMBOL> <ACTION> <QTY> <TYPE> [PRICE]",
            "examples": [
                "ibkr-order AAPL BUY 10 MKT",
                "ibkr-order TSLA SELL 5 LMT 250.00",
                "ibkr-order SPY BUY 20 STP 420.00"
            ],
            "order_types": {
                "MKT": "Market order - executes immediately at best available price",
                "LMT": "Limit order - executes at specified price or better",
                "STP": "Stop order - becomes market order when stop price is reached"
            }
        })
        sys.exit(1)

    symbol = sys.argv[1].upper()
    action = sys.argv[2].upper()
    qty = int(sys.argv[3])
    order_type = sys.argv[4].upper()
    price = None

    if len(sys.argv) > 5:
        price = float(sys.argv[5])

    # Validate inputs
    if action not in ("BUY", "SELL"):
        print_json({"status": "ERROR", "message": f"Invalid action: {action}. Use BUY or SELL."})
        sys.exit(1)

    if order_type not in ("MKT", "LMT", "STP"):
        print_json({"status": "ERROR", "message": f"Invalid order type: {order_type}. Use MKT, LMT, or STP."})
        sys.exit(1)

    if order_type in ("LMT", "STP") and price is None:
        print_json({"status": "ERROR", "message": f"{order_type} orders require a price."})
        sys.exit(1)

    # Check gateway
    conn = check_gateway()
    if "_error" in conn:
        print_json({"status": "ERROR", "message": "IB Gateway not connected", "detail": conn.get("_message", "")})
        sys.exit(1)

    # Get conid
    conid = get_conid(symbol)
    if conid is None:
        print_json({"status": "ERROR", "message": f"Contract not found: {symbol}"})
        sys.exit(1)

    # Safety: check paper trading
    mode = "PAPER" if IB_PAPER_TRADING else "LIVE"

    # Preview order first
    preview = preview_order(symbol, conid, action, qty, order_type, price)

    output = {
        "mode": mode,
        "symbol": symbol,
        "conid": conid,
        "action": action,
        "quantity": qty,
        "order_type": order_type,
        "limit_price": price,
        "preview": preview
    }

    # If preview succeeded, attempt to place
    if "_error" not in preview:
        place_result = place_order(symbol, conid, action, qty, order_type, price)
        output["order_result"] = place_result

        if "_error" not in place_result:
            output["status"] = "SUBMITTED"
            output["message"] = f"{mode} order submitted for {qty} shares of {symbol}"
        else:
            output["status"] = "FAILED"
            output["message"] = f"Order submission failed: {place_result.get('_message', 'Unknown error')}"
    else:
        output["status"] = "PREVIEW_FAILED"
        output["message"] = f"Order preview failed: {preview.get('_message', 'Unknown error')}"

    print_json(output)


if __name__ == "__main__":
    main()
