---
name: ibkr-trading
description: Interactive Brokers trading workflows via the local Client Portal API Gateway. Use for quotes, positions, orders, scans, technical analysis, and risk-controlled trading.
---

# IBKR Client Portal API Gateway Trading

This skill controls Interactive Brokers (IBKR) trading workflows through the `ibkr` launcher. The launcher delegates to Python scripts that talk directly to a locally-running Client Portal API Gateway on `https://localhost:5000/v1/api` (override with `IBCP_GATEWAY_HOST`/`IBCP_GATEWAY_PORT`). This is the REST-based Client Portal API, not the IB Gateway/TWS socket API.

## Architecture

```mermaid
flowchart LR
    A[Kimi Code CLI] -->|ibkr launcher| B[ibkr-tools scripts]
    B -->|Python + HTTPS| C[CP Gateway localhost:5000]
    C -->|HTTPS REST| D[IBKR Servers]

    style A fill:#4CAF50,color:#fff
    style B fill:#2196F3,color:#fff
    style C fill:#FF9800,color:#000
```

## Launcher Invocation Rules

When the user asks for anything involving quotes, orders, positions, scans, or analysis, invoke the launcher commands.

1. **First try:** `ibkr <command> [args...]`
2. **If `ibkr` is not on PATH:** use the full path `~/.kimi-code/plugins/managed/ibkr-tools/bin/ibkr <command> [args...]`
3. **If that path does not exist:** ask the user where the launcher is installed.

Available launcher commands:

| Command | Delegated script |
|---------|------------------|
| `status` | `ibkr_status.py` |
| `quote` | `ibkr_quote.py` |
| `search` | `ibkr_search.py` |
| `positions` | `ibkr_positions.py` |
| `account` | `ibkr_account.py` |
| `orders` | `ibkr_orders.py` |
| `order` | `ibkr_order.py` |
| `cancel-order` | `ibkr_cancel_order.py` |
| `history` | `ibkr_history.py` |
| `pnl` | `ibkr_pnl.py` |
| `gap-scan` | `ibkr_gap_scan.py` |
| `market-movers` | `ibkr_market_movers.py` |
| `analyze-technical` | `ibkr_analyze_technical.py` |
| `analyze-setup` | `ibkr_analyze_setup.py` |
| `analyze-finnhub` | `ibkr_analyze_finnhub.py` |
| `briefing` | `ibkr_briefing.py` |

## Pre-Flight Rule

Before any trading operation, run `ibkr status` and confirm the gateway is connected. If `ibkr status` reports disconnected or errors, stop and tell the user to start IB Gateway and log in.

Confirm the following when relevant:

1. IB Gateway is running and logged in
2. API connections are enabled (Settings > API > Enable)
3. Port matches configuration (default: 5000, set via `IBCP_GATEWAY_PORT` env var; use the same port in `docker compose up` if not 5000)
4. Session is authenticated
5. Market data subscriptions are active

## Command Reference

| Command | Purpose | Example invocation |
|---------|---------|-------------------|
| `ibkr status` | Check Gateway connection | `ibkr status` |
| `ibkr quote` | Real-time quote | `ibkr quote AAPL` |
| `ibkr search` | Contract lookup | `ibkr search ES` |
| `ibkr positions` | Portfolio positions | `ibkr positions` |
| `ibkr account` | Account balances / buying power | `ibkr account` |
| `ibkr orders` | Open orders | `ibkr orders` |
| `ibkr order` | Place an order | `ibkr order AAPL BUY 10 LMT 195.50` |
| `ibkr cancel-order` | Cancel an order | `ibkr cancel-order 123456` |
| `ibkr history` | Historical OHLCV+ data download | `ibkr history AAPL --start-date 2026-01-01 --format csv --output aapl.csv` |
| `ibkr pnl` | P&L summary | `ibkr pnl` |
| `ibkr gap-scan` | Pre-market gap scanner | `ibkr gap-scan --min-gap 3 --direction up --universe nasdaq100` |
| `ibkr market-movers` | Gainers/losers/most active | `ibkr market-movers --type gainers --count 10 --session pre_market` |
| `ibkr analyze-technical` | Technical analysis (RSI, SMA, ATR, MACD, BB) | `ibkr analyze-technical AAPL --period 3m` |
| `ibkr analyze-setup` | ORB setup evaluator (grades A-F) | `ibkr analyze-setup NVDA --direction long` |
| `ibkr analyze-finnhub` | News, earnings, sentiment, analysts | `ibkr analyze-finnhub TSLA` |
| `ibkr briefing` | Full pre-market briefing | `ibkr briefing --universe nasdaq100 --gap-min 3` |

