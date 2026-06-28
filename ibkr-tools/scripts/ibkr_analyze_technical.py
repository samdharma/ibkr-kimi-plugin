#!/usr/bin/env python3
"""
ibkr-analyze-technical: Pure price-action technical analysis using IB Gateway data.

Calculates RSI, SMA, ATR, Bollinger Bands, MACD, support/resistance levels,
and a composite momentum score — all in pure Python (no dependencies).

Also fetches EMA(20) and EMA(50) directly from IB Gateway pre-computed fields.

Usage:
    python3 ibkr_analyze_technical.py <SYMBOL> [OPTIONS]

Options:
    --period       Lookback period: 1m, 3m, 6m, 1y (default: 3m)
    --bar-size     Bar size: 1d, 1h (default: 1d for trend analysis)
    --detailed     Include raw bar data in output (default: false)

Output:
    Full technical report with indicators, trend assessment, support/resistance,
    and composite momentum score (0-100).

Examples:
    python3 ibkr_analyze_technical.py AAPL
    python3 ibkr_analyze_technical.py TSLA --period 6m --detailed
    python3 ibkr_analyze_technical.py NVDA --period 1m --bar-size 1h
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import (
    get_conid, api_get, check_gateway,
    BASE_URL, print_json as _print_json
)
from ibkr_history import fetch_all_bars, parse_bar, compute_daily_change


# ---------------------------------------------------------------------------
# Technical Indicator Calculations (Pure Python)
# ---------------------------------------------------------------------------

def sma(data: list, period: int) -> list:
    """Simple Moving Average. Returns list same length as input (None for first 'period' values)."""
    result = [None] * len(data)
    for i in range(period - 1, len(data)):
        window = data[i - period + 1:i + 1]
        result[i] = round(sum(window) / period, 6)
    return result


def ema(data: list, period: int) -> list:
    """Exponential Moving Average."""
    result = [None] * len(data)
    multiplier = 2 / (period + 1)

    # First EMA = SMA
    for i in range(period - 1, len(data)):
        if i == period - 1:
            result[i] = round(sum(data[:period]) / period, 6)
        else:
            result[i] = round((data[i] - result[i-1]) * multiplier + result[i-1], 6)
    return result


def rsi(closes: list, period: int = 14) -> list:
    """Relative Strength Index (0-100)."""
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)

    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains[i] = max(change, 0)
        losses[i] = abs(min(change, 0))

    result = [None] * len(closes)

    for i in range(period, len(closes)):
        avg_gain = sum(gains[i-period+1:i+1]) / period
        avg_loss = sum(losses[i-period+1:i+1]) / period

        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = round(100 - (100 / (1 + rs)), 2)

    return result


def atr(highs: list, lows: list, closes: list, period: int = 14) -> list:
    """Average True Range."""
    tr_values = [None] * len(closes)
    tr_values[0] = highs[0] - lows[0] if highs[0] and lows[0] else 0

    for i in range(1, len(closes)):
        if highs[i] is None or lows[i] is None or closes[i-1] is None:
            tr_values[i] = tr_values[i-1] if tr_values[i-1] else 0
            continue
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i-1])
        tr3 = abs(lows[i] - closes[i-1])
        tr_values[i] = max(tr1, tr2, tr3)

    result = [None] * len(tr_values)
    for i in range(period - 1, len(tr_values)):
        window = [v for v in tr_values[i-period+1:i+1] if v is not None]
        if window:
            result[i] = round(sum(window) / len(window), 6)

    return result


def bollinger_bands(closes: list, period: int = 20, std_dev: int = 2) -> dict:
    """Bollinger Bands (middle=SMA, upper/lower = SMA +/- 2*std)."""
    middle = sma(closes, period)
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    bandwidth = [None] * len(closes)
    pct_b = [None] * len(closes)

    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        mean = middle[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance ** 0.5

        upper[i] = round(mean + std_dev * std, 6)
        lower[i] = round(mean - std_dev * std, 6)

        if upper[i] != lower[i]:
            bandwidth[i] = round((upper[i] - lower[i]) / middle[i] * 100, 4)
            pct_b[i] = round((closes[i] - lower[i]) / (upper[i] - lower[i]), 4)

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "bandwidth": bandwidth,
        "pct_b": pct_b
    }


def macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD with signal line and histogram."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    macd_line = [None] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = round(ema_fast[i] - ema_slow[i], 6)

    # Signal line = EMA of MACD
    valid_macd = [v for v in macd_line if v is not None]
    if not valid_macd:
        return {"macd": macd_line, "signal": [None]*len(closes), "histogram": [None]*len(closes)}

    # Find first valid index
    first_valid = next(i for i, v in enumerate(macd_line) if v is not None)
    signal_line = [None] * len(closes)

    for i in range(first_valid + signal - 1, len(closes)):
        if i == first_valid + signal - 1:
            window = [v for v in macd_line[first_valid:i+1] if v is not None]
            signal_line[i] = round(sum(window) / len(window), 6)
        elif macd_line[i] is not None and signal_line[i-1] is not None:
            multiplier = 2 / (signal + 1)
            signal_line[i] = round((macd_line[i] - signal_line[i-1]) * multiplier + signal_line[i-1], 6)

    histogram = [None] * len(closes)
    for i in range(len(closes)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = round(macd_line[i] - signal_line[i], 6)

    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def find_support_resistance(bars: list, lookback: int = 20, touches: int = 2) -> dict:
    """Find support and resistance levels from recent swing highs/lows."""
    if len(bars) < lookback + 2:
        return {"support": [], "resistance": []}

    highs = [b["high"] for b in bars if b.get("high") is not None]
    lows = [b["low"] for b in bars if b.get("low") is not None]

    if len(highs) < 5 or len(lows) < 5:
        return {"support": [], "resistance": []}

    # Find local maxima (resistance) and minima (support)
    resistance_levels = []
    support_levels = []

    for i in range(2, min(lookback, len(highs)) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistance_levels.append(round(highs[i], 2))
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            support_levels.append(round(lows[i], 2))

    # Cluster nearby levels (within 1%)
    def cluster_levels(levels, tolerance_pct=0.01):
        if not levels:
            return []
        levels.sort()
        clusters = [[levels[0]]]
        for lvl in levels[1:]:
            if (lvl - clusters[-1][0]) / clusters[-1][0] < tolerance_pct:
                clusters[-1].append(lvl)
            else:
                clusters.append([lvl])
        return [round(sum(c)/len(c), 2) for c in clusters]

    return {
        "support": cluster_levels(support_levels)[:5],
        "resistance": cluster_levels(resistance_levels)[:5]
    }


def fetch_gateway_ema(symbol: str, conid: int) -> dict:
    """Fetch pre-computed EMA values from IB Gateway market data snapshot."""
    # Field codes: 7676=EMA(50), 7677=EMA(20)
    result = api_get("/iserver/marketdata/snapshot", f"conids={conid}&fields=7676,7677")

    ema_data = {}
    if isinstance(result, list) and len(result) > 0:
        data = result[0]
        if "7676" in data:
            try:
                ema_data["ema_50"] = float(data["7676"])
            except (ValueError, TypeError):
                pass
        if "7677" in data:
            try:
                ema_data["ema_20"] = float(data["7677"])
            except (ValueError, TypeError):
                pass

    return ema_data


def compute_momentum_score(indicators: dict, trend: dict) -> int:
    """Compute composite momentum score (0-100)."""
    score = 50  # Neutral base

    # RSI contribution (30=oversold +20 pts, 70=overbought -20 pts)
    rsi_val = indicators.get("rsi_14")
    if rsi_val is not None:
        if rsi_val < 30:
            score += 15
        elif rsi_val < 40:
            score += 5
        elif rsi_val > 70:
            score -= 15
        elif rsi_val > 60:
            score -= 5

    # Trend alignment (above key MAs = bullish)
    if trend.get("above_sma20"):
        score += 10
    if trend.get("above_sma50"):
        score += 10
    if trend.get("above_sma200"):
        score += 10

    # MACD
    macd_hist = indicators.get("macd_histogram")
    if macd_hist is not None:
        if macd_hist > 0:
            score += 8
        else:
            score -= 8

    # Bollinger position
    bb_pct = indicators.get("bb_pct_b")
    if bb_pct is not None:
        if bb_pct < 0.2:
            score += 10  # Oversold bounce potential
        elif bb_pct > 0.8:
            score -= 10  # Overbought

    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# Main Analysis
# ---------------------------------------------------------------------------

def analyze_technical(symbol: str, period_months: int = 3, bar_size: str = "1d", detailed: bool = False) -> dict:
    """Run full technical analysis on a symbol."""

    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "_detail": conn.get("_message", "")}

    conid = get_conid(symbol)
    if conid is None:
        return {"_error": f"Contract not found: {symbol}"}

    # Calculate date range
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=period_months * 30)

    # Fetch bars
    raw_bars = fetch_all_bars(conid, bar_size, start_dt, end_dt)
    if not raw_bars:
        return {"_error": f"No historical data for {symbol}", "suggestion": "Check market data subscriptions."}

    bars = [parse_bar(b) for b in raw_bars]
    bars = compute_daily_change(bars)

    # Extract price arrays
    closes = [b["close"] for b in bars if b.get("close") is not None]
    highs = [b["high"] for b in bars if b.get("high") is not None]
    lows = [b["low"] for b in bars if b.get("low") is not None]
    volumes = [b["volume"] for b in bars if b.get("volume") is not None]

    if len(closes) < 50:
        return {"_error": f"Insufficient data: only {len(closes)} bars. Need 50+ for reliable analysis."}

    latest_bar = bars[-1]
    current_price = closes[-1]

    # --- Indicators ---
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)
    ema20_calc = ema(closes, 20)
    ema50_calc = ema(closes, 50)
    rsi14 = rsi(closes, 14)
    atr14 = atr(highs, lows, closes, 14)
    bb = bollinger_bands(closes, 20, 2)
    macd_data = macd(closes, 12, 26, 9)

    # Fetch EMA from Gateway as well
    gateway_ema = fetch_gateway_ema(symbol, conid)

    # SMA/EMA volume
    vol_sma20 = sma(volumes, 20) if len(volumes) >= 20 else [None] * len(volumes)

    # --- Trend Assessment ---
    trend = {
        "direction": "neutral",
        "strength": 0.5,
        "above_sma20": current_price > sma20[-1] if sma20[-1] else False,
        "above_sma50": current_price > sma50[-1] if sma50[-1] else False,
        "above_sma200": current_price > sma200[-1] if sma200[-1] else False,
        "golden_cross": False,
        "death_cross": False
    }

    # Golden/Death cross detection (SMA20 vs SMA50)
    if sma20[-1] and sma50[-1]:
        if sma20[-1] > sma50[-1]:
            # Check if recent crossover
            for i in range(-10, -1):
                if i + len(sma20) < len(sma20) and sma20[i] and sma50[i]:
                    if sma20[i] <= sma50[i]:
                        trend["golden_cross"] = True
                        break
            trend["direction"] = "bullish"
            trend["strength"] = round(min((current_price - sma50[-1]) / sma50[-1] * 10, 1.0), 2)
        else:
            for i in range(-10, -1):
                if i + len(sma20) < len(sma20) and sma20[i] and sma50[i]:
                    if sma20[i] >= sma50[i]:
                        trend["death_cross"] = True
                        break
            trend["direction"] = "bearish"
            trend["strength"] = round(min((sma50[-1] - current_price) / sma50[-1] * 10, 1.0), 2)

    # --- Support/Resistance ---
    levels = find_support_resistance(bars[-60:])  # Last 60 bars for levels

    # --- Composite Momentum Score ---
    indicators_latest = {
        "rsi_14": rsi14[-1] if rsi14[-1] else None,
        "macd_histogram": macd_data["histogram"][-1] if macd_data["histogram"][-1] else None,
        "bb_pct_b": bb["pct_b"][-1] if bb["pct_b"][-1] else None
    }
    momentum_score = compute_momentum_score(indicators_latest, trend)

    # Determine regime
    if momentum_score >= 70:
        regime = "strongly_bullish"
    elif momentum_score >= 55:
        regime = "bullish"
    elif momentum_score <= 30:
        regime = "strongly_bearish"
    elif momentum_score <= 45:
        regime = "bearish"
    else:
        regime = "neutral"

    # Build output
    result = {
        "symbol": symbol,
        "conid": conid,
        "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "bar_count": len(bars),
        "period_analyzed": f"{bars[0]['timestamp']} to {bars[-1]['timestamp']}",
        "current_price": current_price,
        "indicators": {
            "rsi_14": {
                "current": rsi14[-1],
                "signal": "oversold" if (rsi14[-1] or 50) < 30 else "overbought" if (rsi14[-1] or 50) > 70 else "neutral",
                "trend": "rising" if len(rsi14) > 5 and rsi14[-1] and rsi14[-5] and rsi14[-1] > rsi14[-5] else "falling"
            },
            "sma": {
                "sma_20": sma20[-1],
                "sma_50": sma50[-1],
                "sma_200": sma200[-1] if len(closes) >= 200 else None
            },
            "ema": {
                "ema_20_calc": ema20_calc[-1],
                "ema_50_calc": ema50_calc[-1],
                "ema_20_gateway": gateway_ema.get("ema_20"),
                "ema_50_gateway": gateway_ema.get("ema_50")
            },
            "atr": {
                "atr_14": atr14[-1],
                "atr_pct": round(atr14[-1] / current_price * 100, 4) if atr14[-1] and current_price else None
            },
            "bollinger": {
                "upper": bb["upper"][-1],
                "middle": bb["middle"][-1],
                "lower": bb["lower"][-1],
                "bandwidth_pct": bb["bandwidth"][-1],
                "pct_b": bb["pct_b"][-1],
                "position": "upper" if (bb["pct_b"][-1] or 0.5) > 0.8 else "lower" if (bb["pct_b"][-1] or 0.5) < 0.2 else "middle"
            },
            "macd": {
                "macd_line": macd_data["macd"][-1],
                "signal_line": macd_data["signal"][-1],
                "histogram": macd_data["histogram"][-1],
                "signal": "bullish" if (macd_data["histogram"][-1] or 0) > 0 else "bearish"
            },
            "volume": {
                "latest": volumes[-1] if volumes else None,
                "sma_20": vol_sma20[-1] if vol_sma20 and vol_sma20[-1] else None,
                "ratio": round(volumes[-1] / vol_sma20[-1], 2) if volumes and vol_sma20 and vol_sma20[-1] and vol_sma20[-1] > 0 else None
            }
        },
        "trend": trend,
        "levels": levels,
        "momentum": {
            "score": momentum_score,
            "regime": regime,
            "interpretation": _score_interpretation(momentum_score)
        }
    }

    if detailed:
        result["raw_bars"] = bars[-20:]  # Last 20 bars only

    return result


def _score_interpretation(score: int) -> str:
    """Human-readable interpretation of momentum score."""
    if score >= 80:
        return "Strong upward momentum. Consider long entries on pullbacks to support."
    elif score >= 65:
        return "Bullish bias. Favorable for long positions with proper risk management."
    elif score >= 55:
        return "Slightly bullish. Cautious optimism, wait for confirmation."
    elif score >= 45:
        return "Neutral. No clear directional edge. Stay flat or reduce exposure."
    elif score >= 35:
        return "Slightly bearish. Consider reducing long exposure or hedging."
    elif score >= 20:
        return "Bearish bias. Favorable for short positions or defensive posture."
    else:
        return "Strong downward momentum. Consider short entries on rallies to resistance."


def main():
    parser = argparse.ArgumentParser(
        description="Technical analysis for a stock using IB Gateway data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s AAPL
  %(prog)s TSLA --period 6m --detailed
  %(prog)s NVDA --period 1m --bar-size 1h
        """
    )

    parser.add_argument("symbol", help="Stock ticker symbol")
    parser.add_argument("--period", choices=["1m", "3m", "6m", "1y"], default="3m",
                        help="Lookback period (default: 3m)")
    parser.add_argument("--bar-size", choices=["1d", "1h"], default="1d",
                        help="Bar size for analysis (default: 1d)")
    parser.add_argument("--detailed", action="store_true", default=False,
                        help="Include last 20 raw bars")

    args = parser.parse_args()

    period_map = {"1m": 1, "3m": 3, "6m": 6, "1y": 12}
    period_months = period_map[args.period]

    result = analyze_technical(args.symbol.upper(), period_months, args.bar_size, args.detailed)

    if "_error" in result:
        print(json.dumps({"status": "ERROR", "message": result["_error"], "detail": result.get("_detail", "")}))
        sys.exit(1)

    print(json.dumps({"status": "OK", **result}, indent=2))


if __name__ == "__main__":
    main()
