# IBKR Trading Assistant — Cross-Agent Skill Plugin

A skills-first Interactive Brokers plugin for [Kimi Code CLI](https://www.kimi.com/code) and [Claude Code](https://claude.ai/code). It connects through your locally running IB Gateway and exposes trading, market-data, and analysis workflows via a single `ibkr` launcher.

## What You Get

| Component | Description |
|-----------|-------------|
| **`skills/ibkr-trading/SKILL.md`** | Trading workflows, risk rules, and prompts that agents read before invoking tools |
| **`bin/ibkr`** | One launcher that delegates every command to the Python scripts |
| **`ibkr-tools/scripts/`** | Pure-Python scripts that call the IB Gateway Client Portal API |
| **`.kimi-plugin/plugin.json`** | Kimi Code CLI manifest |
| **`.claude-plugin/`** | Claude Code manifest, marketplace metadata, and `CLAUDE.md` |

No MCP server, no Node.js dependencies, no third-party Python packages — just Python 3.8+ and the standard library.

## Directory Structure

```
ibkr-kimi-plugin/
├── README.md                          # This file
├── CLAUDE.md                          # Claude Code entrypoint / usage summary
├── .kimi-plugin/
│   └── plugin.json                    # Kimi Code CLI manifest (skills + sessionStart)
├── .claude-plugin/
│   ├── plugin.json                    # Claude Code manifest
│   └── marketplace.json               # Claude marketplace metadata
├── bin/
│   └── ibkr                           # Launcher script for all commands
├── skills/
│   └── ibkr-trading/
│       └── SKILL.md                   # Trading skill: workflows, risk rules, prompts
├── ibkr-tools/
│   └── scripts/
│       ├── ibkr_core.py               # Shared API client, SSL context, helpers
│       ├── ibkr_status.py             # Check Gateway connection
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
- [ ] IB Gateway installed, running, and authenticated locally
- [ ] Python 3.8+
- [ ] [Kimi Code CLI](https://www.kimi.com/code) or [Claude Code](https://claude.ai/code)
- [ ] Market data subscriptions active (for real-time quotes and scans)

## Installation

### Kimi Code CLI

Inside a Kimi Code CLI conversation, run:

```
/plugins install https://github.com/<owner>/ibkr-kimi-plugin.git
/reload
```

Kimi installs this as a managed plugin under:

```
~/.kimi-code/plugins/managed/ibkr-tools/
```

Start a new session (`/new`) if the skill does not load after `/reload`.

### Claude Code

For local development:

```bash
claude --skill-dir /path/to/ibkr-kimi-plugin
```

For marketplace distribution, reference `.claude-plugin/marketplace.json` and the manifest in `.claude-plugin/plugin.json`.

### Optional: Add `ibkr` to your PATH

So agents and your shell can call `ibkr` directly:

```bash
# Add to ~/.bashrc, ~/.zshrc, or equivalent
export PATH="/path/to/ibkr-kimi-plugin/bin:$PATH"
```

Or symlink it into `~/.local/bin`:

```bash
mkdir -p ~/.local/bin
ln -s /path/to/ibkr-kimi-plugin/bin/ibkr ~/.local/bin/ibkr
```

## Configuration

Set these environment variables in your shell profile or before launching Kimi / Claude:

```bash
export IBCP_GATEWAY_HOST=localhost      # Client Portal API Gateway hostname
export IBCP_GATEWAY_PORT=5000           # Client Portal API Gateway port
export IBCP_PAPER_TRADING=paper         # paper = paper trading only; set to live for live
export FINNHUB_API_KEY=                 # Optional: news / earnings / sentiment enrichment
```

> **macOS users:** Port 5000 is used by macOS AirPlay Receiver. If you get "address already in use", set `IBCP_GATEWAY_PORT=5001` and use that port when starting the gateway.

### Client Portal API Gateway Settings

1. Start the Client Portal API Gateway (see Installation below).
2. Open `https://localhost:<IBCP_GATEWAY_PORT>` in your browser and log in with your IBKR credentials.
3. Complete 2FA when prompted.

### Port Reference

| Platform | Default Port | Use Case |
|----------|-------------|----------|
| Client Portal API Gateway (this plugin) | 5000 | **Primary endpoint used by `ibkr`** |
| IB Gateway Socket API | 4001 / 4004 | Alternative socket API (not used here) |
| TWS Live | 7496 | TWS GUI |
| TWS Paper | 7497 | TWS GUI |

## Quick Start

If `ibkr` is not on your PATH, use the full managed-plugin path:

```bash
~/.kimi-code/plugins/managed/ibkr-tools/bin/ibkr <command>
```

### 1. Verify the Gateway

```bash
ibkr status
```

Expected output:

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

### 2. Test Market Data

```bash
ibkr quote AAPL
```

### 3. View Positions

```bash
ibkr positions
```

### 4. Place a Paper Trade

```bash
ibkr order AAPL BUY 10 LMT 195.50
```

### 5. Run a Pre-Market Gap Scan

```bash
ibkr gap-scan --min-gap 3 --direction up --universe nasdaq100
```

### 6. Generate a Pre-Market Briefing

```bash
ibkr briefing
```

## Available Commands

Run `ibkr help` at any time to see the command list.

| Command | Arguments | Purpose |
|---------|-----------|---------|
| `status` | None | Check IB Gateway connection |
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
Kimi / Claude
  -> reads skill from skills/ibkr-trading/SKILL.md
  -> invokes ibkr <command> [args...]
  -> bin/ibkr selects the matching Python script in ibkr-tools/scripts/
  -> script calls https://localhost:5000/v1/api via ibkr_core.py
  -> IB Gateway relays to IBKR backend
  -> script returns structured JSON to the agent
```

Key implementation points:

- **Skill-first design** — agents load `skills/ibkr-trading/SKILL.md` before calling commands, so they understand workflows and risk rules.
- **Single launcher** — `bin/ibkr` resolves the repo root from its own location and works both in development and under `~/.kimi-code/plugins/managed/ibkr-tools/`.
- **No external dependencies** — pure Python standard library (`urllib`, `ssl`, `json`, `argparse`, `csv`).
- **Self-signed SSL** — `ibkr_core.py` disables certificate verification only for the local IB Gateway self-signed certificate.
- **Structured output** — every command returns JSON with `"status": "OK"`, `"status": "ERROR"`, or `"status": "DEGRADED"`.

## Safety Features

1. **Paper Trading Default** — `IBCP_PAPER_TRADING=paper` is required unless explicitly set to `live` for live orders.
2. **Preview Before Submit** — orders are previewed via the `whatif` endpoint to show margin impact before submission.
3. **No Credentials Stored** — uses your existing IB Gateway session; no IBKR passwords or API keys in code.
4. **Localhost Only** — designed for a local IB Gateway; credentials are never exposed externally.
5. **Order Confirmation** — every order response includes mode (`PAPER`/`LIVE`) and order details.
6. **Human Confirmation** — this plugin provides data, analysis, and order instructions; it does not auto-trade.

## Direct API Testing

Test the IB Gateway API directly without the launcher:

```bash
# Check session
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
| "Connection failed" | Start the Client Portal API Gateway and check `IBCP_GATEWAY_HOST` / `IBCP_GATEWAY_PORT` |
| "HTTP 401" / "HTTP 403" | IB Gateway session expired — re-authenticate in the Gateway UI |
| No market data | Subscribe to market data in IB Account Management |
| Empty positions | Normal if you hold no positions |
| Order rejected | Check buying power with `ibkr account` |
| `ibkr: command not found` | Add `/path/to/ibkr-kimi-plugin/bin` to your PATH, or use the full path `~/.kimi-code/plugins/managed/ibkr-tools/bin/ibkr` |
| Skill not loaded in Kimi | Run `/reload` or start a new conversation with `/new` |

## References

- [IBKR Client Portal API Reference](https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/)
- [Kimi Code CLI Plugin Docs](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/plugins.html)
- [Kimi Code CLI Skill Docs](https://moonshotai.github.io/kimi-cli/en/customization/skills.html)
