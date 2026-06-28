# IBKR Trading Assistant

This repository is an Interactive Brokers trading assistant that connects to a locally running IB Gateway (Client Portal API).

## Invocation

Invoke all functionality through the `bin/ibkr` launcher:

```bash
bin/ibkr status
bin/ibkr quote AAPL
bin/ibkr search AAPL
bin/ibkr positions
bin/ibkr account
bin/ibkr orders
bin/ibkr order AAPL BUY 10 LMT 195.50
bin/ibkr cancel-order <order_id>
bin/ibkr history AAPL --start-date 2026-01-01 --end-date 2026-06-28 --bar-size 1d --format csv --output aapl.csv
bin/ibkr pnl
bin/ibkr gap-scan --min-gap 3 --direction up --universe nasdaq100
bin/ibkr market-movers --type gainers --count 10 --session pre_market
bin/ibkr analyze-technical AAPL --period 3m
bin/ibkr analyze-setup NVDA --direction long
bin/ibkr analyze-finnhub TSLA
bin/ibkr briefing --universe nasdaq100 --gap-min 3
```

## Pre-flight

- Always run `bin/ibkr status` first to confirm the IB Gateway is running and authenticated.
- Default gateway endpoint is `https://localhost:4004/v1/api` (override with `IB_GATEWAY_HOST` and `IB_GATEWAY_PORT`).
- Paper trading is the default (`IB_PAPER_TRADING=true`). Live trading requires explicitly setting `IB_PAPER_TRADING=false`.

## Risk rules

- Preview every order before submission and report margin impact.
- Do not submit live orders without explicit user confirmation.
- Enforce position limits, cash reserve, and stop-loss discipline from `skills/ibkr-trading/SKILL.md`.
