# IBKR Trading Assistant — Kimi Code CLI Plugin

A Kimi Code CLI plugin for Interactive Brokers trading. It connects through the **IBKR Client Portal API Gateway** running locally on your machine and exposes quotes, positions, orders, scans, and analysis via a single `ibkr` launcher.

> **Not the socket API.** This plugin uses the [Client Portal API Gateway](https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/), not the IB Gateway/TWS socket API on ports 4001/7496/7497. A Dockerized Client Portal Gateway is included.

## What You Get

| Component | Description |
|-----------|-------------|
| `skills/ibkr-trading/SKILL.md` | Trading workflows, risk rules, and prompts Kimi reads before invoking tools |
| `bin/ibkr` | Launcher that delegates every command to the Python scripts |
| `ibkr-tools/scripts/` | Pure-Python scripts that call the Client Portal API Gateway |
| `.kimi-plugin/plugin.json` | Kimi Code CLI manifest |
| `cp-gateway/` | Docker setup for the Client Portal API Gateway |
| `docker-compose.yml` | One-command gateway launcher |

No MCP server, no Node.js dependencies, no third-party Python packages — just Python 3.8+ and the standard library.

## Directory Structure

```
ibkr-kimi-plugin/
├── README.md                          # This file
├── .kimi-plugin/
│   └── plugin.json                    # Kimi Code CLI manifest
├── bin/
│   └── ibkr                           # Launcher script for all commands
├── cp-gateway/
│   ├── Dockerfile                     # Client Portal API Gateway image
│   └── conf.yaml                      # Gateway config (mounted into container)
├── docker-compose.yml                 # Run the Client Portal API Gateway in Docker
├── skills/
│   └── ibkr-trading/
│       └── SKILL.md                   # Trading skill: workflows, risk rules, prompts
├── ibkr-tools/
│   └── scripts/
│       ├── ibkr_core.py               # Shared API client, SSL context, helpers
│       ├── ibkr_status.py             # Check gateway connection
│       ├── ibkr_quote.py              # Real-time quotes
│       ├── ibkr_search.py             # Contract lookup by symbol
│       ├── ibkr_positions.py          # Portfolio positions
│       ├── ibkr_account.py            # Account balances / buying power
│       ├── ibkr_orders.py             # List open orders
│       ├── ibkr_order.py              # Place orders
│       ├── ibkr_cancel_order.py       # Cancel orders
│       ├── ibkr_history.py            # Historical OHLCV+ bars
│       ├── ibkr_pnl.py                # Daily P&L summary
│       ├── ibkr_gap_scan.py           # Pre-market gap scanner
│       ├── ibkr_market_movers.py      # Gainers / losers / most active
│       ├── ibkr_analyze_technical.py  # RSI, SMA, EMA, ATR, MACD, Bollinger Bands
│       ├── ibkr_analyze_setup.py      # ORB setup grader (A+ through F)
│       ├── ibkr_analyze_finnhub.py    # News, earnings, sentiment enrichment
│       └── ibkr_briefing.py           # Pre-market briefing generator
└── docs/
    ├── ibkr-ai-analysis-proposal.md
    └── ibkr-kimi-integration-blueprint.md
```

## Prerequisites

