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

# 技术面指标字段（按日线）
TECHNICAL_FIELDS = {
    "rsi_14": "RSI_1",
    "macd": "MACD_MACD_1",
    "macd_signal": "MACD_SIGNAL_1",
    "sma20": "SMA20_1",
    "sma50": "SMA50_1",
    "ema20": "EMA20_1",
    "ema50": "EMA50_1",
    "recommend_all": "RECOMMEND_ALL_1",
    "recommend_ma": "RECOMMEND_MA_1",
    "recommend_other": "RECOMMEND_OTHER_1",
}


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _resolve_technical_stock_fields():
    fields = []
    resolved_keys = {}
    for key, field_name in TECHNICAL_FIELDS.items():
        if hasattr(StockField, field_name):
            field_obj = getattr(StockField, field_name)
            fields.append(field_obj)
            raw_value = getattr(field_obj, "value", str(field_obj))
            if isinstance(raw_value, tuple) and raw_value:
                resolved_keys[key] = str(raw_value[0])
            else:
                resolved_keys[key] = str(raw_value)
    return fields, resolved_keys


def _load_market_snapshot() -> Any:
    """
    拉取美国市场行情快照，用于本地筛选。
    """
    if not TVSCREENER_AVAILABLE:
        return None

    ss = StockScreener()
    ss.set_markets(Market.AMERICA)
    ss.set_range(0, 5000)
    tech_fields, _ = _resolve_technical_stock_fields()
    base_fields = [
        StockField.NAME,
        StockField.PRICE,
        StockField.CHANGE_PERCENT,
        StockField.VOLUME,
    ]
    ss.select(*(base_fields + tech_fields))
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

    token = symbol.split(":")[-1].upper()
    symbol_col = "Symbol" if "Symbol" in snapshot.columns else None
    row = snapshot[snapshot[symbol_col] == symbol] if symbol_col else snapshot.iloc[0:0]
    if row.empty and symbol_col:
        row = snapshot[snapshot[symbol_col].astype(str).str.upper() == token]
    if row.empty and symbol_col:
        row = snapshot[snapshot[symbol_col].astype(str).str.upper().str.endswith(f":{token}")]
    if row.empty and "Name" in snapshot.columns:
        row = snapshot[snapshot["Name"].astype(str).str.upper() == token]

    if row.empty:
        return {"error": "无数据"}

    payload = row.iloc[0].to_dict()

    def _lookup(col_name: str):
        if col_name in payload:
            return payload.get(col_name)
        # 兼容大小写差异
        for k, v in payload.items():
            if str(k).lower() == str(col_name).lower():
                return v
        return None

    _, tech_col_map = _resolve_technical_stock_fields()
    price = float(_lookup("Price") or 0)
    change_pct = float(_lookup("Change %") or 0)
    change = price * change_pct / 100 if price else 0.0

    return {
        "symbol": payload.get("Symbol") or symbol,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "volume": float(_lookup("Volume") or 0),
        "technical": {
            "rsi_14": _lookup(tech_col_map.get("rsi_14", "")),
            "macd": _lookup(tech_col_map.get("macd", "")),
            "macd_signal": _lookup(tech_col_map.get("macd_signal", "")),
            "sma20": _lookup(tech_col_map.get("sma20", "")),
            "sma50": _lookup(tech_col_map.get("sma50", "")),
            "ema20": _lookup(tech_col_map.get("ema20", "")),
            "ema50": _lookup(tech_col_map.get("ema50", "")),
            "recommend_all": _lookup(tech_col_map.get("recommend_all", "")),
            "recommend_ma": _lookup(tech_col_map.get("recommend_ma", "")),
            "recommend_other": _lookup(tech_col_map.get("recommend_other", "")),
        },
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
