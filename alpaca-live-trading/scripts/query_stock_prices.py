#!/usr/bin/env python3
"""
查询股票实时价格 - 通过 TradingView tvscreener

用法:
    python query_stock_prices.py                    # 查询 NASDAQ 100 热门股票
    python query_stock_prices.py AAPL MSFT NVDA    # 查询指定股票
"""

import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
# 将 scripts 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

# tvscreener 导入
try:
    from tvscreener import Market, StockField, StockScreener
    TVSCREENER_AVAILABLE = True
except ImportError:
    TVSCREENER_AVAILABLE = False
    print("⚠️ tvscreener 未安装，请运行: pip install -U tvscreener")

# 默认查询: NASDAQ 100 + QQQ (共 101)
DEFAULT_SYMBOLS = [
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
    "QQQ"
]


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _load_market_snapshot() -> Any:
    """
    拉取美国市场行情快照，用于本地筛选。
    """
    if not TVSCREENER_AVAILABLE:
        return None

    ss = StockScreener()
    ss.set_markets(Market.AMERICA)
    ss.set_range(0, 5000)
    ss.select(
        StockField.NAME,
        StockField.PRICE,
        StockField.CHANGE_PERCENT,
        StockField.VOLUME,
    )
    return ss.get()


def get_quote(symbol: str, snapshot) -> Dict[str, Any]:
    """
    获取股票的实时报价（TradingView tvscreener）

    Args:
        symbol: 股票代码（例如 NVDA 或 NASDAQ:NVDA）
        snapshot: tvscreener DataFrame

    Returns:
        包含报价信息的字典
    """
    if snapshot is None:
        return {"error": "tvscreener 未就绪"}

    token = symbol.split(":")[-1]
    row = snapshot[snapshot["Symbol"] == symbol]
    if row.empty and "Name" in snapshot.columns:
        row = snapshot[snapshot["Name"].astype(str) == token]

    if row.empty:
        return {"error": "无数据"}

    payload = row.iloc[0].to_dict()
    price = float(payload.get("Price") or 0)
    change_pct = float(payload.get("Change %") or 0)
    change = price * change_pct / 100 if price else 0.0

    return {
        "symbol": payload.get("Symbol") or symbol,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "volume": float(payload.get("Volume") or 0),
    }


def write_latest_snapshot(results: List[Dict[str, Any]], symbols: List[str]) -> None:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "stock_prices_latest.json"
    payload = {
        "source": "tvscreener",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbols": symbols,
        "results": results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    """主函数"""
    # 解析命令行参数
    symbols = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SYMBOLS
    
    print("📈 股票实时价格查询")
    print("=" * 50)
    print(f"数据来源: TradingView tvscreener")
    print(f"查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"查询股票: {', '.join(symbols)}")
    print("=" * 50)
    
    if not TVSCREENER_AVAILABLE:
        sys.exit(1)
    
    print("\n获取报价数据...\n")
    
    results = []
    snapshot = _load_market_snapshot()
    for symbol in symbols:
        print(f"  获取 {symbol}...", end=" ")
        result = get_quote(symbol, snapshot)
        if "error" in result:
            print(f"❌ {result['error']}")
        else:
            print("✓")
            results.append(result)
    
    if results:
        print("\n" + "=" * 50)
        print("📊 股票价格汇总")
        print("=" * 50)
        print(f"{'股票':<8} {'当前价格':>12} {'涨跌':>10} {'涨跌幅':>10}")
        print("-" * 50)
        
        for r in results:
            change_str = f"{r['change']:+.2f}" if r.get("change") is not None else "N/A"
            pct_str = f"{float(r['change_pct']):+.2f}%" if r.get("change_pct") is not None else "N/A"
            print(f"{r['symbol']:<8} ${r['price']:>10.2f} {change_str:>10} {pct_str:>10}")

    write_latest_snapshot(results, symbols)
    print("\n💾 已更新最新股价文件: skills/alpaca-live-trading/data/stock_prices_latest.json")


if __name__ == "__main__":
    main()
