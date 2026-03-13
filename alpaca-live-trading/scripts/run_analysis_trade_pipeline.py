#!/usr/bin/env python3
"""
Alpaca Live Trading 一体化流程:
1) 读取 position.jsonl / balance.jsonl
2) 分析股票池（默认 101 只）:
   - AlphaVantage 基本面
   - AlphaVantage 新闻与情绪
   - Polymarket 市场赔率
   - tvscreener 价格与技术面
3) 可选执行交易计划
4) 交易后更新 position.jsonl / balance.jsonl（由 execute_alpaca_trade.py 完成）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 确保可以导入同目录脚本
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _config import get_risk_config, get_strategy_config, load_config
from order_builder import build_trade_plan
from query_fundamentals import fetch_fundamentals_for_symbol
from query_market_news import fetch_news_per_ticker
from query_polymarket_sentiment import get_financial_sentiment
from query_stock_prices import DEFAULT_SYMBOLS, _load_market_snapshot, get_quote
from risk_guard import apply_risk_guard
from strategy_engine import run_strategies


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _tail_rows(rows: List[Dict[str, Any]], n: int = 5) -> List[Dict[str, Any]]:
    return rows[-n:] if len(rows) > n else rows


def _extract_latest_account_snapshot(balance_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in reversed(balance_rows or []):
        account = row.get("account")
        if isinstance(account, dict):
            return account
    return {}


def _extract_latest_positions_snapshot(balance_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for row in reversed(balance_rows or []):
        positions = row.get("positions")
        if isinstance(positions, list):
            return positions
    return []


def _execute_trade_plan(trade_plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    exec_script = SCRIPT_DIR / "execute_alpaca_trade.py"
    results: List[Dict[str, Any]] = []
    for item in trade_plan:
        action = str(item.get("action", "")).lower().strip()
        symbol = str(item.get("symbol", "")).upper().strip()
        qty = int(item.get("qty", 0))
        if action not in {"buy", "sell"} or not symbol or qty <= 0:
            results.append(
                {
                    "status": "skipped",
                    "input": item,
                    "reason": "invalid action/symbol/qty",
                }
            )
            continue

        cmd = [
            sys.executable,
            str(exec_script),
            "--action",
            action,
            "--symbol",
            symbol,
            "--qty",
            str(qty),
            "--json",
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            try:
                payload = json.loads(completed.stdout)
                results.append({"status": "ok", "trade": payload})
            except Exception:
                results.append(
                    {
                        "status": "ok_non_json",
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                    }
                )
        else:
            results.append(
                {
                    "status": "failed",
                    "input": item,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )
    return results


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_av_time(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # AlphaVantage time format: YYYYMMDDTHHMMSS
        return datetime.strptime(ts[:15], "%Y%m%dT%H%M%S")
    except Exception:
        return None


def _article_signal(article: Dict[str, Any]) -> float:
    ticker_score = _to_float(article.get("target_ticker_sentiment_score"))
    overall_score = _to_float(article.get("overall_sentiment_score"))
    if ticker_score is not None and overall_score is not None:
        return 0.7 * ticker_score + 0.3 * overall_score
    if ticker_score is not None:
        return ticker_score
    if overall_score is not None:
        return overall_score
    return 0.0


def _compute_news_rank(item: Dict[str, Any]) -> Dict[str, Any]:
    articles = item.get("articles", []) or []
    scores: List[float] = []
    if not articles:
        return {
            "ticker": item.get("ticker"),
            "news_count": 0,
            "avg_ticker_sentiment_score": item.get("avg_ticker_sentiment_score"),
            "avg_overall_sentiment_score": item.get("avg_overall_sentiment_score"),
            "momentum_score": -1.0,
        }

    latest_ts = max((_parse_av_time(a.get("time_published", "")) for a in articles), default=None)
    for a in articles:
        base = _article_signal(a)
        ts = _parse_av_time(a.get("time_published", ""))
        if latest_ts is not None and ts is not None:
            delta_hours = max((latest_ts - ts).total_seconds() / 3600.0, 0.0)
            recency_weight = 1.0 / (1.0 + delta_hours / 24.0)  # 半衰近似：按天衰减
        else:
            recency_weight = 0.7
        scores.append(base * recency_weight)

    # 少样本惩罚，避免 1-2 条新闻噪声过大
    count = len(articles)
    count_penalty = min(count / 5.0, 1.0)
    momentum = (sum(scores) / max(count, 1)) * count_penalty
    return {
        "ticker": item.get("ticker"),
        "news_count": count,
        "avg_ticker_sentiment_score": item.get("avg_ticker_sentiment_score"),
        "avg_overall_sentiment_score": item.get("avg_overall_sentiment_score"),
        "momentum_score": round(momentum, 6),
    }


def _select_top_by_news(news_items: List[Dict[str, Any]], top_k: int) -> Tuple[List[str], List[Dict[str, Any]]]:
    scored = [_compute_news_rank(item) for item in news_items]
    ranked = sorted(
        scored,
        key=lambda x: (
            _to_float(x.get("momentum_score")) if _to_float(x.get("momentum_score")) is not None else -999,
            _to_float(x.get("avg_ticker_sentiment_score")) if _to_float(x.get("avg_ticker_sentiment_score")) is not None else -999,
            x.get("news_count", 0),
        ),
        reverse=True,
    )
    selected = [x.get("ticker") for x in ranked[:top_k] if x.get("ticker")]
    return selected, ranked


def _to_ratio_01(value: Optional[float], low: float, high: float) -> float:
    if value is None or high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _latest_quarter_growth(
    quarterly: List[Dict[str, Any]],
    key: str,
) -> Optional[float]:
    if not quarterly or len(quarterly) < 2:
        return None
    latest = _to_float(quarterly[0].get(key))
    prev = _to_float(quarterly[1].get(key))
    if latest is None or prev in (None, 0):
        return None
    return latest / prev - 1.0


def _compute_round2_scores(
    candidates: List[str],
    fundamentals: List[Dict[str, Any]],
    quotes: List[Dict[str, Any]],
    news_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    fundamentals_map = {str(x.get("symbol", "")).upper(): x for x in fundamentals if isinstance(x, dict)}
    quote_map = {str(x.get("symbol", "")).upper().split(":")[-1]: x for x in quotes if isinstance(x, dict)}
    news_rank_map = {str(x.get("ticker", "")).upper(): x for x in [_compute_news_rank(item) for item in news_items]}

    scored: List[Dict[str, Any]] = []
    for symbol in candidates:
        s = str(symbol).upper()
        block = fundamentals_map.get(s, {})
        overview = block.get("company_overview", {}) if isinstance(block, dict) else {}
        quarterly = block.get("quarterly_key_financials", []) if isinstance(block, dict) else []
        quote = quote_map.get(s, {})
        news_rank = news_rank_map.get(s, {})

        roe = _to_float(overview.get("roe_ttm"))
        profit_margin = _to_float(overview.get("profit_margin"))
        rev_growth = _latest_quarter_growth(quarterly, "revenue")
        fcf_growth = _latest_quarter_growth(quarterly, "free_cashflow")
        rec_all = _to_float((quote.get("technical") or {}).get("recommend_all")) if isinstance(quote, dict) else None
        momentum = _to_float(news_rank.get("momentum_score"))

        fundamental_score = (
            0.35 * _to_ratio_01(roe, 0.0, 0.25)
            + 0.25 * _to_ratio_01(profit_margin, 0.0, 0.30)
            + 0.20 * _to_ratio_01(rev_growth, -0.20, 0.50)
            + 0.20 * _to_ratio_01(fcf_growth, -0.50, 1.00)
        )
        technical_score = _to_ratio_01(rec_all, -1.0, 1.0)
        news_score = _to_ratio_01(momentum, -0.30, 0.30)
        composite = 0.50 * fundamental_score + 0.30 * technical_score + 0.20 * news_score

        scored.append(
            {
                "symbol": s,
                "score": round(composite, 6),
                "fundamental_score": round(fundamental_score, 6),
                "technical_score": round(technical_score, 6),
                "news_score": round(news_score, 6),
                "inputs": {
                    "roe_ttm": roe,
                    "profit_margin": profit_margin,
                    "revenue_growth_qoq": rev_growth,
                    "fcf_growth_qoq": fcf_growth,
                    "recommend_all": rec_all,
                    "momentum_score": momentum,
                },
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def _extract_polymarket_market_signal(polymarket_text: str) -> Optional[float]:
    if not polymarket_text:
        return None
    signals: List[float] = []
    # 简单抽取：S&P500/NASDAQ 当日上涨概率
    patterns = [
        r"S&P 500.*?\|\s*Yes:\s*([0-9]+(?:\.[0-9]+)?)%",
        r"NASDAQ.*?\|\s*Yes:\s*([0-9]+(?:\.[0-9]+)?)%",
    ]
    for pat in patterns:
        m = re.search(pat, polymarket_text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            yes_prob = float(m.group(1)) / 100.0
            # 概率映射到 [-1, 1]
            signals.append((yes_prob - 0.5) * 2.0)
    if not signals:
        return None
    return sum(signals) / len(signals)


def _extract_benchmark_signal(news_items: List[Dict[str, Any]], benchmark_tickers: List[str]) -> Optional[float]:
    values: List[float] = []
    targets = {t.upper() for t in benchmark_tickers}
    for item in news_items:
        if str(item.get("ticker", "")).upper() not in targets:
            continue
        v = _to_float(item.get("avg_ticker_sentiment_score"))
        if v is None:
            v = _to_float(item.get("avg_overall_sentiment_score"))
        if v is not None:
            values.append(v)
    if not values:
        return None
    return sum(values) / len(values)


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _normalize_symbol(symbol: Any) -> str:
    raw = str(symbol or "").upper().strip()
    return raw.split(":")[-1] if raw else ""


def main() -> None:
    config = load_config()
    strategy_config = get_strategy_config(config)
    risk_config = get_risk_config(config)

    parser = argparse.ArgumentParser(description="运行 Alpaca 分析+交易一体化流程")
    parser.add_argument(
        "--tickers",
        type=str,
        default="",
        help="股票列表，逗号分隔；为空时默认 NASDAQ100+QQQ 共101只",
    )
    parser.add_argument("--days", type=int, default=365, help="基本面回看天数，默认365")
    parser.add_argument("--news-limit", type=int, default=5, help="每只股票新闻条数，默认5")
    parser.add_argument("--prefilter-top-k", type=int, default=10, help="第一阶段新闻筛选后保留数量，默认10")
    parser.add_argument(
        "--benchmark-tickers",
        type=str,
        default="QQQ,SPY",
        help="第二阶段市场门控基准代码，默认 QQQ,SPY",
    )
    parser.add_argument(
        "--market-gate-threshold",
        type=float,
        default=-0.05,
        help="市场门控阈值，低于该值不执行交易，默认 -0.05",
    )
    parser.add_argument(
        "--av-calls-per-minute",
        type=float,
        default=75.0,
        help="AlphaVantage 限速，默认 75 次/分钟",
    )
    parser.add_argument(
        "--trade-plan-file",
        type=str,
        default="",
        help="交易计划 JSON 文件路径（列表格式: [{action,symbol,qty}, ...]）",
    )
    parser.add_argument(
        "--execute-trades",
        action="store_true",
        help="是否实际执行交易（未开启仅分析不交易）",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="skills/alpaca-live-trading/data/analysis_pipeline_latest.json",
        help="输出分析结果 JSON 文件",
    )
    args = parser.parse_args()

    tickers = (
        [s.strip().upper() for s in args.tickers.split(",") if s.strip()]
        if args.tickers
        else DEFAULT_SYMBOLS.copy()
    )
    if not tickers:
        print("❌ 股票列表为空")
        raise SystemExit(1)

    interval = 60.0 / max(args.av_calls_per_minute, 1.0)
    print(f"🚀 启动流程，股票数: {len(tickers)}，AlphaVantage 节流: {interval:.3f}s/次")

    # 0) 读取已有状态
    data_dir = SCRIPT_DIR.parent / "data"
    position_path = data_dir / "position" / "position.jsonl"
    balance_path = data_dir / "balance" / "balance.jsonl"
    old_positions = _read_jsonl(position_path)
    old_balances = _read_jsonl(balance_path)

    # 第一阶段：基于策略进行预筛选（默认 w_bottom_breakout）
    selected_strategy = str(strategy_config.get("name", "")).strip().lower()
    top_k = int(strategy_config.get("prefilter_top_k") or args.prefilter_top_k or 10)
    top_k = max(top_k, 1)

    print(f"🧠 第一阶段：策略预筛选（strategy={selected_strategy or 'N/A'}，Top{top_k}）...")
    snapshot = _load_market_snapshot()
    prefilter_quotes: List[Dict[str, Any]] = [get_quote(ticker, snapshot) for ticker in tickers]
    prefilter_context = {
        "universe_tickers": tickers,
        "quotes": prefilter_quotes,
        "history_db_path": str(SCRIPT_DIR.parent / "data" / "stock_daily.sqlite"),
        "history_lookback_days": 420,
        "strategy_prefilter_top_k": top_k,
    }
    round1_decisions: Dict[str, Any] = {}
    round1_candidates_signals: List[Dict[str, Any]] = []
    if strategy_config.get("enabled") and selected_strategy:
        round1_decisions = run_strategies(
            strategy_names=[selected_strategy],
            context=prefilter_context,
            min_confidence=strategy_config.get("min_confidence", 0.6),
        )
        round1_candidates_signals = round1_decisions.get("signals_accepted", []) or []
        if not round1_candidates_signals:
            round1_candidates_signals = (round1_decisions.get("signals_all", []) or [])[:top_k]

    round1_candidates = [_normalize_symbol(item.get("symbol")) for item in round1_candidates_signals if item.get("symbol")]
    round1_candidates = _dedupe_keep_order([x for x in round1_candidates if x])[:top_k]
    print(f"✅ 第一阶段完成，候选数: {len(round1_candidates)}，候选: {round1_candidates}")

    benchmark_tickers = [x.strip().upper() for x in args.benchmark_tickers.split(",") if x.strip()]
    deep_universe = _dedupe_keep_order(round1_candidates + benchmark_tickers)
    print(f"🔎 第二阶段深度分析标的数: {len(deep_universe)}")

    # 第二阶段：深度分析（策略候选 + 基准ETF）
    print("📰 第二阶段：候选标的 + 基准ETF 新闻情绪...")
    deep_news = fetch_news_per_ticker(
        tickers=deep_universe,
        per_ticker_limit=max(1, args.news_limit),
        sort="LATEST",
        request_interval=interval,
    )

    print("📚 第二阶段：基本面...")
    fundamentals: List[Dict[str, Any]] = []
    for idx, ticker in enumerate(deep_universe, 1):
        print(f"[{idx}/{len(deep_universe)}] 基本面: {ticker}")
        try:
            fundamentals.append(
                fetch_fundamentals_for_symbol(
                    ticker,
                    days=args.days,
                    endpoint_request_interval=interval,
                )
            )
        except Exception as e:
            fundamentals.append({"symbol": ticker, "error": str(e)})

    # Polymarket 市场赔率
    print("📊 获取 Polymarket 赔率...")
    try:
        polymarket = get_financial_sentiment()
    except Exception as e:
        polymarket = f"ERROR: {e}"

    # tvscreener 价格 + 技术面
    print("📈 第二阶段：tvscreener 价格与技术面...")
    quotes: List[Dict[str, Any]] = []
    for ticker in deep_universe:
        quotes.append(get_quote(ticker, snapshot))

    _, deep_news_ranking = _select_top_by_news(deep_news, top_k=max(len(round1_candidates), 1))
    round2_scores = _compute_round2_scores(
        candidates=round1_candidates,
        fundamentals=fundamentals,
        quotes=quotes,
        news_items=deep_news,
    )

    benchmark_news_signal = _extract_benchmark_signal(deep_news, benchmark_tickers)
    polymarket_signal = _extract_polymarket_market_signal(polymarket if isinstance(polymarket, str) else "")
    signal_values = [v for v in [benchmark_news_signal, polymarket_signal] if v is not None]
    market_gate_score = sum(signal_values) / len(signal_values) if signal_values else None
    should_trade_by_market = market_gate_score is not None and market_gate_score >= args.market_gate_threshold
    if market_gate_score is None:
        # 没有市场信号时，保守放行，避免策略完全停摆
        should_trade_by_market = True

    # 可选交易执行（受市场门控）
    trade_results: List[Dict[str, Any]] = []
    trade_plan: List[Dict[str, Any]] = []
    strategy_decisions: Dict[str, Any] = {}
    generated_trade_plan: List[Dict[str, Any]] = []
    risk_rejections: List[Dict[str, Any]] = []
    account_snapshot = _extract_latest_account_snapshot(old_balances)
    positions_snapshot = _extract_latest_positions_snapshot(old_balances)

    if strategy_config.get("enabled"):
        strategy_decisions = dict(round1_decisions or {})
        round2_score_map = {item["symbol"]: item for item in round2_scores}
        round2_pass_symbols = [item["symbol"] for item in round2_scores if item.get("score", 0.0) >= 0.4]
        if not round2_pass_symbols:
            round2_pass_symbols = [item["symbol"] for item in round2_scores[:top_k]]
        round2_pass_symbols = _dedupe_keep_order(round2_pass_symbols)[:top_k]

        source_signals = strategy_decisions.get("signals_accepted", []) or strategy_decisions.get("signals_all", []) or []
        filtered_signals: List[Dict[str, Any]] = []
        for signal in source_signals:
            symbol = _normalize_symbol(signal.get("symbol"))
            if not symbol or symbol not in round2_pass_symbols:
                continue
            row = round2_score_map.get(symbol, {})
            base_conf = _to_float(signal.get("confidence")) or 0.0
            round2_conf = _to_float(row.get("score")) or 0.0
            enriched = dict(signal)
            enriched["confidence"] = max(0.0, min(0.95, 0.7 * base_conf + 0.3 * round2_conf))
            md = dict(enriched.get("metadata") or {})
            md["round2_score"] = row.get("score")
            md["round2_components"] = {
                "fundamental_score": row.get("fundamental_score"),
                "technical_score": row.get("technical_score"),
                "news_score": row.get("news_score"),
            }
            enriched["metadata"] = md
            filtered_signals.append(enriched)

        strategy_decisions["selected_strategy"] = selected_strategy
        strategy_decisions["round1_candidates"] = round1_candidates
        strategy_decisions["round2_scores"] = round2_scores
        strategy_decisions["round2_pass_symbols"] = round2_pass_symbols
        strategy_decisions["signals_after_round2"] = filtered_signals

        build_result = build_trade_plan(
            signals=filtered_signals,
            risk_config=risk_config,
            account_snapshot=account_snapshot,
            positions_snapshot=positions_snapshot,
        )
        generated_trade_plan = build_result.get("trade_plan", [])
        strategy_decisions["order_build"] = {
            "skipped_signals": build_result.get("skipped_signals", []),
            "assumptions": build_result.get("assumptions", {}),
        }

        risk_result = apply_risk_guard(
            trade_plan=generated_trade_plan,
            risk_config=risk_config,
            account_snapshot=account_snapshot,
            positions_snapshot=positions_snapshot,
        )
        generated_trade_plan = risk_result.get("accepted_plan", [])
        risk_rejections = risk_result.get("rejections", [])
        strategy_decisions["risk_guard"] = risk_result.get("risk_snapshot", {})

    if args.trade_plan_file:
        plan_path = Path(args.trade_plan_file)
        if plan_path.exists():
            try:
                trade_plan = json.loads(plan_path.read_text(encoding="utf-8"))
                if not isinstance(trade_plan, list):
                    raise ValueError("交易计划文件必须是 JSON 列表")
            except Exception as e:
                print(f"⚠️ 读取交易计划失败: {e}")
                trade_plan = []
        else:
            print(f"⚠️ 交易计划文件不存在: {plan_path}")
    else:
        trade_plan = generated_trade_plan

    if strategy_config.get("enabled") and not args.trade_plan_file:
        print(f"🧠 策略自动生成交易计划: {len(trade_plan)} 条")

    if args.execute_trades and trade_plan and should_trade_by_market:
        print(f"🧾 执行交易计划，共 {len(trade_plan)} 条...")
        trade_results = _execute_trade_plan(trade_plan)
    elif args.execute_trades and trade_plan and not should_trade_by_market:
        print("🛑 市场门控未通过，跳过执行交易。")
        trade_results = [{"status": "blocked_by_market_gate", "market_gate_score": market_gate_score}]
    elif args.execute_trades:
        print("⚠️ 已指定执行交易，但交易计划为空，跳过执行。")

    # 6) 读取交易后状态
    new_positions = _read_jsonl(position_path)
    new_balances = _read_jsonl(balance_path)

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tickers_count": len(tickers),
        "tickers": tickers,
        "pipeline": {
            "stage1_prefilter": {
                "input_universe_size": len(tickers),
                "strategy": selected_strategy,
                "top_k": top_k,
                "candidates": round1_candidates,
                "strategy_decisions": round1_decisions,
            },
            "stage2_deep_analysis": {
                "benchmark_tickers": benchmark_tickers,
                "deep_universe": deep_universe,
                "deep_universe_size": len(deep_universe),
                "round2_scores": round2_scores,
                "deep_news_ranking": deep_news_ranking,
            },
            "market_gate": {
                "benchmark_news_signal": benchmark_news_signal,
                "polymarket_signal": polymarket_signal,
                "market_gate_score": market_gate_score,
                "threshold": args.market_gate_threshold,
                "should_trade": should_trade_by_market,
            },
        },
        "alpha_vantage": {
            "calls_per_minute": args.av_calls_per_minute,
            "request_interval_seconds": interval,
            "fundamentals": fundamentals,
            "news_sentiment_stage2": deep_news,
        },
        "polymarket_sentiment": polymarket,
        "tvscreener": {
            "quotes": quotes,
        },
        "state_before": {
            "position_path": str(position_path),
            "balance_path": str(balance_path),
            "position_tail": _tail_rows(old_positions, 5),
            "balance_tail": _tail_rows(old_balances, 5),
        },
        "trade_execution": {
            "enabled": bool(args.execute_trades),
            "config_strategy_enabled": bool(strategy_config.get("enabled")),
            "strategy_config": strategy_config,
            "risk_config": risk_config,
            "trade_plan_source": "manual_file" if args.trade_plan_file else ("strategy_auto" if strategy_config.get("enabled") else "none"),
            "trade_plan": trade_plan,
            "generated_trade_plan": generated_trade_plan,
            "strategy_decisions": strategy_decisions,
            "risk_rejections": risk_rejections,
            "results": trade_results,
        },
        "state_after": {
            "position_tail": _tail_rows(new_positions, 5),
            "balance_tail": _tail_rows(new_balances, 5),
        },
    }

    out_path = Path(args.output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 流程完成，结果已写入: {out_path}")


if __name__ == "__main__":
    main()
