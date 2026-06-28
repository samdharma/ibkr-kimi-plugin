#!/usr/bin/env python3
"""
ibkr-analyze-setup: ORB-specific trade setup evaluator.

Grades potential trades A+ through F based on:
- Gap quality (direction, magnitude, not parabolic)
- Volume confirmation (pre-market vs average)
- Technical alignment (trend, RSI, moving averages)
- Risk/reward ratio (ATR-based stops)
- Catalyst assessment (news, earnings proximity)

Usage:
    python3 ibkr_analyze_setup.py <SYMBOL> [OPTIONS]

Options:
    --strategy     Strategy type: ORB, GAP_GO, MOMENTUM, REVERSAL (default: ORB)
    --direction    Expected direction: long, short (default: auto-detect)
    --entry        Planned entry price (optional)
    --stop         Planned stop price (optional)
    --target       Planned target price (optional)
    --detailed     Include full technical breakdown (default: false)

Output:
    Graded setup report with score, components, and recommendation (TAKE/WATCH/PASS/CAUTION).

Examples:
    python3 ibkr_analyze_setup.py NVDA
    python3 ibkr_analyze_setup.py AAPL --strategy ORB --direction long
    python3 ibkr_analyze_setup.py TSLA --entry 242.50 --stop 238.00 --target 250.00
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_core import get_conid, api_get, check_gateway
from ibkr_history import fetch_all_bars, parse_bar, compute_daily_change
from ibkr_analyze_technical import (
    sma, ema, rsi, atr, bollinger_bands, macd,
    find_support_resistance, compute_momentum_score
)


# ---------------------------------------------------------------------------
# Scoring Rubric
# ---------------------------------------------------------------------------

GRADE_THRESHOLDS = [
    (95, "A+", "Exceptional setup — high confidence"),
    (88, "A",  "Excellent setup — strong edge"),
    (82, "A-", "Very good setup — favorable conditions"),
    (75, "B+", "Good setup — worth taking with proper sizing"),
    (68, "B",  "Above average — reasonable edge"),
    (62, "B-", "Decent setup — manage risk carefully"),
    (55, "C+", "Marginal — borderline, requires confirmation"),
    (48, "C",  "Average — no clear edge, stay flat"),
    (42, "C-", "Below average — avoid unless exceptional catalyst"),
    (35, "D",  "Weak — unfavorable risk/reward"),
    (0,  "F",  "Poor — do not take this setup")
]


def score_to_grade(score: int) -> tuple:
    """Convert numeric score to letter grade."""
    for threshold, grade, desc in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade, desc
    return "F", "Poor — do not take this setup"


# ---------------------------------------------------------------------------
# Component Scorers
# ---------------------------------------------------------------------------

def score_gap(gap_pct: float, direction: str, avg_atr_pct: float) -> dict:
    """Score gap quality (0-100). Penalizes gaps that are too small or too extreme."""
    abs_gap = abs(gap_pct)

    # Ideal gap: 2-8% for most stocks
    if 2 <= abs_gap <= 6:
        score = 85
        assessment = f"Clean {abs_gap:.1f}% gap — ideal range for follow-through"
    elif 1 <= abs_gap < 2:
        score = 60
        assessment = f"Modest {abs_gap:.1f}% gap — may lack momentum"
    elif 6 < abs_gap <= 10:
        score = 70
        assessment = f"Large {abs_gap:.1f}% gap — risk of reversal/fade"
    elif 10 < abs_gap <= 20:
        score = 45
        assessment = f"Extended {abs_gap:.1f}% gap — parabolic risk, wait for pullback"
    else:
        score = 25
        assessment = f"Extreme {abs_gap:.1f}% gap — likely gap-fill, avoid chase"

    # Bonus for gap being 1-3x ATR (normal, not anomalous)
    if avg_atr_pct > 0:
        gap_atr_ratio = abs_gap / avg_atr_pct
        if 1 <= gap_atr_ratio <= 3:
            score += 5
            assessment += ", normal vs recent volatility"
        elif gap_atr_ratio > 5:
            score -= 10
            assessment += ", abnormal vs recent volatility"

    return {
        "score": max(0, min(100, score)),
        "gap_pct": round(gap_pct, 2),
        "abs_gap_pct": round(abs_gap, 2),
        "direction": direction,
        "assessment": assessment
    }


def score_volume(premkt_volume: int, avg_volume: int) -> dict:
    """Score volume confirmation (0-100)."""
    if not avg_volume or avg_volume == 0:
        return {"score": 50, "premkt_volume_ratio": 0, "assessment": "Volume data unavailable"}

    ratio = premkt_volume / avg_volume

    if ratio >= 3:
        score = 90
        assessment = f"{ratio:.1f}x average volume — exceptional institutional interest"
    elif ratio >= 2:
        score = 80
        assessment = f"{ratio:.1f}x average volume — strong pre-market participation"
    elif ratio >= 1:
        score = 65
        assessment = f"{ratio:.1f}x average volume — decent interest"
    elif ratio >= 0.5:
        score = 45
        assessment = f"{ratio:.1f}x average volume — below average, low conviction"
    else:
        score = 25
        assessment = f"{ratio:.1f}x average volume — very weak interest"

    return {
        "score": score,
        "premkt_volume": premkt_volume,
        "avg_daily_volume": avg_volume,
        "premkt_volume_ratio": round(ratio, 2),
        "assessment": assessment
    }


def score_technical(closes: list, highs: list, lows: list, direction: str) -> dict:
    """Score technical alignment (0-100)."""
    if len(closes) < 50:
        return {"score": 50, "assessment": "Insufficient data for technical analysis"}

    current_price = closes[-1]
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    rsi14 = rsi(closes, 14)
    atr14 = atr(highs, lows, closes, 14)
    macd_data = macd(closes, 12, 26, 9)

    score = 50
    details = []

    # Trend alignment
    above_sma20 = current_price > sma20[-1] if sma20[-1] else False
    above_sma50 = current_price > sma50[-1] if sma50[-1] else False

    if direction == "long":
        if above_sma20 and above_sma50:
            score += 15
            details.append("Price above SMA20 and SMA50 — bullish trend")
        elif above_sma20:
            score += 5
            details.append("Price above SMA20 but below SMA50 — mixed")
        else:
            score -= 10
            details.append("Price below key MAs — counter-trend long")
    elif direction == "short":
        if not above_sma20 and not above_sma50:
            score += 15
            details.append("Price below SMA20 and SMA50 — bearish trend")
        elif not above_sma20:
            score += 5
            details.append("Price below SMA20 but above SMA50 — mixed")
        else:
            score -= 10
            details.append("Price above key MAs — counter-trend short")

    # RSI check (don't buy overbought, don't sell oversold)
    current_rsi = rsi14[-1] if rsi14[-1] else 50
    if direction == "long":
        if current_rsi < 35:
            score += 10
            details.append(f"RSI {current_rsi} — oversold bounce potential")
        elif current_rsi > 75:
            score -= 15
            details.append(f"RSI {current_rsi} — overbought, risky long")
        else:
            details.append(f"RSI {current_rsi} — neutral zone")
    elif direction == "short":
        if current_rsi > 70:
            score += 10
            details.append(f"RSI {current_rsi} — overbought fade potential")
        elif current_rsi < 25:
            score -= 15
            details.append(f"RSI {current_rsi} — oversold, risky short")
        else:
            details.append(f"RSI {current_rsi} — neutral zone")

    # MACD alignment
    macd_hist = macd_data["histogram"][-1] if macd_data["histogram"][-1] else 0
    if direction == "long" and macd_hist > 0:
        score += 10
        details.append("MACD histogram positive — momentum aligned")
    elif direction == "short" and macd_hist < 0:
        score += 10
        details.append("MACD histogram negative — momentum aligned")
    elif direction == "long" and macd_hist < 0:
        score -= 5
        details.append("MACD histogram negative — momentum against long")
    elif direction == "short" and macd_hist > 0:
        score -= 5
        details.append("MACD histogram positive — momentum against short")

    return {
        "score": max(0, min(100, score)),
        "rsi": round(current_rsi, 1),
        "above_sma20": above_sma20,
        "above_sma50": above_sma50,
        "macd_histogram": round(macd_hist, 4),
        "atr_14": round(atr14[-1], 4) if atr14[-1] else None,
        "assessment": "; ".join(details)
    }


def score_risk_reward(entry: float, stop: float, target: float, direction: str, atr: float) -> dict:
    """Score risk/reward setup (0-100)."""
    risk = abs(entry - stop)
    reward = abs(target - entry)

    if risk <= 0:
        return {"score": 0, "risk_reward_ratio": 0, "assessment": "Invalid risk (stop = entry)"}

    rr_ratio = reward / risk

    # Score based on R:R ratio
    if rr_ratio >= 4:
        score = 95
        assessment = f"Exceptional {rr_ratio:.1f}:1 risk/reward"
    elif rr_ratio >= 3:
        score = 85
        assessment = f"Excellent {rr_ratio:.1f}:1 risk/reward"
    elif rr_ratio >= 2.5:
        score = 75
        assessment = f"Good {rr_ratio:.1f}:1 risk/reward"
    elif rr_ratio >= 2:
        score = 65
        assessment = f"Acceptable {rr_ratio:.1f}:1 risk/reward"
    elif rr_ratio >= 1.5:
        score = 50
        assessment = f"Marginal {rr_ratio:.1f}:1 risk/reward"
    elif rr_ratio >= 1:
        score = 35
        assessment = f"Poor {rr_ratio:.1f}:1 risk/reward — not worth the risk"
    else:
        score = 15
        assessment = f"Terrible {rr_ratio:.1f}:1 risk/reward — avoid"

    # Bonus: stop within 1.5-2x ATR is reasonable
    if atr and atr > 0:
        risk_atr_multiple = risk / atr
        if 1 <= risk_atr_multiple <= 2.5:
            score += 5
            assessment += f", stop at {risk_atr_multiple:.1f}x ATR (reasonable)"
        elif risk_atr_multiple > 4:
            score -= 10
            assessment += f", stop too wide at {risk_atr_multiple:.1f}x ATR"

    return {
        "score": max(0, min(100, score)),
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "risk": round(risk, 2),
        "reward": round(reward, 2),
        "risk_reward_ratio": round(rr_ratio, 2),
        "risk_in_atr": round(risk / atr, 2) if atr else None,
        "assessment": assessment
    }


def auto_compute_levels(current_price: float, direction: str, atr_val: float,
                        levels: dict, gap_pct: float) -> tuple:
    """Auto-compute entry, stop, and target if not provided."""
    if direction == "long":
        entry = current_price
        # Stop: below nearest support or 1.5x ATR below entry
        if levels.get("support"):
            nearest_support = max(levels["support"])  # Highest support below price
            atr_stop = entry - 1.5 * atr_val
            stop = max(nearest_support, atr_stop) if nearest_support < entry else atr_stop
        else:
            stop = entry - 1.5 * atr_val
        # Target: 2.5x risk or nearest resistance
        risk = entry - stop
        if levels.get("resistance"):
            nearest_resistance = min(levels["resistance"])  # Lowest resistance above price
            atr_target = entry + 2.5 * risk
            target = min(nearest_resistance, atr_target) if nearest_resistance > entry else atr_target
        else:
            target = entry + 2.5 * risk
    else:  # short
        entry = current_price
        if levels.get("resistance"):
            nearest_resistance = min(levels["resistance"])
            atr_stop = entry + 1.5 * atr_val
            stop = min(nearest_resistance, atr_stop) if nearest_resistance > entry else atr_stop
        else:
            stop = entry + 1.5 * atr_val
        risk = stop - entry
        if levels.get("support"):
            nearest_support = max(levels["support"])
            atr_target = entry - 2.5 * risk
            target = max(nearest_support, atr_target) if nearest_support < entry else atr_target
        else:
            target = entry - 2.5 * risk

    return round(entry, 2), round(stop, 2), round(target, 2)


# ---------------------------------------------------------------------------
# Main Setup Analyzer
# ---------------------------------------------------------------------------

def analyze_setup(symbol: str, strategy: str = "ORB", direction: str = None,
                  user_entry: float = None, user_stop: float = None,
                  user_target: float = None, detailed: bool = False) -> dict:
    """Run full ORB/setup analysis and grading."""

    conn = check_gateway()
    if "_error" in conn:
        return {"_error": "IB Gateway not connected", "detail": conn.get("_message", "")}

    conid = get_conid(symbol)
    if conid is None:
        return {"_error": f"Contract not found: {symbol}"}

    # Fetch current quote
    quote_result = api_get("/iserver/marketdata/snapshot", f"conids={conid}&fields=31,83,84,7295,7676,85,86")
    current_price = None
    prev_close = None
    premkt_volume = 0

    if isinstance(quote_result, list) and len(quote_result) > 0:
        q = quote_result[0]
        current_price = float(q.get("31", 0)) or None  # Last price
        prev_close = float(q.get("7676", 0)) or None
        premkt_volume = int(float(q.get("7295", 0))) if q.get("7295") else 0

    if not current_price:
        return {"_error": "Cannot get current price"}

    # Calculate gap
    gap_pct = 0
    if prev_close and prev_close > 0:
        gap_pct = round((current_price - prev_close) / prev_close * 100, 2)

    # Auto-detect direction
    if not direction:
        direction = "long" if gap_pct >= 0 else "short"

    # Fetch historical bars for technical analysis
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=90)
    raw_bars = fetch_all_bars(conid, "1d", start_dt, end_dt)

    bars = [parse_bar(b) for b in raw_bars] if raw_bars else []
    closes = [b["close"] for b in bars if b.get("close") is not None] if bars else []
    highs = [b["high"] for b in bars if b.get("high") is not None] if bars else []
    lows = [b["low"] for b in bars if b.get("low") is not None] if bars else []
    volumes = [b["volume"] for b in bars if b.get("volume") is not None] if bars else []

    # Compute indicators
    atr14 = atr(highs, lows, closes, 14) if len(closes) >= 14 else [None] * len(closes)
    current_atr = atr14[-1] if atr14 and atr14[-1] else current_price * 0.02

    avg_volume = sum(volumes[-20:]) / len(volumes[-20:]) if len(volumes) >= 20 else 0

    levels = find_support_resistance(bars[-60:]) if len(bars) >= 20 else {"support": [], "resistance": []}

    # Auto-compute levels if not provided
    if user_entry and user_stop and user_target:
        entry, stop, target = user_entry, user_stop, user_target
    else:
        entry, stop, target = auto_compute_levels(current_price, direction, current_atr, levels, gap_pct)

    # Score each component
    gap_score = score_gap(gap_pct, direction, (current_atr / current_price * 100) if current_atr else 0)
    vol_score = score_volume(premkt_volume, int(avg_volume))
    tech_score = score_technical(closes, highs, lows, direction) if len(closes) >= 50 else {"score": 50, "rsi": None, "assessment": "Insufficient history"}
    rr_score = score_risk_reward(entry, stop, target, direction, current_atr)

    # Catalyst score placeholder (would be enriched by Finnhub data)
    catalyst_score = {
        "score": 50,
        "has_earnings_soon": False,
        "days_to_earnings": None,
        "news_sentiment": "neutral",
        "assessment": "Catalyst data not available — check Finnhub integration"
    }

    # Weighted composite score
    weights = {
        "gap_quality": 0.25,
        "volume_confirmation": 0.20,
        "technical_alignment": 0.25,
        "risk_reward": 0.20,
        "catalyst": 0.10
    }

    composite = round(
        gap_score["score"] * weights["gap_quality"] +
        vol_score["score"] * weights["volume_confirmation"] +
        tech_score["score"] * weights["technical_alignment"] +
        rr_score["score"] * weights["risk_reward"] +
        catalyst_score["score"] * weights["catalyst"]
    )

    grade, grade_desc = score_to_grade(composite)

    # Recommendation
    if composite >= 75:
        action = "TAKE"
        confidence = round(composite / 100, 2)
        rationale = f"Strong {grade} setup with favorable risk/reward. All key components score well."
    elif composite >= 60:
        action = "WATCH"
        confidence = round(composite / 100, 2)
        rationale = f"Decent {grade} setup but needs confirmation. Wait for entry trigger or volume pickup."
    elif composite >= 45:
        action = "CAUTION"
        confidence = round(composite / 100, 2)
        rationale = f"Marginal {grade} setup. Consider only with strong catalyst or as a paper trade."
    else:
        action = "PASS"
        confidence = round((100 - composite) / 100, 2)
        rationale = f"Weak {grade} setup. Unfavorable risk/reward or conflicting signals. Skip."

    # Key trigger level
    if direction == "long":
        key_level = round(entry + 0.5 * (target - entry) / 5, 2)  # Slightly above entry
        invalidation = stop
    else:
        key_level = round(entry - 0.5 * (entry - target) / 5, 2)
        invalidation = stop

    result = {
        "symbol": symbol,
        "conid": conid,
        "strategy": strategy,
        "direction": direction,
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_price": round(current_price, 2),
        "prev_close": round(prev_close, 2) if prev_close else None,
        "gap_pct": round(gap_pct, 2),
        "grade": grade,
        "grade_description": grade_desc,
        "composite_score": composite,
        "components": {
            "gap_quality": gap_score,
            "volume_confirmation": vol_score,
            "technical_alignment": {
                "score": tech_score["score"],
                "rsi": tech_score.get("rsi"),
                "above_sma20": tech_score.get("above_sma20"),
                "above_sma50": tech_score.get("above_sma50"),
                "macd_histogram": tech_score.get("macd_histogram"),
                "atr_14": tech_score.get("atr_14"),
                "assessment": tech_score["assessment"]
            },
            "risk_reward": rr_score,
            "catalyst": catalyst_score
        },
        "recommended_levels": {
            "entry": entry,
            "stop": stop,
            "target": target,
            "key_trigger": key_level,
            "invalidation": invalidation
        },
        "support_resistance": levels,
        "recommendation": {
            "action": action,
            "confidence": confidence,
            "rationale": rationale
        }
    }

    if detailed:
        result["recent_bars"] = bars[-10:] if len(bars) >= 10 else bars

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate a trade setup with A-F grading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s NVDA
  %(prog)s AAPL --strategy ORB --direction long
  %(prog)s TSLA --entry 242.50 --stop 238.00 --target 250.00
  %(prog)s AMD --direction short --detailed
        """
    )

    parser.add_argument("symbol", help="Stock ticker symbol")
    parser.add_argument("--strategy", choices=["ORB", "GAP_GO", "MOMENTUM", "REVERSAL"], default="ORB")
    parser.add_argument("--direction", choices=["long", "short"], default=None,
                        help="Trade direction (auto-detected from gap if not specified)")
    parser.add_argument("--entry", type=float, default=None, help="Planned entry price")
    parser.add_argument("--stop", type=float, default=None, help="Planned stop price")
    parser.add_argument("--target", type=float, default=None, help="Planned target price")
    parser.add_argument("--detailed", action="store_true", default=False)

    args = parser.parse_args()

    result = analyze_setup(
        args.symbol.upper(),
        strategy=args.strategy,
        direction=args.direction,
        user_entry=args.entry,
        user_stop=args.stop,
        user_target=args.target,
        detailed=args.detailed
    )

    if "_error" in result:
        print(json.dumps({"status": "ERROR", "message": result["_error"], "detail": result.get("detail", "")}))
        sys.exit(1)

    print(json.dumps({"status": "OK", **result}, indent=2))


if __name__ == "__main__":
    main()
