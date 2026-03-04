#!/usr/bin/env python3
"""
策略引擎：根据 pipeline 上下文生成交易信号。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


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