## Workflow Patterns

### Market Data Request

```mermaid
sequenceDiagram
    participant K as Kimi
    participant Q as ibkr quote
    participant G as IB Gateway

    K->>Q: ibkr quote TSLA
    Q->>G: GET /iserver/secdef/search?symbol=TSLA
    G-->>Q: conid: 76792991
    Q->>G: GET /iserver/marketdata/snapshot?conids=76792991
    G-->>Q: {31: 242.50, 83: 242.45, 84: 242.65}
    Q-->>K: TSLA: Bid 242.45 / Ask 242.65 / Last 242.50
```

### Order Placement (Paper Trading)

```mermaid
sequenceDiagram
    participant U as User
    participant K as Kimi
    participant O as ibkr order
    participant G as IB Gateway

    U->>K: "Buy 10 shares of AAPL at limit $195"
    K->>O: ibkr order AAPL BUY 10 LMT 195.00
    O->>G: POST /iserver/account/order/whatif
    G-->>O: Preview: margin impact, commission
    O->>G: POST /iserver/account/{acct}/orders
    G-->>O: {order_id: 123456, status: submitted}
    O-->>K: Order submitted: ID 123456
    K-->>U: "Submitted PAPER order: Buy 10 AAPL @ 195 LMT"
```

### Position and Risk Check

```mermaid
flowchart TD
    A[Start] --> B[ibkr positions]
    B --> C{Position > 10% of NAV?}
    C -->|Yes| D[Flag Risk Warning]
    C -->|No| E[Acceptable]
    E --> F[ibkr account]
    F --> G{Buying Power > Order Value?}
    G -->|Yes| H[Proceed with Order]
    G -->|No| I[Reject - Insufficient Funds]
    D --> J[Require Confirmation]

    style D fill:#F44336,color:#fff
    style I fill:#F44336,color:#fff
    style H fill:#4CAF50,color:#fff
```

### Pre-Market Gap Scan Workflow

```mermaid
sequenceDiagram
    participant U as User
    participant K as Kimi
    participant S as ibkr gap-scan
    participant G as IB Gateway

    U->>K: "Scan for pre-market gappers > 3%"
    K->>S: ibkr gap-scan --min-gap 3 --direction both
    S->>G: POST /iserver/scanner/run (MOST_ACTIVE)
    G-->>S: Top active stocks
    S->>S: Resolve conids for each symbol
    S->>G: GET /iserver/marketdata/snapshot (batch)
    G-->>S: {last, prev_close, volume}
    S->>S: Calculate gap % per stock
    S->>S: Filter by min-gap, price, volume
    S->>S: Sort by absolute gap %
    S-->>K: Top 50 gappers with gap%, direction, price
    K-->>U: "Found 12 stocks gapping > 3%. Top: XYZ +8.2%, ABC -5.1%..."
```

### Gap Scan Parameter Guide

| Parameter | Typical Values | When to Use |
|-----------|---------------|-------------|
| `--min-gap` | 2.0, 3.0, 5.0, 10.0 | Higher = fewer but stronger signals |
| `--max-gap` | 20.0, 30.0, 50.0 | Cap to avoid low-float parabolics |
| `--direction` | up, down, both | Momentum plays = up; mean reversion = down |
| `--min-price` | 1.0, 5.0, 10.0 | Avoid sub-$5 penny stocks |
| `--max-price` | 100, 200, 500 | Focus on affordable position sizes |
| `--min-volume` | 100, 500, 1000 | Ensure liquidity (in thousands) |
| `--universe` | nasdaq100, most_active | NQ100 for quality; most_active for breadth |
| `--max-results` | 10, 20, 50 | Manageable watchlist size |
| `--sort-by` | gap, volume, price | Gap = momentum; Volume = confirmation |