- [ ] Interactive Brokers account (paper or live)
- [ ] Client Portal API Gateway running locally (use the included Docker Compose setup)
- [ ] Python 3.8+
- [ ] [Kimi Code CLI](https://www.kimi.com/code)
- [ ] Market data subscriptions active (for real-time quotes and scans)

## Installation

### 1. Install the plugin in Kimi Code CLI

Inside a Kimi Code CLI conversation, run:

```text
/plugins install /path/to/ibkr-kimi-plugin
/reload
```

Or install from a Git URL:

```text
/plugins install https://github.com/<owner>/ibkr-kimi-plugin.git
/reload
```

Kimi copies the plugin to:

```
~/.kimi-code/plugins/managed/ibkr-tools/
```

Start a new session (`/new`) if the skill does not load after `/reload`.

> **Important:** After editing the source repo, reinstall with `/plugins install /path/to/ibkr-kimi-plugin` again. Kimi always runs from the managed copy, not your working directory.

### 2. Add `ibkr` to your PATH (optional)

So you and agents can call `ibkr` directly:

```bash
# Add to ~/.bashrc, ~/.zshrc, or equivalent
export PATH="/path/to/ibkr-kimi-plugin/bin:$PATH"
```

Or symlink it:

```bash
mkdir -p ~/.local/bin
ln -s /path/to/ibkr-kimi-plugin/bin/ibkr ~/.local/bin/ibkr
```

## Client Portal API Gateway

This plugin talks to IBKR through the **Client Portal API Gateway**, a small Java application that proxies REST calls to IBKR. It runs on `https://localhost:5000` by default.

### Quick start with Docker Compose

Build and run the gateway:

```bash
docker compose up -d --build
```

The gateway listens on `https://localhost:5000`. To use a different host port, set `IBCP_GATEWAY_PORT` first:

```bash
export IBCP_GATEWAY_PORT=5001
docker compose up -d --build
```

Then authenticate:

1. Open `https://localhost:<IBCP_GATEWAY_PORT>` in a browser.
2. Accept the self-signed certificate warning.
3. Log in with your IBKR credentials and complete 2FA.

The API is usable only after this browser login step. The session may time out after inactivity; re-open the URL and log in again if commands start failing with `401`.

### Stop the gateway

```bash
docker compose down
```

### Verify it is running

```bash
curl -k https://localhost:5000/v1/api/sso/validate
```

Before login this returns `401`. After login it returns session JSON.

### Why the custom `conf.yaml`?

The default gateway config only allows connections from `127.0.0.1`, `192.*`, and `131.216.*`. When Docker maps the port, requests arrive from the Docker bridge network (`172.*` or `10.*`), so they are rejected with `404 Access Denied`. The included `cp-gateway/conf.yaml` adds `172.*` and `10.*` to the allow-list, which is why the gateway works through Docker.

## Configuration

Set these environment variables in your shell profile or before launching Kimi:

```bash
export IBCP_GATEWAY_HOST=localhost      # Client Portal API Gateway hostname
export IBCP_GATEWAY_PORT=5000           # Client Portal API Gateway port
export IBCP_PAPER_TRADING=true          # true = paper trading; set to live for live orders
export FINNHUB_API_KEY=                 # Optional: news / earnings / sentiment enrichment
```

> **macOS users:** Port 5000 is used by macOS AirPlay Receiver. If you get "address already in use", set `IBCP_GATEWAY_PORT=5001` (in both the export and the `docker compose up` step) and use that port everywhere.

### Port Reference

| Platform | Default Port | Used By This Plugin? |
|----------|-------------:|----------------------|
| **Client Portal API Gateway** | **5000** | **Yes — primary endpoint** |
| IB Gateway socket API (live) | 4001 | No |
| IB Gateway socket API (paper) | 4002 | No |
| TWS live | 7496 | No |
| TWS paper | 7497 | No |

## Quick Start

If `ibkr` is not on your PATH, use the full managed-plugin path:

```bash
~/.kimi-code/plugins/managed/ibkr-tools/bin/ibkr <command>
```

### 1. Verify the gateway

```bash
ibkr status
```

Expected output after login:

```json
{
  "status": "CONNECTED",
  "connected": true,
  "mode": "PAPER",
  "endpoint": "https://localhost:5000/v1/api",
  "accounts": ["DU1234567"],
  "account_count": 1
}
```

### 2. Test market data

```bash
ibkr quote AAPL
```

### 3. View positions

```bash
ibkr positions
```

### 4. Place a paper trade

```bash
ibkr order AAPL BUY 10 LMT 195.50
```

### 5. Run a pre-market gap scan

```bash
ibkr gap-scan --min-gap 3 --direction up --universe nasdaq100
```

### 6. Generate a pre-market briefing

```bash
ibkr briefing
```

## Available Commands

Run `ibkr help` at any time to see the command list.

| Command | Arguments | Purpose |
|---------|-----------|---------|
| `status` | None | Check gateway connection |
| `quote` | `<symbol>` | Bid, ask, last, volume, change |
| `search` | `<symbol>` | Contract ID (conid) and contract details |
| `positions` | None | All positions with P&L |
| `account` | None | Net liquidation, buying power, cash |
| `orders` | None | All open orders with status |
| `order` | `<symbol> <BUY/SELL> <qty> <MKT/LMT/STP> [price]` | Place an order (paper by default) |
| `cancel-order` | `<order_id>` | Cancel an open order |
| `history` | `<symbol> [options]` | Download historical OHLCV+ bars (CSV or JSON) |
| `pnl` | None | Daily realized + unrealized P&L |
| `gap-scan` | See parameter guide below | Pre-market gap-up/down scanner |
| `market-movers` | See parameter guide below | Gainers, losers, most active |
| `analyze-technical` | `<symbol> [--period 1m/3m/6m/1y] [--bar-size 1d/1h] [--detailed]` | Technical analysis with momentum score |
| `analyze-setup` | `<symbol> [--direction long/short] [--entry] [--stop] [--target]` | ORB setup evaluator with A-F grade |
| `analyze-finnhub` | `<symbol> [--news-count N] [--from-date YYYY-MM-DD]` | News, earnings, sentiment (needs `FINNHUB_API_KEY`) |
| `briefing` | `[--universe nasdaq100/most_active] [--gap-min N] [--max-setups N]` | Full pre-market briefing with setup ideas |

### Gap Scan Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--min-gap` | float | 2.0 | Minimum gap % to report |
| `--max-gap` | float | 50.0 | Maximum gap % to report |
| `--direction` | up/down/both | both | Gap direction filter |
| `--min-price` | float | 5.0 | Minimum stock price ($) |
| `--max-price` | float | 500.0 | Maximum stock price ($) |
| `--min-volume` | int | 100 | Min daily volume (thousands) |
| `--min-avg-volume` | int | 50 | Min 30-day avg volume (thousands) |
| `--universe` | nasdaq100/sp500/most_active/all | most_active | Stock universe |
| `--max-results` | int | 50 | Max stocks to return |
| `--sort-by` | gap/volume/price | gap | Sort field |
| `--detailed` | flag | false | Include full quote details |
| `--output-format` | json/table | json | Output format |

### Market Movers Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--type` | gainers/losers/most_active/all | all | Which movers to show |
| `--count` | int | 20 | Results per category |
| `--session` | pre_market/regular/after_hours | regular | Market session context |
| `--exchange` | nyse/nasdaq/all | all | Exchange filter |
| `--min-price` | float | 5.0 | Minimum stock price ($) |
| `--min-volume` | int | 50 | Min daily volume (thousands) |

## How It Works

```
Kimi Code CLI
  -> reads skill from skills/ibkr-trading/SKILL.md
  -> invokes ibkr <command> [args...]
  -> bin/ibkr selects the matching Python script in ibkr-tools/scripts/
  -> script calls https://localhost:5000/v1/api via ibkr_core.py
  -> Client Portal API Gateway relays to IBKR backend
  -> script returns structured JSON to Kimi
```

Key implementation points:

- **Skill-first design** — Kimi loads `skills/ibkr-trading/SKILL.md` before calling commands, so it understands workflows and risk rules.
- **Single launcher** — `bin/ibkr` resolves the repo root from its own location and works both in development and under `~/.kimi-code/plugins/managed/ibkr-tools/`.
- **No external dependencies** — pure Python standard library (`urllib`, `ssl`, `json`, `argparse`, `csv`).
- **Self-signed SSL** — `ibkr_core.py` disables certificate verification only for the local gateway self-signed certificate.
- **Structured output** — every command returns JSON with `"status": "OK"`, `"status": "ERROR"`, or `"status": "DEGRADED"`.

## Safety Features

1. **Paper Trading Default** — `IBCP_PAPER_TRADING=true` keeps orders in paper mode unless explicitly set to `live`.
2. **Preview Before Submit** — orders are previewed via the `whatif` endpoint to show margin impact before submission.
3. **No Credentials Stored** — uses your existing gateway session; no IBKR passwords or API keys in code.
4. **Localhost Only** — designed for a local gateway; credentials are never exposed externally.
5. **Order Confirmation** — every order response includes mode (`PAPER`/`LIVE`) and order details.
6. **Human Confirmation** — this plugin provides data, analysis, and order instructions; it does not auto-trade.

## Direct API Testing

Test the gateway API directly without the launcher:

```bash
# Check session (returns 401 until you log in via browser)
curl -k https://localhost:5000/v1/api/sso/validate

# Search AAPL
curl -k 'https://localhost:5000/v1/api/iserver/secdef/search?symbol=AAPL&secType=STK'

# Get quote (replace 76792991 with actual conid from search)
curl -k 'https://localhost:5000/v1/api/iserver/marketdata/snapshot?conids=76792991&fields=31,83,84'

# Get positions
curl -k https://localhost:5000/v1/api/portfolio/positions

# Get account summary
curl -k https://localhost:5000/v1/api/iserver/account/summary
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Connection failed" / "Connection refused" | Start the gateway with `docker compose up -d --build` and check `IBCP_GATEWAY_HOST` / `IBCP_GATEWAY_PORT` |
| "404 Access Denied" | Requests are coming from an IP not in `cp-gateway/conf.yaml` `ips.allow`. Rebuild the container so the updated `conf.yaml` is mounted. |
| "HTTP 401" / "HTTP 403" | Gateway session expired — re-authenticate at `https://localhost:<IBCP_GATEWAY_PORT>` |
| No market data | Subscribe to market data in IB Account Management |
| Empty positions | Normal if you hold no positions |
| Order rejected | Check buying power with `ibkr account` |
| `ibkr: command not found` | Add `/path/to/ibkr-kimi-plugin/bin` to your PATH, or use the full path `~/.kimi-code/plugins/managed/ibkr-tools/bin/ibkr` |
| Skill not loaded in Kimi | Run `/reload` or start a new conversation with `/new` |

## References

- [IBKR Client Portal API Reference](https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/)
- [Kimi Code CLI Plugin Docs](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/plugins.html)
- [Kimi Code CLI Skill Docs](https://moonshotai.github.io/kimi-cli/en/customization/skills.html)
