#!/usr/bin/env python3
"""
IBKR Client Portal API Core Module
Shared utilities for connecting to IB Gateway via Client Portal API.

Prerequisites:
    - IB Gateway running locally with API enabled
    - Market data subscriptions active on your IBKR account
    - Python 3.8+

IB Gateway API endpoint: https://localhost:4004/v1/api
Default ports: TWS Paper=7497, TWS Live=7496, Gateway=4001-4004
"""

import json
import os
import ssl
import sys
import urllib.request
import urllib.error
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

IB_GATEWAY_HOST = os.getenv("IB_GATEWAY_HOST", "localhost")
IB_GATEWAY_PORT = int(os.getenv("IB_GATEWAY_PORT", "4004"))
IB_PAPER_TRADING = os.getenv("IB_PAPER_TRADING", "true").lower() == "true"

BASE_URL = f"https://{IB_GATEWAY_HOST}:{IB_GATEWAY_PORT}/v1/api"

# ---------------------------------------------------------------------------
# SSL Context — IB Gateway uses self-signed cert on localhost
# ---------------------------------------------------------------------------

def _get_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ---------------------------------------------------------------------------
# HTTP Helpers
# ---------------------------------------------------------------------------

def api_get(endpoint: str, query: str = "") -> dict:
    """Make a GET request to the Client Portal API."""
    url = f"{BASE_URL}{endpoint}"
    if query:
        url = f"{url}?{query}"

    ctx = _get_ssl_context()
    req = urllib.request.Request(
        url,
        headers={"Host": "api.ibkr.com"},
        method="GET"
    )

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            raw = resp.read()
            if not raw:
                return {"_raw": "", "_status": resp.status}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"_raw": raw.decode("utf-8", errors="replace"), "_status": resp.status}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"_error": f"HTTP {e.code}", "_message": body, "_url": url}
    except urllib.error.URLError as e:
        return {"_error": "Connection failed", "_message": str(e.reason), "_url": url}
    except Exception as e:
        return {"_error": "Request failed", "_message": str(e), "_url": url}


def api_post(endpoint: str, data: dict) -> dict:
    """Make a POST request to the Client Portal API."""
    url = f"{BASE_URL}{endpoint}"
    payload = json.dumps(data).encode("utf-8")

    ctx = _get_ssl_context()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Host": "api.ibkr.com",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            raw = resp.read()
            if not raw:
                return {"_raw": "", "_status": resp.status}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"_raw": raw.decode("utf-8", errors="replace"), "_status": resp.status}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"_error": f"HTTP {e.code}", "_message": body, "_url": url}
    except urllib.error.URLError as e:
        return {"_error": "Connection failed", "_message": str(e.reason), "_url": url}
    except Exception as e:
        return {"_error": "Request failed", "_message": str(e), "_url": url}


def api_delete(endpoint: str) -> dict:
    """Make a DELETE request to the Client Portal API."""
    url = f"{BASE_URL}{endpoint}"

    ctx = _get_ssl_context()
    req = urllib.request.Request(
        url,
        headers={"Host": "api.ibkr.com"},
        method="DELETE"
    )

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            raw = resp.read()
            if not raw:
                return {"_raw": "", "_status": resp.status}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"_raw": raw.decode("utf-8", errors="replace"), "_status": resp.status}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"_error": f"HTTP {e.code}", "_message": body, "_url": url}
    except urllib.error.URLError as e:
        return {"_error": "Connection failed", "_message": str(e.reason), "_url": url}
    except Exception as e:
        return {"_error": "Request failed", "_message": str(e), "_url": url}


# ---------------------------------------------------------------------------
# Common Utilities
# ---------------------------------------------------------------------------

def check_gateway() -> dict:
    """Check if IB Gateway is running and session is valid."""
    return api_get("/sso/validate")


def get_accounts() -> list:
    """Get list of accounts. Returns list of account objects."""
    result = api_get("/iserver/accounts")
    if isinstance(result, dict) and "accounts" in result:
        return result["accounts"]
    return result if isinstance(result, list) else []


def get_selected_account() -> str:
    """Get the currently selected account ID."""
    accounts = get_accounts()
    if accounts:
        return accounts[0]  # First account is selected by default
    return ""


def search_contract(symbol: str, sec_type: str = "STK") -> list:
    """Search for a contract by symbol. Returns list of contract dicts."""
    result = api_get("/iserver/secdef/search", f"symbol={symbol}&secType={sec_type}")
    if isinstance(result, list):
        return result
    return []


def get_conid(symbol: str, sec_type: str = "STK") -> Optional[int]:
    """Get the contract ID (conid) for a symbol. Returns None if not found."""
    contracts = search_contract(symbol, sec_type)
    if contracts:
        return contracts[0].get("conid")
    return None


# ---------------------------------------------------------------------------
# Output Formatting
# ---------------------------------------------------------------------------

def print_json(data: Any) -> None:
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=2, default=str))


def print_error(message: str, detail: str = "") -> None:
    """Print a structured error."""
    error = {"status": "ERROR", "message": message}
    if detail:
        error["detail"] = detail
    print_json(error)


def print_success(data: Any, message: str = "") -> None:
    """Print a successful response."""
    output = {"status": "OK"}
    if message:
        output["message"] = message
    if isinstance(data, dict):
        output.update(data)
    else:
        output["data"] = data
    print_json(output)