### ORB Strategy Gap Scan Presets

| Strategy | Command |
|----------|---------|
| **Conservative gap-up** | `ibkr gap-scan --min-gap 2 --max-gap 10 --direction up --min-price 10 --min-volume 500 --universe nasdaq100 --max-results 20` |
| **Aggressive gap-up** | `ibkr gap-scan --min-gap 5 --direction up --min-price 5 --min-volume 100 --universe most_active --max-results 50` |
| **Gap-down reversal** | `ibkr gap-scan --min-gap 3 --direction down --min-price 15 --min-volume 300 --sort-by volume` |
| **Pre-market momentum** | `ibkr gap-scan --min-gap 4 --direction both --min-price 10 --min-volume 1000 --universe most_active --detailed` |

### Market Movers Workflow

```mermaid
flowchart TD
    A[Start Session] --> B{Market Open?}
    B -->|Pre-market| C[ibkr market-movers --session pre_market]
    B -->|Regular| D[ibkr market-movers --session regular]
    B -->|After-hours| E[ibkr market-movers --session after_hours]

    C --> F[Review Gainers + Losers]
    D --> F
    E --> F

    F --> G{ORB Setup?}
    G -->|Yes| H[Cross-reference with gap-scan]
    G -->|No| I[Monitor for intraday breaks]

    H --> J[Confirm volume + gap confluence]
    J --> K[Set alerts / prepare orders]

    style C fill:#FF9800,color:#000
    style D fill:#4CAF50,color:#fff
    style E fill:#9C27B0,color:#fff
```

### Market Movers Presets

| Scenario | Command |
|----------|---------|
| **Pre-market leaders** | `ibkr market-movers --type gainers --count 15 --session pre_market --min-volume 100` |
| **Regular hours top gainers** | `ibkr market-movers --type gainers --count 20 --exchange nasdaq` |
| **Short squeeze scan** | `ibkr market-movers --type gainers --count 10 --min-volume 500 --detailed` |
| **End-of-day washouts** | `ibkr market-movers --type losers --count 10 --session after_hours` |
| **Full market picture** | `ibkr market-movers --type all --count 10 --detailed` |

## AI Analysis Workflows

### Technical Analysis Workflow

```mermaid
sequenceDiagram
    participant U as User
    participant K as Kimi
    participant T as ibkr analyze-technical
    participant G as IB Gateway

    U->>K: "Technical picture of AAPL"
    K->>T: ibkr analyze-technical AAPL --period 3m
    T->>G: Fetch 3 months daily bars
    G-->>T: OHLCV data
    T->>T: Calculate RSI(14), SMA(20/50/200), ATR(14)
    T->>T: Calculate Bollinger Bands, MACD
    T->>T: Find support/resistance levels
    T->>T: Compute momentum score (0-100)
    T-->>K: Full technical report
    K-->>U: "AAPL: Momentum score 72/100. Above all SMAs, RSI 58 neutral, MACD bullish. Support at $238, resistance at $248. Bullish trend with strength 0.65."
```

**When Kimi receives the technical report, it should interpret:**
- Momentum score > 70 = bullish, < 30 = bearish, 30-70 = neutral
- RSI > 70 = overbought caution, < 30 = oversold opportunity
- Price above SMA20 + SMA50 = trend aligned for longs
- MACD histogram positive = momentum supporting longs
- ATR% > 5% = volatile stock, wider stops needed

### Setup Evaluation Workflow

