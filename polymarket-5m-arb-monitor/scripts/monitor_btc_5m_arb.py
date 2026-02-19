#!/usr/bin/env python3
"""
监控 Polymarket 5分钟 BTC 方向盘，并结合 Alpaca 现货分钟线寻找套利窗口。

核心逻辑：
1. 每轮获取 "Bitcoin Up or Down - 5 min" 的 Up/Down 概率
2. 使用 Alpaca BTCUSD 分钟线估计未来 5 分钟上涨概率
3. 扣除手续费阈值（默认 0.15%）后，输出是否存在正边际机会
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.data.historical.crypto import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame
except ImportError:
    print("❌ 缺少 alpaca-py，请安装: pip install alpaca-py")
    raise SystemExit(1)


GAMMA_BASE_URL = "https://gamma-api.polymarket.com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="监控 Polymarket BTC 5分钟盘，检测手续费后套利空间"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.yaml",
        help="配置文件路径（默认: polymarket-5m-arb-monitor/config.yaml）",
    )
    parser.add_argument(
        "--symbol",
        default="BTC/USD",
        help="Alpaca Crypto symbol，默认 BTC/USD",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=30,
        help="轮询间隔秒数，默认 30",
    )
    parser.add_argument(
        "--polls",
        type=int,
        default=0,
        help="轮询次数，0 表示无限循环",
    )
    parser.add_argument(
        "--fee-rate",
        type=float,
        default=0.0015,
        help="手续费门槛（小数），默认 0.0015 即 0.15%%",
    )
    parser.add_argument(
        "--history-bars",
        type=int,
        default=300,
        help="Alpaca 分钟线回看条数，默认 300",
    )
    parser.add_argument(
        "--neighbors",
        type=int,
        default=80,
        help="KNN 近邻数量，用于估计未来5分钟上涨概率",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出每一轮结果",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "arb_monitor.jsonl",
        help="每轮结果落盘路径（jsonl）",
    )
    parser.add_argument(
        "--auto-trade",
        action="store_true",
        help="发现 ARBITRAGE 信号时自动下单",
    )
    parser.add_argument(
        "--trade-notional-usd",
        type=float,
        default=100.0,
        help="自动交易单笔名义金额（USD），默认 100",
    )
    parser.add_argument(
        "--trade-cooldown-seconds",
        type=int,
        default=300,
        help="自动交易冷却秒数，默认 300",
    )
    parser.add_argument(
        "--pid-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "monitor.pid",
        help="监控进程 PID 文件路径",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="停止正在运行的监控进程（通过 pid-file）",
    )
    return parser.parse_args()


def load_alpaca_credentials(config_path: Path) -> Tuple[str, str, bool]:
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        raise SystemExit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    alpaca = cfg.get("alpaca", {})
    api_key = alpaca.get("api_key", "")
    secret_key = alpaca.get("secret_key", "")
    paper = bool(alpaca.get("paper", True))
    if not api_key or not secret_key:
        print(f"❌ 配置缺少 alpaca.api_key / alpaca.secret_key: {config_path}")
        raise SystemExit(1)
    return api_key, secret_key, paper


def decode_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []
    return []


def fetch_polymarket_target_market(session: requests.Session) -> Dict[str, Any]:
    params = {
        "closed": "false",
        "limit": 200,
        "tag_slug": "5m",
        "order": "volume24hr",
        "ascending": "false",
    }
    resp = session.get(f"{GAMMA_BASE_URL}/events", params=params, timeout=20)
    resp.raise_for_status()
    events = resp.json()

    candidates: List[Dict[str, Any]] = []
    for event in events:
        event_title = str(event.get("title") or "").strip()
        event_low = event_title.lower()
        event_is_target = "bitcoin up or down" in event_low
        markets = event.get("markets", [])
        for market in markets:
            title = str(market.get("question") or market.get("title") or event_title).strip()
            low = title.lower()
            if "bitcoin up or down" in low or event_is_target:
                m = dict(market)
                m["event_title"] = event_title
                m["event_slug"] = event.get("slug", "")
                candidates.append(m)

    if not candidates:
        raise RuntimeError("未找到 'Bitcoin Up or Down - 5 min' 相关盘口")

    def vol_key(m: Dict[str, Any]) -> float:
        for key in ("volume24hr", "volume", "volumeNum"):
            try:
                return float(m.get(key) or 0)
            except Exception:
                continue
        return 0.0

    candidates.sort(key=vol_key, reverse=True)
    return candidates[0]


def extract_up_down_prob(market: Dict[str, Any]) -> Tuple[float, float]:
    outcomes = [str(x).strip().lower() for x in decode_list(market.get("outcomes"))]
    prices_raw = decode_list(market.get("outcomePrices"))
    prices: List[float] = []
    for x in prices_raw:
        try:
            prices.append(float(x))
        except Exception:
            prices.append(0.0)

    if len(prices) < 2:
        raise RuntimeError("盘口缺少有效 outcomePrices")

    up_idx = None
    down_idx = None
    for i, label in enumerate(outcomes):
        if label in {"up", "yes"} and up_idx is None:
            up_idx = i
        if label in {"down", "no"} and down_idx is None:
            down_idx = i

    if up_idx is None:
        up_idx = 0
    if down_idx is None:
        down_idx = 1 if up_idx == 0 else 0

    up_prob = max(0.0, min(1.0, prices[up_idx]))
    down_prob = max(0.0, min(1.0, prices[down_idx]))
    return up_prob, down_prob


def fetch_alpaca_closes(
    client: CryptoHistoricalDataClient,
    symbol: str,
    limit: int,
) -> List[float]:
    req = CryptoBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        limit=limit,
    )
    bars = client.get_crypto_bars(req).df
    if bars is None or bars.empty:
        raise RuntimeError("Alpaca 返回空分钟线")

    # 兼容多层索引与单层索引
    if "close" in bars.columns:
        close_series = bars["close"]
    else:
        raise RuntimeError("Alpaca 分钟线缺少 close 字段")

    closes = [float(x) for x in close_series.tolist() if x is not None]
    if len(closes) < 30:
        raise RuntimeError(f"分钟线数量不足: {len(closes)}")
    return closes


def estimate_up_probability_knn(
    closes: List[float],
    neighbors: int = 80,
) -> Tuple[float, Dict[str, float]]:
    # feature: 过去5分钟收益; target: 未来5分钟是否上涨
    features: List[float] = []
    targets: List[int] = []

    for t in range(5, len(closes) - 5):
        prev = closes[t - 5]
        cur = closes[t]
        nxt = closes[t + 5]
        if prev <= 0 or cur <= 0:
            continue
        f = (cur / prev) - 1.0
        y = 1 if (nxt / cur) - 1.0 > 0 else 0
        features.append(f)
        targets.append(y)

    if len(features) < 50:
        return 0.5, {
            "sample_count": float(len(features)),
            "current_5m_ret": 0.0,
            "uncond_up_prob": 0.5,
        }

    cur_ret = (closes[-1] / closes[-6]) - 1.0
    pairs = list(zip(features, targets))
    pairs.sort(key=lambda p: abs(p[0] - cur_ret))

    k = max(10, min(neighbors, len(pairs)))
    nearest = pairs[:k]
    cond_prob = sum(y for _, y in nearest) / float(k)
    uncond_prob = sum(targets) / float(len(targets))

    # 70% 条件概率 + 30% 无条件概率，降低过拟合抖动
    blended = 0.7 * cond_prob + 0.3 * uncond_prob
    blended = max(0.01, min(0.99, blended))

    return blended, {
        "sample_count": float(len(features)),
        "current_5m_ret": cur_ret,
        "uncond_up_prob": uncond_prob,
    }


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        out = (proc.stdout or "").lower()
        return str(pid) in out and "no tasks are running" not in out
    except Exception:
        return False


def read_pid(pid_file: Path) -> Optional[int]:
    if not pid_file.exists():
        return None
    try:
        raw = pid_file.read_text(encoding="utf-8").strip()
        return int(raw)
    except Exception:
        return None


def write_pid(pid_file: Path, pid: int) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid), encoding="utf-8")


def remove_pid_file(pid_file: Path) -> None:
    try:
        if pid_file.exists():
            pid_file.unlink()
    except Exception:
        pass


def stop_monitor(pid_file: Path) -> int:
    pid = read_pid(pid_file)
    if pid is None:
        print(f"⚠️ 未找到监控 PID 文件: {pid_file}")
        return 1
    if not process_exists(pid):
        print(f"⚠️ PID {pid} 不在运行，已清理 pid 文件")
        remove_pid_file(pid_file)
        return 1

    try:
        proc = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as e:
        print(f"❌ 停止失败: {e}")
        return 1

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        msg = stderr or stdout or "未知错误"
        print(f"❌ 停止失败: {msg}")
        return 1

    for _ in range(20):
        time.sleep(0.1)
        if not process_exists(pid):
            remove_pid_file(pid_file)
            print(f"✅ 已停止监控进程 PID={pid}")
            return 0

    print(f"⚠️ 已发送停止信号，但进程仍在运行 PID={pid}")
    return 1


def normalize_trading_symbol(data_symbol: str) -> str:
    return data_symbol.replace("/", "").upper()


def get_crypto_position_qty(trading_client: TradingClient, symbol: str) -> float:
    target = symbol.upper()
    for pos in trading_client.get_all_positions():
        pos_symbol = str(getattr(pos, "symbol", "")).upper()
        if pos_symbol == target:
            try:
                return float(pos.qty)
            except Exception:
                return 0.0
    return 0.0


def maybe_auto_trade(
    result: Dict[str, Any],
    trading_client: TradingClient,
    trading_symbol: str,
    trade_notional_usd: float,
    last_trade_ts: Optional[float],
    cooldown_seconds: int,
) -> Dict[str, Any]:
    now_ts = time.time()
    out: Dict[str, Any] = {
        "enabled": True,
        "executed": False,
        "reason": "",
        "order_id": None,
        "side": None,
        "notional_usd": trade_notional_usd,
    }

    if result.get("signal") != "ARBITRAGE":
        out["reason"] = "signal_not_arbitrage"
        return out

    if last_trade_ts is not None and (now_ts - last_trade_ts) < cooldown_seconds:
        out["reason"] = "cooldown"
        out["cooldown_left_seconds"] = max(0.0, cooldown_seconds - (now_ts - last_trade_ts))
        return out

    best_side = result.get("best_side")
    if best_side not in {"UP", "DOWN"}:
        out["reason"] = "invalid_best_side"
        return out

    try:
        if best_side == "UP":
            order = trading_client.submit_order(
                order_data=MarketOrderRequest(
                    symbol=trading_symbol,
                    notional=trade_notional_usd,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.GTC,
                )
            )
            out["executed"] = True
            out["side"] = "buy"
            out["order_id"] = str(order.id)
            out["reason"] = "submitted"
            return out

        # DOWN: 优先卖出现有 BTC 持仓；若无持仓则跳过，避免报错
        spot = float(result.get("alpaca_spot_price") or 0.0)
        if spot <= 0:
            out["reason"] = "invalid_spot_price"
            return out
        qty_to_sell = trade_notional_usd / spot
        current_qty = get_crypto_position_qty(trading_client, trading_symbol)
        if current_qty <= 0:
            out["reason"] = "no_position_for_down_signal"
            return out

        qty = min(current_qty, qty_to_sell)
        if qty <= 0:
            out["reason"] = "qty_too_small"
            return out

        order = trading_client.submit_order(
            order_data=MarketOrderRequest(
                symbol=trading_symbol,
                qty=round(qty, 6),
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
            )
        )
        out["executed"] = True
        out["side"] = "sell"
        out["order_id"] = str(order.id)
        out["reason"] = "submitted"
        out["sell_qty"] = round(qty, 6)
        return out

    except Exception as e:
        out["reason"] = "submit_failed"
        out["error"] = str(e)
        return out


def build_opportunity(
    market: Dict[str, Any],
    up_prob_pm: float,
    down_prob_pm: float,
    up_prob_model: float,
    spot_price: float,
    fee_rate: float,
    model_meta: Dict[str, float],
    alpaca_symbol: str,
) -> Dict[str, Any]:
    down_prob_model = 1.0 - up_prob_model
    edge_up = up_prob_model - up_prob_pm
    edge_down = down_prob_model - down_prob_pm

    best_side = "UP" if edge_up >= edge_down else "DOWN"
    best_edge = edge_up if best_side == "UP" else edge_down
    signal = "ARBITRAGE" if best_edge > fee_rate else "NO_EDGE"

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signal": signal,
        "best_side": best_side,
        "best_edge": best_edge,
        "fee_rate": fee_rate,
        "pm_market_question": market.get("question") or market.get("title"),
        "pm_market_slug": market.get("slug"),
        "pm_event_slug": market.get("event_slug"),
        "pm_up_prob": up_prob_pm,
        "pm_down_prob": down_prob_pm,
        "model_up_prob": up_prob_model,
        "model_down_prob": down_prob_model,
        "alpaca_symbol": alpaca_symbol,
        "alpaca_spot_price": spot_price,
        "model_meta": model_meta,
    }


def print_human(result: Dict[str, Any]) -> None:
    edge_pct = result["best_edge"] * 100.0
    fee_pct = result["fee_rate"] * 100.0
    mark = "🚨" if result["signal"] == "ARBITRAGE" else "·"
    print(
        f"{mark} {result['timestamp_utc']} | {result['signal']} | "
        f"best={result['best_side']} edge={edge_pct:.3f}% (fee={fee_pct:.3f}%) | "
        f"PM Up={result['pm_up_prob']*100:.2f}% Down={result['pm_down_prob']*100:.2f}% | "
        f"Model Up={result['model_up_prob']*100:.2f}% | Spot={result['alpaca_spot_price']:.2f}"
    )
    auto_trade = result.get("auto_trade")
    if isinstance(auto_trade, dict) and auto_trade.get("enabled"):
        print(
            "    auto_trade: "
            f"executed={auto_trade.get('executed')} "
            f"side={auto_trade.get('side')} "
            f"order_id={auto_trade.get('order_id')} "
            f"reason={auto_trade.get('reason')}"
        )


def main() -> None:
    args = parse_args()

    if args.stop:
        raise SystemExit(stop_monitor(args.pid_file))

    if args.interval_seconds <= 0:
        print("❌ --interval-seconds 必须 > 0")
        raise SystemExit(1)
    if args.fee_rate <= 0:
        print("❌ --fee-rate 必须 > 0")
        raise SystemExit(1)

    api_key, secret_key, paper = load_alpaca_credentials(args.config)
    alpaca_client = CryptoHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    trading_client = TradingClient(api_key, secret_key, paper=paper)
    trading_symbol = normalize_trading_symbol(args.symbol)

    if args.trade_notional_usd <= 0:
        print("❌ --trade-notional-usd 必须 > 0")
        raise SystemExit(1)
    if args.trade_cooldown_seconds < 0:
        print("❌ --trade-cooldown-seconds 不能小于 0")
        raise SystemExit(1)

    existing_pid = read_pid(args.pid_file)
    if existing_pid is not None and process_exists(existing_pid):
        print(f"❌ 监控已在运行，PID={existing_pid}。如需停止请执行: --stop")
        raise SystemExit(1)
    if existing_pid is not None and not process_exists(existing_pid):
        remove_pid_file(args.pid_file)

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "polymarket-5m-arb-monitor/1.0",
        }
    )

    rounds = 0
    last_trade_ts: Optional[float] = None
    write_pid(args.pid_file, os.getpid())
    try:
        while True:
            rounds += 1
            try:
                market = fetch_polymarket_target_market(session)
                up_pm, down_pm = extract_up_down_prob(market)
                closes = fetch_alpaca_closes(alpaca_client, args.symbol, args.history_bars)
                spot = float(closes[-1])
                up_model, meta = estimate_up_probability_knn(closes, args.neighbors)
                result = build_opportunity(
                    market=market,
                    up_prob_pm=up_pm,
                    down_prob_pm=down_pm,
                    up_prob_model=up_model,
                    spot_price=spot,
                    fee_rate=args.fee_rate,
                    model_meta=meta,
                    alpaca_symbol=args.symbol,
                )
                result["paper"] = paper

                if args.auto_trade:
                    auto_trade = maybe_auto_trade(
                        result=result,
                        trading_client=trading_client,
                        trading_symbol=trading_symbol,
                        trade_notional_usd=args.trade_notional_usd,
                        last_trade_ts=last_trade_ts,
                        cooldown_seconds=args.trade_cooldown_seconds,
                    )
                    result["auto_trade"] = auto_trade
                    if auto_trade.get("executed"):
                        last_trade_ts = time.time()

                if args.json:
                    print(json.dumps(result, ensure_ascii=False))
                else:
                    print_human(result)
                append_jsonl(args.output_jsonl, result)

            except KeyboardInterrupt:
                print("\n已停止监控。")
                raise SystemExit(0)
            except Exception as e:
                err = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "signal": "ERROR",
                    "error": str(e),
                }
                if args.json:
                    print(json.dumps(err, ensure_ascii=False))
                else:
                    print(f"⚠️ {err['timestamp_utc']} | ERROR | {e}", file=sys.stderr)
                append_jsonl(args.output_jsonl, err)

            if args.polls > 0 and rounds >= args.polls:
                break
            time.sleep(args.interval_seconds)
    finally:
        remove_pid_file(args.pid_file)


if __name__ == "__main__":
    main()
