#!/usr/bin/env python3
"""
查询股票实时价格 - 通过 AlphaVantage API

用法:
    python query_stock_prices.py                    # 查询 NASDAQ 100 热门股票
    python query_stock_prices.py AAPL MSFT NVDA    # 查询指定股票
"""

import sys
import json
import requests
from datetime import datetime
from pathlib import Path

# 将 scripts 目录加入 Python 路径以导入 _config
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _config import load_config, get_alphavantage_key

# 从 config.yaml 加载 AlphaVantage API Key
_config = load_config()
APIKEY = get_alphavantage_key(_config)
BASE_URL = "https://www.alphavantage.co/query"

# 默认查询的热门股票
DEFAULT_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "NFLX", "AMD"
]


def get_intraday_price(symbol: str) -> dict:
    """
    获取股票的日内价格数据
    
    Args:
        symbol: 股票代码
        
    Returns:
        包含价格信息的字典
    """
    if not APIKEY:
        return {"error": "ALPHAADVANTAGE_API_KEY 未配置"}
    
    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": "60min",
        "apikey": APIKEY,
        "outputsize": "compact"
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        data = response.json()
        
        if "Error Message" in data:
            return {"error": data["Error Message"]}
        
        if "Note" in data:
            return {"error": "API 调用限制，请稍后重试"}
        
        time_series = data.get("Time Series (60min)", {})
        if not time_series:
            return {"error": "无数据"}
        
        # 获取最新的价格
        latest_time = sorted(time_series.keys())[-1]
        latest_data = time_series[latest_time]
        
        return {
            "symbol": symbol,
            "time": latest_time,
            "open": float(latest_data["1. open"]),
            "high": float(latest_data["2. high"]),
            "low": float(latest_data["3. low"]),
            "close": float(latest_data["4. close"]),
            "volume": int(latest_data["5. volume"])
        }
    except requests.exceptions.Timeout:
        return {"error": "请求超时"}
    except Exception as e:
        return {"error": str(e)}


def get_daily_price(symbol: str) -> dict:
    """
    获取股票的每日价格数据（包括前一天收盘价）
    
    Args:
        symbol: 股票代码
        
    Returns:
        包含每日价格信息的字典
    """
    if not APIKEY:
        return {"error": "ALPHAADVANTAGE_API_KEY 未配置"}
    
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "apikey": APIKEY,
        "outputsize": "compact"
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        data = response.json()
        
        if "Error Message" in data:
            return {"error": data["Error Message"]}
        
        if "Note" in data:
            return {"error": "API 调用限制，请稍后重试"}
        
        time_series = data.get("Time Series (Daily)", {})
        if not time_series:
            return {"error": "无数据"}
        
        dates = sorted(time_series.keys(), reverse=True)
        
        result = {"symbol": symbol}
        
        if len(dates) >= 1:
            latest = time_series[dates[0]]
            result["latest_date"] = dates[0]
            result["latest_close"] = float(latest["4. close"])
        
        if len(dates) >= 2:
            prev = time_series[dates[1]]
            result["prev_date"] = dates[1]
            result["prev_close"] = float(prev["4. close"])
            result["change"] = result["latest_close"] - result["prev_close"]
            result["change_pct"] = (result["change"] / result["prev_close"]) * 100
        
        return result
    except requests.exceptions.Timeout:
        return {"error": "请求超时"}
    except Exception as e:
        return {"error": str(e)}


def get_quote(symbol: str) -> dict:
    """
    获取股票的实时报价
    
    Args:
        symbol: 股票代码
        
    Returns:
        包含报价信息的字典
    """
    if not APIKEY:
        return {"error": "ALPHAADVANTAGE_API_KEY 未配置"}
    
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": APIKEY
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        data = response.json()
        
        if "Error Message" in data:
            return {"error": data["Error Message"]}
        
        if "Note" in data:
            return {"error": "API 调用限制，请稍后重试"}
        
        quote = data.get("Global Quote", {})
        if not quote:
            return {"error": "无数据"}
        
        return {
            "symbol": quote.get("01. symbol"),
            "price": float(quote.get("05. price", 0)),
            "open": float(quote.get("02. open", 0)),
            "high": float(quote.get("03. high", 0)),
            "low": float(quote.get("04. low", 0)),
            "volume": int(quote.get("06. volume", 0)),
            "prev_close": float(quote.get("08. previous close", 0)),
            "change": float(quote.get("09. change", 0)),
            "change_pct": quote.get("10. change percent", "0%").replace("%", "")
        }
    except requests.exceptions.Timeout:
        return {"error": "请求超时"}
    except Exception as e:
        return {"error": str(e)}


def main():
    """主函数"""
    # 解析命令行参数
    symbols = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SYMBOLS
    
    print("📈 股票实时价格查询")
    print("=" * 50)
    print(f"数据来源: AlphaVantage API")
    print(f"查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"查询股票: {', '.join(symbols)}")
    print("=" * 50)
    
    if not APIKEY:
        print("\n❌ 错误: AlphaVantage API Key 未配置")
        print("请在 config.yaml 中配置 alphavantage.api_key")
        sys.exit(1)
    
    print("\n获取报价数据...\n")
    
    results = []
    for symbol in symbols:
        print(f"  获取 {symbol}...", end=" ")
        result = get_quote(symbol)
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
            change_str = f"{r['change']:+.2f}" if r['change'] else "N/A"
            pct_str = f"{float(r['change_pct']):+.2f}%" if r['change_pct'] else "N/A"
            print(f"{r['symbol']:<8} ${r['price']:>10.2f} {change_str:>10} {pct_str:>10}")
    
    print("\n💡 提示: AlphaVantage 免费版限制 5 次/分钟，如遇限制请稍后重试")


if __name__ == "__main__":
    main()