```mermaid
sequenceDiagram
    participant U as User
    participant K as Kimi
    participant S as ibkr analyze-setup
    participant G as IB Gateway

    U->>K: "Should I take NVDA ORB long?"
    K->>S: ibkr analyze-setup NVDA
    S->>G: Current quote + historical bars
    G-->>S: Price, gap%, volume, history
    S->>S: Score gap quality (0-100)
    S->>S: Score volume confirmation (0-100)
    S->>S: Score technical alignment (0-100)
    S->>S: Calculate risk/reward from ATR
    S->>S: Composite score -> grade (A+ to F)
    S->>S: Recommendation: TAKE/WATCH/PASS/CAUTION
    S-->>K: Graded setup with levels
    K-->>U: "NVDA ORB: Grade B+. 3.2% gap, 2.1x volume. R:R 2.6:1. Entry 142.80, stop 140.80, target 147.00. Recommendation: WATCH — wait for 5-min break above trigger."
```

**Grade interpretation:**
| Grade | Score | Action |
|-------|-------|--------|
| A+ / A / A- | 82-100 | TAKE — strong edge, favorable conditions |
| B+ / B / B- | 62-81 | WATCH — decent, needs confirmation |
| C+ / C / C- | 42-61 | CAUTION — marginal, paper trade only |
| D / F | 0-41 | PASS — avoid |

### Research Workflow ("Why is it moving?")

```mermaid
flowchart TD
    A[User asks: "Why is TSLA moving?"] --> B[ibkr analyze-technical]
    A --> C[ibkr analyze-finnhub]
    A --> D[Kimi web search]

    B -->|Price action context| E[Kimi Synthesis]
    C -->|News + earnings + sentiment| E
    D -->|Web articles + SEC filings| E

    E --> F[Concise answer with confidence level]

    style D fill:#9C27B0,color:#fff
    style E fill:#4CAF50,color:#fff
```

**How Kimi should use the data:**
1. Run `ibkr analyze-technical` — get gap%, volume, trend context
2. Run `ibkr analyze-finnhub` — get news headlines with sentiment, earnings proximity
3. Use Kimi's built-in web search for broader context
4. Synthesize: "TSLA gapping +3.5% on delivery beat (Reuters positive). RSI 54, not overbought. Above all SMAs. Next earnings in 24 days. Bullish catalyst with technical alignment."

### Pre-Market Briefing Workflow

```mermaid
flowchart LR
    A[ibkr briefing] --> B[Gap Distribution]
    A --> C[Top Gappers]
    A --> D[Top Gainers/Losers]
    A --> E[Setup Ideas with Grades]
    A --> F[Key Takeaways]

    B --> G[Kimi Morning Brief]
    C --> G
    D --> G
    E --> G
    F --> G

    G --> H[Actionable Trading Plan]

    style A fill:#2196F3,color:#fff
    style G fill:#4CAF50,color:#fff
```

**The briefing output includes:**
- How many stocks gapping up vs down (market bias)
- Top 10 gappers with gap% and direction
- Top 10 gainers and losers
- Up to 5 setup ideas with entry/stop/target/grade
- Key takeaways (automated insights)

### Finnhub Integration Guide

To enable news, earnings, and analyst data:

```bash
# 1. Get free API key at https://finnhub.io/register
# 2. Export in your shell profile:
export FINNHUB_API_KEY=your_key_here
```

**Without Finnhub:** Technical analysis and setup grading work fully. News/earnings columns will show "not available."

**With Finnhub:** Full enrichment — sentiment scoring on headlines, earnings proximity warnings, analyst consensus, price targets.

### Historical Data Export for Backtesting

```mermaid
sequenceDiagram
    participant U as User
    participant H as ibkr history
    participant G as IB Gateway
    participant F as CSV File

    U->>H: ibkr history AAPL --start-date 2024-01-01 --end-date 2026-06-28 --bar-size 1d --format csv --output aapl_30m.csv
    H->>G: Request bars in chunks
    G-->>H: OHLCV+ data (auto-chunked for large ranges)
    H->>H: Compute range, body, change, change_pct
    H->>F: Write CSV with header
    H-->>U: {"status": "OK", "bar_count": 1250, "file": "aapl_30m.csv"}
```

