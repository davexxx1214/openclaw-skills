#!/usr/bin/env python3
"""
执行 Alpaca 交易并同步本地记录。

功能：
1. 提交 buy/sell 市价单
2. 成交后重新查询 Alpaca 账户与持仓（真实状态）
3. 更新 position.jsonl
4. 更新 balance.jsonl（含账户总览 + 持仓明细）

用法:
    python skills/alpaca-live-trading/scripts/execute_alpaca_trade.py --action buy --symbol AAPL --qty 1
    python skills/alpaca-live-trading/scripts/execute_alpaca_trade.py --action sell --symbol AAPL --qty 1
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from _config import get_alpaca_credentials, load_config

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest
except ImportError:
    print("❌ 缺少 alpaca-py，请安装: pip install alpaca-py")
    raise SystemExit(1)


DEFAULT_POSITION_SYMBOLS = [
    "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "NFLX",
    "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN", "PEP",
    "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC", "BKNG",
    "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON", "CRWD", "CEG",
    "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX", "CDNS", "ORLY", "SNPS",
    "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI", "MAR", "MNST", "CSX", "ADSK",
    "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP", "NXPI", "DDOG", "AXON", "ROST",
    "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO", "XEL", "ZS", "PAYX", "WBD",
    "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR", "KDP", "MCHP", "GEHC", "VRSK",
    "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD", "ON", "BIIB", "LULU", "CDW", "GFS",
    "QQQ",
]

def resolve_skill_data_dir() -> Path:
    # skills/alpaca-live-trading/scripts -> skills/alpaca-live-trading/data
    return Path(__file__).resolve().parent.parent / "data"


def normalize_positions(raw_positions: Dict[str, Any]) -> Dict[str, Any]:
    out = {symbol: 0 for symbol in DEFAULT_POSITION_SYMBOLS}
    for symbol, qty in raw_positions.items():
        if symbol == "CASH":
            continue
        out[symbol] = int(float(qty))
    out["CASH"] = float(raw_positions.get("CASH", 0.0))
    return out


def get_next_id(jsonl_path: Path) -> int:
    if not jsonl_path.exists():
        return 0
    current = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                current = max(current, int(row.get("id", 0)))
            except Exception:
                continue
    return current


def append_jsonl(jsonl_path: Path, row: Dict[str, Any]) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_positions_from_alpaca(account, positions) -> Dict[str, Any]:
    raw = {"CASH": float(account.cash)}
    for pos in positions:
        raw[pos.symbol] = int(float(pos.qty))
    return normalize_positions(raw)


def build_positions_details(positions) -> List[Dict[str, Any]]:
    details = []
    for pos in positions:
        details.append(
            {
                "symbol": pos.symbol,
                "qty": float(pos.qty),
                "filled_price": float(pos.avg_entry_price),  # 当前持仓口径下的成交均价（成本）
                "avg_entry_price": float(pos.avg_entry_price),
                "current_price": float(pos.current_price),
                "market_value": float(pos.market_value),
                "unrealized_pl": float(pos.unrealized_pl),
                "unrealized_plpc": float(pos.unrealized_plpc),
                "side": pos.side.value if hasattr(pos.side, "value") else str(pos.side),
            }
        )
    return details


def main() -> None:
    parser = argparse.ArgumentParser(description="执行 Alpaca 交易并更新 position/balance")
    parser.add_argument("--action", required=True, choices=["buy", "sell"], help="交易动作")
    parser.add_argument("--symbol", required=True, help="股票代码，如 AAPL")
    parser.add_argument("--qty", required=True, type=int, help="交易股数，正整数")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if args.qty <= 0:
        print("❌ qty 必须为正整数")
        raise SystemExit(1)

    config = load_config()
    api_key, secret_key, paper = get_alpaca_credentials(config)

    client = TradingClient(api_key, secret_key, paper=paper)
    symbol = args.symbol.upper()
    side = OrderSide.BUY if args.action == "buy" else OrderSide.SELL

    order = client.submit_order(
        order_data=MarketOrderRequest(
            symbol=symbol,
            qty=args.qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
    )

    filled_price = None
    for _ in range(15):
        time.sleep(1)
        order = client.get_order_by_id(order.id)
        status = order.status.value if hasattr(order.status, "value") else str(order.status)
        if status in {"filled", "partially_filled"}:
            filled_price = float(order.filled_avg_price) if order.filled_avg_price else None
            break
        if status in {"canceled", "expired", "rejected"}:
            print(f"❌ 订单失败: {status}")
            raise SystemExit(1)

    if not filled_price:
        print("⏳ 订单已提交但尚未成交，请稍后查询账户状态。")
        raise SystemExit(0)

    # 每笔交易后重新查询 Alpaca 实际账户和持仓（作为唯一真实来源）
    account = client.get_account()
    positions = client.get_all_positions()
    normalized_positions = build_positions_from_alpaca(account, positions)
    positions_details = build_positions_details(positions)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base_dir = resolve_skill_data_dir()
    position_file = base_dir / "position" / "position.jsonl"
    balance_file = base_dir / "balance" / "balance.jsonl"

    next_id = get_next_id(position_file) + 1
    append_jsonl(
        position_file,
        {
            "date": now,
            "id": next_id,
            "this_action": {
                "action": args.action,
                "symbol": symbol,
                "amount": args.qty,
                "price": filled_price,
                "source": "alpaca-skill",
                "order_id": str(order.id),
            },
            "positions": normalized_positions,
        },
    )

    append_jsonl(
        balance_file,
        {
            "date": now,
            "trade": {
                "action": args.action,
                "symbol": symbol,
                "qty": args.qty,
                "filled_price": filled_price,
                "order_id": str(order.id),
            },
            "account": {
                "account_number": account.account_number,
                "status": account.status.value if hasattr(account.status, "value") else str(account.status),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "equity": float(account.equity),
                "last_equity": float(account.last_equity),
                "long_market_value": float(account.long_market_value),
                "short_market_value": float(account.short_market_value),
                "initial_margin": float(account.initial_margin),
                "maintenance_margin": float(account.maintenance_margin),
                "daytrade_count": account.daytrade_count,
                "pattern_day_trader": account.pattern_day_trader,
            },
            "positions": positions_details,
        },
    )

    result = {
        "status": "filled",
        "action": args.action,
        "symbol": symbol,
        "qty": args.qty,
        "filled_price": filled_price,
        "order_id": str(order.id),
        "paper": bool(paper),
        "position_file": str(position_file),
        "balance_file": str(balance_file),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        mode = "Paper Trading" if paper else "Live Trading"
        print(f"✅ 交易成功 ({mode})")
        print(f"  动作: {args.action.upper()} {symbol} x {args.qty}")
        print(f"  成交价: ${filled_price:.2f}")
        print(f"  订单号: {order.id}")
        print(f"  position: {position_file}")
        print(f"  balance: {balance_file}")


if __name__ == "__main__":
    main()
