#!/usr/bin/env python3
"""
策略引擎：根据 pipeline 上下文生成交易信号。
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DAILY_DB_PATH = SCRIPT_DIR.parent / "data" / "stock_daily.sqlite"


@dataclass
class StrategySignal:
    strategy: str
    symbol: str
    action: str
    confidence: float
    reason: str
    score: float
    price: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if payload.get("metadata") is None:
            payload["metadata"] = {}
        return payload


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_symbol(symbol: Any) -> str:
    raw = str(symbol or "").upper().strip()
    return raw.split(":")[-1] if raw else ""


def _build_quote_map(quotes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for quote in quotes or []:
        symbol = _normalize_symbol(quote.get("symbol"))
        if symbol:
            out[symbol] = quote
    return out


def _extract_price(quote: Optional[Dict[str, Any]]) -> Optional[float]:
    if not quote:
        return None
    return _to_float(quote.get("price"))


def _extract_recommend_all(quote: Optional[Dict[str, Any]]) -> Optional[float]:
    if not quote:
        return None
    technical = quote.get("technical", {})
    if not isinstance(technical, dict):
        return None
    return _to_float(technical.get("recommend_all"))


def _load_daily_bars_from_sqlite(db_path: Path, symbol: str, limit: int = 420) -> List[Dict[str, float]]:
    if not db_path.exists():
        return []
    query = """
    SELECT trade_date, open, high, low, close, volume
    FROM stock_daily
    WHERE symbol = ?
    ORDER BY trade_date DESC
    LIMIT ?
    """
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(query, (symbol, limit)).fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()

    bars: List[Dict[str, float]] = []
    for row in reversed(rows):
        bars.append(
            {
                "trade_date": row[0],
                "open": _to_float(row[1]) or 0.0,
                "high": _to_float(row[2]) or 0.0,
                "low": _to_float(row[3]) or 0.0,
                "close": _to_float(row[4]) or 0.0,
                "volume": _to_float(row[5]) or 0.0,
            }
        )
    return bars


def _simple_local_lows(closes: List[float], window: int = 3) -> List[int]:
    out: List[int] = []
    for i in range(window, len(closes) - window):
        cur = closes[i]
        left = closes[i - window : i]
        right = closes[i + 1 : i + window + 1]
        if left and right and cur <= min(left) and cur <= min(right):
            out.append(i)
    return out


def _safe_log_return(a: float, b: float) -> float:
    if a <= 0 or b <= 0:
        return 0.0
    return math.log(b / a)


def _window_volatility(closes: List[float], start: int, end: int) -> float:
    seg = closes[start : end + 1]
    if len(seg) < 2:
        return 1.0
    returns = [_safe_log_return(seg[i - 1], seg[i]) for i in range(1, len(seg))]
    if not returns:
        return 1.0
    mean_r = sum(returns) / len(returns)
    var = sum((x - mean_r) ** 2 for x in returns) / len(returns)
    return math.sqrt(max(var, 0.0))


def _compute_return(closes: List[float], days: int) -> Optional[float]:
    if len(closes) <= days or closes[-days - 1] <= 0:
        return None
    return closes[-1] / closes[-days - 1] - 1.0


def _rank_to_percentile_desc(values: Dict[str, Optional[float]]) -> Dict[str, float]:
    valid = [(k, v) for k, v in values.items() if v is not None]
    if not valid:
        return {}
    sorted_items = sorted(valid, key=lambda kv: kv[1], reverse=True)
    total = len(sorted_items)
    out: Dict[str, float] = {}
    for idx, (symbol, _) in enumerate(sorted_items, 1):
        # top rank -> 100.0, bottom -> about 1/total*100
        out[symbol] = (total - idx + 1) / total * 100.0
    return out


def _detect_w_bottom_pattern(bars: List[Dict[str, float]]) -> Optional[Dict[str, Any]]:
    if len(bars) < 120:
        return None

    closes = [bar["close"] for bar in bars]
    highs = [bar["high"] for bar in bars]
    lows_idx = _simple_local_lows(closes, window=3)
    if len(lows_idx) < 2:
        return None

    best: Optional[Dict[str, Any]] = None
    for left_idx in lows_idx[:-1]:
        for right_idx in lows_idx[lows_idx.index(left_idx) + 1 :]:
            span = right_idx - left_idx
            if span < 15 or span > 180:
                continue

            left_low = closes[left_idx]
            right_low = closes[right_idx]
            baseline = max(left_low, right_low, 1e-9)
            low_gap = abs(left_low - right_low) / baseline
            if low_gap > 0.08:
                continue

            mid_seg = closes[left_idx : right_idx + 1]
            neckline_price = max(mid_seg)
            neckline_idx = left_idx + mid_seg.index(neckline_price)
            support_price = min(left_low, right_low)
            if neckline_price <= support_price * 1.08:
                continue

            latest_close = closes[-1]
            latest_high = highs[-1]
            distance_to_neckline = (neckline_price - latest_close) / max(neckline_price, 1e-9)
            is_near_breakout = support_price <= latest_close <= neckline_price and distance_to_neckline <= 0.05
            is_breakout = latest_high >= neckline_price
            if not is_near_breakout and not is_breakout:
                continue

            vol = _window_volatility(closes, left_idx, right_idx)
            upside_ratio = (neckline_price - support_price) / max(neckline_price, 1e-9)
            candidate = {
                "left_idx": left_idx,
                "right_idx": right_idx,
                "neckline_idx": neckline_idx,
                "span_days": span,
                "support_price": support_price,
                "neckline_price": neckline_price,
                "latest_close": latest_close,
                "latest_high": latest_high,
                "breakout_state": "breakout" if is_breakout else "near_breakout",
                "distance_to_neckline": max(distance_to_neckline, 0.0),
                "volatility": vol,
                "upside_ratio": upside_ratio,
            }
            if best is None or candidate["upside_ratio"] > best["upside_ratio"]:
                best = candidate
    return best


def _score_w_bottom_candidate(
    candidate: Dict[str, Any],
    rps120: float,
    rps250: float,
) -> float:
    vol = _to_float(candidate.get("volatility")) or 1.0
    span = _to_float(candidate.get("span_days")) or 0.0
    upside = _to_float(candidate.get("upside_ratio")) or 0.0

    vol_score = _clamp(1.0 - vol * 20.0, 0.0, 1.0)
    span_score = _clamp(span / 180.0, 0.0, 1.0)
    upside_score = _clamp(upside / 0.25, 0.0, 1.0)
    rps_score = _clamp((rps120 + rps250) / 200.0, 0.0, 1.0)
    state_bonus = 0.1 if candidate.get("breakout_state") == "breakout" else 0.05

    return 0.3 * vol_score + 0.25 * span_score + 0.25 * upside_score + 0.2 * rps_score + state_bonus


def _run_w_bottom_breakout(context: Dict[str, Any]) -> List[StrategySignal]:
    tickers = context.get("universe_tickers") or context.get("selected_top_tickers") or []
    symbols = [_normalize_symbol(x) for x in tickers if _normalize_symbol(x)]
    if not symbols:
        return []

    db_path_raw = context.get("history_db_path")
    db_path = Path(str(db_path_raw)).resolve() if db_path_raw else DEFAULT_DAILY_DB_PATH
    lookback = int((_to_float(context.get("history_lookback_days")) or 420))
    top_k = int((_to_float(context.get("strategy_prefilter_top_k")) or 10))
    top_k = max(top_k, 1)

    quote_map = _build_quote_map(context.get("quotes", []) or [])

    symbol_close_map: Dict[str, List[float]] = {}
    pattern_map: Dict[str, Dict[str, Any]] = {}
    ret120_map: Dict[str, Optional[float]] = {}
    ret250_map: Dict[str, Optional[float]] = {}

    for symbol in symbols:
        bars = _load_daily_bars_from_sqlite(db_path, symbol, limit=lookback)
        if len(bars) < 120:
            continue
        closes = [bar["close"] for bar in bars]
        symbol_close_map[symbol] = closes
        ret120_map[symbol] = _compute_return(closes, 120)
        ret250_map[symbol] = _compute_return(closes, 250)

        pattern = _detect_w_bottom_pattern(bars)
        if pattern is not None:
            pattern_map[symbol] = pattern

    if not pattern_map:
        return []

    rps120_rank = _rank_to_percentile_desc(ret120_map)
    rps250_rank = _rank_to_percentile_desc(ret250_map)

    signals: List[StrategySignal] = []
    for symbol, pattern in pattern_map.items():
        rps120 = rps120_rank.get(symbol, 50.0)
        rps250 = rps250_rank.get(symbol, 50.0)
        score = _score_w_bottom_candidate(pattern, rps120=rps120, rps250=rps250)
        confidence = _clamp(0.45 + score * 0.5, 0.0, 0.95)

        quote = quote_map.get(symbol, {})
        price = _extract_price(quote) or _to_float(pattern.get("latest_close"))
        state = str(pattern.get("breakout_state"))
        reason = (
            f"W底形态{state}（neckline={pattern['neckline_price']:.2f}, "
            f"support={pattern['support_price']:.2f}, score={score:.3f}）"
        )
        signals.append(
            StrategySignal(
                strategy="w_bottom_breakout",
                symbol=symbol,
                action="buy",
                confidence=confidence,
                reason=reason,
                score=score,
                price=price,
                metadata={
                    "breakout_state": state,
                    "neckline_price": round(pattern["neckline_price"], 4),
                    "support_price": round(pattern["support_price"], 4),
                    "distance_to_neckline": round(pattern["distance_to_neckline"], 6),
                    "span_days": int(pattern["span_days"]),
                    "volatility": round(pattern["volatility"], 8),
                    "upside_ratio": round(pattern["upside_ratio"], 6),
                    "rps120": round(rps120, 3),
                    "rps250": round(rps250, 3),
                },
            )
        )

    signals.sort(key=lambda x: x.score, reverse=True)
    return signals[:top_k]


def _run_news_momentum(context: Dict[str, Any]) -> List[StrategySignal]:
    ranking = context.get("ranking", []) or []
    quote_map = _build_quote_map(context.get("quotes", []) or [])
    signals: List[StrategySignal] = []

    for item in ranking[:15]:
        symbol = _normalize_symbol(item.get("ticker"))
        if not symbol:
            continue
        momentum = _to_float(item.get("momentum_score"))
        if momentum is None:
            continue

        quote = quote_map.get(symbol, {})
        price = _extract_price(quote)
        if price is None or price <= 0:
            continue

        if momentum >= 0.05:
            confidence = _clamp(0.55 + momentum * 2.0, 0.0, 0.95)
            signals.append(
                StrategySignal(
                    strategy="news_momentum",
                    symbol=symbol,
                    action="buy",
                    confidence=confidence,
                    reason=f"新闻动量偏强（momentum={momentum:.4f}）",
                    score=momentum,
                    price=price,
                )
            )
        elif momentum <= -0.12:
            confidence = _clamp(0.55 + abs(momentum) * 1.5, 0.0, 0.95)
            signals.append(
                StrategySignal(
                    strategy="news_momentum",
                    symbol=symbol,
                    action="sell",
                    confidence=confidence,
                    reason=f"新闻动量偏弱（momentum={momentum:.4f}）",
                    score=momentum,
                    price=price,
                )
            )
    return signals


def _run_market_gate_trend(context: Dict[str, Any]) -> List[StrategySignal]:
    score = _to_float(context.get("market_gate_score"))
    selected = context.get("selected_top_tickers", []) or []
    quote_map = _build_quote_map(context.get("quotes", []) or [])
    signals: List[StrategySignal] = []

    if score is None or not selected:
        return signals

    for symbol_raw in selected[:8]:
        symbol = _normalize_symbol(symbol_raw)
        if not symbol:
            continue
        quote = quote_map.get(symbol, {})
        price = _extract_price(quote)
        if price is None or price <= 0:
            continue

        rec = _extract_recommend_all(quote)
        if score >= 0.10:
            if rec is not None and rec < -0.15:
                continue
            confidence = _clamp(0.6 + score * 0.8 + max(rec or 0.0, 0.0) * 0.2, 0.0, 0.95)
            signals.append(
                StrategySignal(
                    strategy="market_gate_trend",
                    symbol=symbol,
                    action="buy",
                    confidence=confidence,
                    reason=f"市场门控偏多（gate={score:.4f}）",
                    score=score,
                    price=price,
                    metadata={"recommend_all": rec},
                )
            )
        elif score <= -0.10:
            confidence = _clamp(0.6 + abs(score) * 0.8 + max(-(rec or 0.0), 0.0) * 0.2, 0.0, 0.95)
            signals.append(
                StrategySignal(
                    strategy="market_gate_trend",
                    symbol=symbol,
                    action="sell",
                    confidence=confidence,
                    reason=f"市场门控偏空（gate={score:.4f}）",
                    score=score,
                    price=price,
                    metadata={"recommend_all": rec},
                )
            )

    return signals


_STRATEGY_HANDLERS = {
    "news_momentum": _run_news_momentum,
    "market_gate_trend": _run_market_gate_trend,
    "w_bottom_breakout": _run_w_bottom_breakout,
}


def run_strategies(strategy_names: List[str], context: Dict[str, Any], min_confidence: float = 0.6) -> Dict[str, Any]:
    """
    执行指定策略并返回交易信号。
    """
    enabled = [_normalize_symbol(name).lower() for name in strategy_names if str(name).strip()]
    min_conf = _clamp(float(min_confidence), 0.0, 1.0)

    unknown: List[str] = []
    all_signals: List[StrategySignal] = []

    for strategy_name in enabled:
        handler = _STRATEGY_HANDLERS.get(strategy_name)
        if handler is None:
            unknown.append(strategy_name)
            continue
        all_signals.extend(handler(context))

    accepted = [signal for signal in all_signals if signal.confidence >= min_conf]
    rejected = [signal for signal in all_signals if signal.confidence < min_conf]

    return {
        "enabled_strategies": enabled,
        "unknown_strategies": unknown,
        "min_confidence": min_conf,
        "signals_all": [signal.to_dict() for signal in all_signals],
        "signals_accepted": [signal.to_dict() for signal in accepted],
        "signals_rejected": [signal.to_dict() for signal in rejected],
    }