**CSV columns:** `timestamp, open, high, low, close, volume, range, body, range_pct, change, change_pct`

**For backtest tools:** The CSV is pandas-compatible. Read with `pd.read_csv("aapl_30m.csv")` — no parsing needed.

**Default behavior:** If no dates specified, downloads last 3 months of daily bars.

## Risk Management Rules

### Hard Limits (Never Override Without Explicit User Confirmation)

- **Max Position Size**: No single position > 10% of net liquidation value
- **Max Sector Exposure**: No sector > 30% of portfolio
- **Cash Reserve**: Maintain minimum 20% cash or short-term equivalents
- **Order Validation**: Always preview order before submission to check margin impact

### Order Type Guidelines

| Scenario | Recommended Type | Reason |
|----------|-----------------|--------|
| Quick entry/exit on momentum | MKT | Speed matters |
| Specific price entry | LMT | Control fill price |
| Breakout entry | STP | Auto-trigger on move |
| Profit target | LMT GTC | Set and forget |
| Loss protection | STP | Automated stop |

## Paper Trading Requirement

All new strategies and launcher commands MUST be validated in paper trading mode first:

```bash
export IBCP_PAPER_TRADING=true
```

`ibkr order` enforces preview-before-submit and displays PAPER/LIVE mode in every response. Live trading requires explicitly setting `IBCP_PAPER_TRADING=live` and confirming with the user.

## Client Portal API Gateway Configuration

### Required Settings

1. **Enable API**: Edit > Settings > API > Enable "ActiveX and Socket Clients"
2. **Port**: The Client Portal API Gateway endpoint used by the scripts is `https://localhost:5000/v1/api` by default (override with `IBCP_GATEWAY_PORT`).
3. **Localhost Only**: Ensure "Allow connections from localhost only" is checked
4. **Master API Client ID**: Leave as 0 unless using multiple clients

### Session Persistence

- IB Gateway auto-logs out after ~6 minutes of inactivity
- Keep Gateway window active or use auto-restart scripts
- The launcher commands will return clear DISCONNECTED status if the session expired

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `IBCP_GATEWAY_HOST` | `localhost` | Client Portal API Gateway hostname |
| `IBCP_GATEWAY_PORT` | `5000` | Client Portal API Gateway port (also set when running `docker compose up`) |
| `IBCP_PAPER_TRADING` | `true` | `true` for paper trading, `live` for live |
| `FINNHUB_API_KEY` | none | Optional: news / earnings / sentiment enrichment |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Connection failed" | Gateway not running | Start IB Gateway, log in |
| "HTTP 401/403" | Session expired | Re-authenticate in Gateway |
| "No market data" | Missing subscription | Check Market Data Subscriptions in Account Management |
| "Contract not found" | Wrong symbol | Use `ibkr search` to verify |
| "Order rejected" | Insufficient buying power | Check `ibkr account` for available funds |
| "Preview failed" | Invalid parameters | Check conid, order type, price format |
| Empty positions list | No holdings | Normal if portfolio is flat |

## Best Practices

1. **Always check status first**: Run `ibkr status` at session start
2. **Quote before ordering**: Get current market price with `ibkr quote` before placing orders
3. **Verify fills**: After placing an order, check `ibkr orders` to confirm status
4. **Monitor P&L**: Run `ibkr pnl` at end of session for performance tracking
5. **Use limit orders**: Prefer LMT over MKT to control slippage
6. **Log everything**: The launcher outputs structured JSON — redirect to files for audit trail

## Direct API Testing (Outside Kimi)

```bash
# Test Gateway connectivity
curl -k https://localhost:5000/v1/api/sso/validate

# Get account list
curl -k https://localhost:5000/v1/api/iserver/accounts

# Search for AAPL
curl -k 'https://localhost:5000/v1/api/iserver/secdef/search?symbol=AAPL&secType=STK'
```
