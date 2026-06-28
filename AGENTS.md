# Agent Guide: ibkr-kimi-plugin

This file is written for AI coding agents who need to understand and work on the `ibkr-kimi-plugin` project. The project uses English for all comments, documentation, and code.

## Project overview

`ibkr-kimi-plugin` is a local Interactive Brokers (IBKR) integration for [Kimi Code CLI](https://moonshotai.github.io/kimi-cli/). It exposes 16 trading tools as a Kimi plugin (`ibkr-tools`) and a companion skill (`ibkr-trading`) that provides trading workflows and risk rules.

The plugin talks directly to the IBKR Client Portal API on a locally-running IB Gateway via HTTPS REST calls. No MCP server, no Node.js runtime, and no third-party Python packages are required.

What the project does:
- Checks IB Gateway connection (`ibkr-status`).
- Fetches quotes, positions, account balances, open orders, and P&L.
- Places and cancels stock orders with paper-trading safeguards.
- Downloads historical OHLCV+ bars to CSV or JSON.
- Runs pre-market gap scans and market-movers scans.
- Performs pure-Python technical analysis (RSI, SMA/EMA, ATR, Bollinger Bands, MACD, support/resistance, momentum score).
- Grades ORB trade setups A+ through F.
- Enriches analysis with Finnhub news, earnings, sentiment, and analyst data (optional, requires `FINNHUB_API_KEY`).
- Generates a structured pre-market briefing.

## Technology stack

- **Language:** Python 3.8+.
- **Standard library only** (`urllib`, `ssl`, `json`, `argparse`, `csv`, `datetime`, `sys`, `os`, `io`, `typing`). No `requirements.txt`, `pyproject.toml`, `package.json`, or `Cargo.toml` exists.
- **Integration format:** Kimi Code CLI plugin manifest (`ibkr-tools/kimi.plugin.json`) plus a Kimi skill (`ibkr-trading/SKILL.md`).
- **External runtime dependency:** A locally installed and running IB Gateway (or TWS) exposing the Client Portal API on `https://localhost:4004/v1/api`.
- **Optional external API:** Finnhub REST API for news/earnings enrichment (`FINNHUB_API_KEY`).

## Project structure

```
ibkr-kimi-plugin/
├── README.md                          # User-facing docs, quick-start, tool reference
├── AGENTS.md                          # This file
├── .gitignore                         # Currently empty
├── docs/
│   ├── ibkr-ai-analysis-proposal.md   # Architecture proposal for AI analysis layer
│   └── ibkr-kimi-integration-blueprint.md  # Broader MCP/blueprint research doc
├── ibkr-tools/
│   ├── kimi.plugin.json               # Kimi plugin manifest (v1.2.0)
│   └── scripts/
│       ├── ibkr_core.py               # Shared HTTP client + utilities (imported by other scripts)
│       ├── ibkr_status.py             # Connection check
│       ├── ibkr_quote.py              # Real-time quotes
│       ├── ibkr_search.py             # Contract lookup by symbol
│       ├── ibkr_positions.py          # Portfolio positions
│       ├── ibkr_account.py            # Account balances / buying power
│       ├── ibkr_orders.py             # Open orders list
│       ├── ibkr_order.py              # Place orders
│       ├── ibkr_cancel_order.py       # Cancel an order
│       ├── ibkr_history.py            # Historical OHLCV+ bar downloader
│       ├── ibkr_pnl.py                # Daily P&L summary
│       ├── ibkr_gap_scan.py           # Pre-market gap scanner
│       ├── ibkr_market_movers.py      # Gainers/losers/most-active
│       ├── ibkr_analyze_technical.py  # Technical indicators + momentum score
│       ├── ibkr_analyze_setup.py      # ORB setup grader
│       ├── ibkr_analyze_finnhub.py    # News/earnings/sentiment enrichment
│       └── ibkr_briefing.py           # Pre-market briefing generator
└── ibkr-trading/
    └── SKILL.md                       # Trading workflows, risk rules, prompts for Kimi
```

## Architecture and runtime flow

```
Kimi Code CLI
  -> reads ibkr-tools/kimi.plugin.json
  -> invokes `python3 <script>.py [args]`
  -> script uses ibkr_core.py to call https://localhost:4004/v1/api
  -> IB Gateway relays to IBKR backend
  -> script returns structured JSON to Kimi
```

Key implementation points:
- Each tool is a standalone executable Python script.
- `ibkr_core.py` centralizes base URL construction, SSL context (IB Gateway uses a self-signed cert, so verification is disabled for localhost), GET/POST/DELETE helpers, account discovery, contract search, and JSON output helpers.
- `ibkr_analyze_technical.py` and `ibkr_analyze_setup.py` depend on helper functions in `ibkr_history.py` for historical bar fetching.
- `ibkr_briefing.py` imports from `ibkr_gap_scan.py`, `ibkr_analyze_setup.py`, and `ibkr_analyze_technical.py`.
- Output contract: every script prints JSON. Use `"status": "OK"` for success, `"status": "ERROR"` for failures, and `"status": "DEGRADED"` / `"status": "PARTIAL"` for optional-data failures (Finnhub).

## Configuration and environment variables

All configuration is environment-driven. There are no credential files checked into the repo.

| Variable | Default | Purpose |
|----------|---------|---------|
| `IB_GATEWAY_HOST` | `localhost` | IB Gateway hostname |
| `IB_GATEWAY_PORT` | `4004` | Client Portal API port |
| `IB_PAPER_TRADING` | `true` | If `true`, tools report/operate in paper mode. Must be explicitly set to `false` for live. |
| `FINNHUB_API_KEY` | none | Optional Finnhub API key for news/earnings/analyst enrichment |

IB Gateway must be configured with API enabled and a matching port. The default port used by this plugin is `4004` (Client Portal API), not the TWS socket ports `7496`/`7497` or the Gateway socket port `4001`.

## Build and test commands

There is no build system and no automated test suite in this repository.

Useful commands for agents:

```bash
# Syntax-check all Python scripts
python3 -m py_compile ibkr-tools/scripts/*.py

# Install or reinstall the plugin locally
kimi plugin install ./ibkr-tools

# Verify the plugin is registered
kimi plugin list

# Test a tool directly (requires IB Gateway running)
python3 ibkr-tools/scripts/ibkr_status.py
python3 ibkr-tools/scripts/ibkr_quote.py AAPL
```

To exercise the full plugin from Kimi CLI:

```
ibkr-status
ibkr-quote symbol=AAPL
ibkr-positions
ibkr-account
ibkr-gap-scan --min-gap 3 --direction up --universe nasdaq100
ibkr-analyze-technical AAPL --period 3m
```

## Code style guidelines

- Python 3.8+ syntax; type hints are welcome but not required.
- Keep scripts dependency-free; only use the Python standard library.
- Prefer `argparse` for command-line arguments.
- Always use `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` at the top of a script so it can import `ibkr_core.py` from the same directory when invoked by absolute path.
- Use the helpers in `ibkr_core.py` for HTTP calls (`api_get`, `api_post`, `api_delete`), gateway checks (`check_gateway`), and output (`print_json`, `print_error`, `print_success`).
- Check gateway connectivity before making API calls and return structured error JSON on failure.
- Never hardcode account IDs, credentials, or secrets. Use environment variables.
- When adding a new tool, mirror the existing pattern: create `scripts/ibkr_<name>.py`, add a tool entry to `ibkr-tools/kimi.plugin.json`, and reinstall the plugin.

## Testing instructions

- There are no unit tests. Validation is manual/integration-style against a running IB Gateway.
- Paper trading is the default; use it for all tests (`IB_PAPER_TRADING=true`).
- To test order tools safely, use a paper IBKR account and verify with `ibkr-orders` after placement.
- For Finnhub-dependent tools, set `FINNHUB_API_KEY` and verify both populated and degraded (`_degraded`) outputs.
- For local smoke tests without Kimi, invoke the scripts directly with `python3`.

## Deployment / installation

The plugin is installed into Kimi Code CLI from the local directory:

```bash
kimi plugin install ./ibkr-tools
```

Or from a Git URL:

```bash
kimi plugin install https://github.com/<user>/ibkr-kimi-plugin.git
```

The skill is referenced from the manifest via `"skills": "../ibkr-trading"` and `"sessionStart": {"skill": "ibkr-trading"}`. After changing tool definitions or adding/removing scripts, reinstall the plugin.

There is no CI/CD pipeline, container image, or production deployment script. This is a local developer/user plugin.

## Security considerations

- **Credentials:** No API keys or passwords are stored in code. IBKR authentication is handled by the local IB Gateway session. Finnhub is the only optional API key and must be supplied via the `FINNHUB_API_KEY` environment variable.
- **Network:** Designed for localhost only. `ibkr_core.py` disables SSL certificate verification only for the local IB Gateway self-signed certificate.
- **Trading mode:** `IB_PAPER_TRADING` defaults to `true`. Live trading requires explicitly setting it to `false`.
- **Order safety:** `ibkr_order.py` previews the order via the `whatif` endpoint before submission and reports whether the mode is `PAPER` or `LIVE` in the response.
- **Secrets in git:** `.gitignore` is currently empty; do not add config files, session files, or credential exports to the repository.
- **Do not auto-trade:** The plugin provides data, analysis, and order instructions. Human confirmation is required before any order reaches the market.

## Common issues for agents to know

- `"Connection failed"` or `HTTP` errors usually mean IB Gateway is not running, the API is not enabled, or the port/env var is wrong. First step is always `ibkr-status`.
- `HTTP 401` / `403` means the Gateway session expired; re-authenticate in the Gateway UI.
- No market data usually means missing market-data subscriptions in IB Account Management.
- `ibkr_order.py` currently hardcodes the account placeholder `DU12345` in the submission endpoint. In practice the account ID from `get_accounts()` should be used; verify and fix if the order endpoint fails.
- `ibkr_analyze_finnhub.py` returns `DEGRADED` status when `FINNHUB_API_KEY` is absent; downstream callers and Kimi prompts should handle that gracefully.

## How to extend the plugin

1. Create `ibkr-tools/scripts/ibkr_<tool>.py` following the import and error-handling patterns of existing scripts.
2. Add a tool definition to `ibkr-tools/kimi.plugin.json` with the correct `name`, `description`, `command`, and JSON-schema `parameters`.
3. Reinstall the plugin with `kimi plugin install ./ibkr-tools`.
4. Update `README.md` and `ibkr-trading/SKILL.md` if the new tool changes user workflows or risk rules.

## Documentation references

- `README.md` — user quick-start and tool parameter tables.
- `ibkr-trading/SKILL.md` — Kimi workflow prompts, risk rules, and best practices.
- `docs/ibkr-ai-analysis-proposal.md` — design rationale for the technical/setup/briefing analysis scripts.
- `docs/ibkr-kimi-integration-blueprint.md` — broader research on MCP-based IBKR integrations.
- External: [IBKR Client Portal API Reference](https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/), [Kimi Plugin Docs](https://moonshotai.github.io/kimi-cli/en/customization/plugins.html).
