# Alpaca Live Trading Skill

AI 实时交易技能 - 使用 Alpaca Paper Trading 进行美股交易决策。

## 概述

此技能提供一组独立的 Python 查询脚本，用于获取交易决策所需的各类数据。所有脚本可独立运行，不依赖任何 MCP 服务或项目主服务。

交易决策与执行所需数据：
1. **获取股价数据** - 通过 TradingView tvscreener 获取 NASDAQ 100 成分股的实时价格
2. **获取市场新闻** - 通过 AlphaVantage NEWS_SENTIMENT API 获取市场新闻和情绪分析
3. **获取市场情绪** - 通过 Polymarket 获取预测市场情绪指标
4. **查询账户状态** - 通过 Alpaca API 获取当前持仓和账户余额
5. **执行交易并落盘** - 每次交易后同步更新 `position.jsonl` 与 `balance.jsonl`

## 环境配置

### 1. 安装 Python 依赖

```bash
pip install requests pyyaml alpaca-py tvscreener
```

### 2. 配置 API Keys

复制配置模板并填入真实的 API Key：

```bash
cp skills/alpaca-live-trading/config.example.yaml skills/alpaca-live-trading/config.yaml
```

编辑 `config.yaml`：

```yaml
# AlphaVantage API - 用于获取股价数据和市场新闻
# 申请地址: https://www.alphavantage.co/support/#api-key
alphavantage:
  api_key: "your_alphavantage_api_key"

# Alpaca Trading API - 用于查询账户和执行交易
# 申请地址: https://app.alpaca.markets/paper/dashboard/overview
# paper: true 表示模拟交易，false 表示真实交易
alpaca:
  api_key: "your_alpaca_api_key"
  secret_key: "your_alpaca_secret_key"
  paper: true
```

> 注意：`config.yaml` 包含真实 API Key，已加入 `.gitignore`，不会被提交到 Git。

## 查询脚本

以下脚本均可独立运行，所有脚本位于 `skills/alpaca-live-trading/scripts/` 目录。

## 交易执行与记录规则（重要）

每次执行交易（buy/sell）时，必须遵循以下流程：

1. 下单（Alpaca）
2. 订单成交后，重新查询 Alpaca 账户真实状态（账户概览 + 全部持仓）
3. 读取并更新 `position.jsonl`
4. 读取并更新 `balance.jsonl`

其中：
- `position.jsonl`：记录每笔动作及交易后持仓快照（用于策略/回测一致性）
- `balance.jsonl`：记录交易后账户总览和每只持仓的成本、现价、市值、盈亏（用于资金追踪）

### 1. 查询股价数据 (TradingView tvscreener)

```bash
# 查询 NASDAQ 100 + QQQ (共 101 只) 的实时价格
python skills/alpaca-live-trading/scripts/query_stock_prices.py

# 查询指定股票
python skills/alpaca-live-trading/scripts/query_stock_prices.py AAPL MSFT NVDA
```

**默认股票列表（NASDAQ 100 + QQQ，101 只）：**
```
NVDA, MSFT, AAPL, GOOG, GOOGL, AMZN, META, AVGO, TSLA, NFLX,
PLTR, COST, ASML, AMD, CSCO, AZN, TMUS, MU, LIN, PEP,
SHOP, APP, INTU, AMAT, LRCX, PDD, QCOM, ARM, INTC, BKNG,
AMGN, TXN, ISRG, GILD, KLAC, PANW, ADBE, HON, CRWD, CEG,
ADI, ADP, DASH, CMCSA, VRTX, MELI, SBUX, CDNS, ORLY, SNPS,
MSTR, MDLZ, ABNB, MRVL, CTAS, TRI, MAR, MNST, CSX, ADSK,
PYPL, FTNT, AEP, WDAY, REGN, ROP, NXPI, DDOG, AXON, ROST,
IDXX, EA, PCAR, FAST, EXC, TTWO, XEL, ZS, PAYX, WBD,
BKR, CPRT, CCEP, FANG, TEAM, CHTR, KDP, MCHP, GEHC, VRSK,
CTSH, CSGP, KHC, ODFL, DXCM, TTD, ON, BIIB, LULU, CDW, GFS,
QQQ
```

> 注意：该脚本使用 TradingView tvscreener，无需 AlphaVantage 限速配置。

**查询结果会更新到：**
`skills/alpaca-live-trading/data/stock_prices_latest.json`

**输出示例：**
```
📈 股票实时价格查询
====================
获取 AAPL 价格... ✓
获取 MSFT 价格... ✓

📊 股票价格汇总
股票     当前价格         涨跌       涨跌幅
AAPL     $185.50      +1.30      +0.71%
MSFT     $420.30      +1.80      +0.43%
```

### 2. 查询市场新闻和情绪 (AlphaVantage NEWS_SENTIMENT)

```bash
# 查询最新金融市场新闻
python skills/alpaca-live-trading/scripts/query_market_news.py

# 查询指定股票相关新闻
python skills/alpaca-live-trading/scripts/query_market_news.py --tickers AAPL,NVDA

# 查询指定主题新闻
python skills/alpaca-live-trading/scripts/query_market_news.py --topics technology

# 组合过滤 + 详细模式
python skills/alpaca-live-trading/scripts/query_market_news.py --tickers AAPL --topics earnings --verbose

# 以 JSON 格式输出（方便程序解析）
python skills/alpaca-live-trading/scripts/query_market_news.py --tickers NVDA --json
```

**支持的新闻主题：**
`blockchain`, `earnings`, `ipo`, `mergers_and_acquisitions`, `financial_markets`, `economy_fiscal`, `economy_monetary`, `economy_macro`, `energy_transportation`, `finance`, `life_sciences`, `manufacturing`, `real_estate`, `retail_wholesale`, `technology`

**输出示例：**
```
📰 市场新闻与情绪查询
============================================================
找到 10 篇新闻:

  1. NVIDIA Reports Record Revenue Amid AI Boom
     来源: Reuters | 时间: 2026-02-05 14:30:00
     情绪: 强烈看涨 (+0.456)
     摘要: NVIDIA reported record quarterly revenue driven by...

  2. Apple Announces New AI Features for iPhone
     来源: Bloomberg | 时间: 2026-02-05 12:15:00
     情绪: 看涨 (+0.234)
     摘要: Apple unveiled a suite of new artificial intelligence...
```

### 3. 查询 Polymarket 市场情绪

```bash
# 查询金融市场情绪指标
python skills/alpaca-live-trading/scripts/query_polymarket_sentiment.py

# 查询热门预测市场
python skills/alpaca-live-trading/scripts/query_polymarket_sentiment.py --trending
```

**输出示例：**
```
📊 Polymarket 金融市场实时情绪指标
数据时间: 2026-02-05 15:30:00 UTC

## Finance Daily (每日金融)
1. **S&P 500 up today?** | Yes: 65.2% | 24h Vol: $125,000
2. **NASDAQ up today?** | Yes: 58.3% | 24h Vol: $89,000

## Stocks (股票)
1. **AAPL above $185 EOD?** | Yes: 72.1% | 24h Vol: $45,000
2. **NVDA above $900 this week?** | Yes: 61.5% | 24h Vol: $156,000
```

### 4. 查询 Alpaca 账户状态

```bash
# 查询账户余额和持仓
python skills/alpaca-live-trading/scripts/query_alpaca_account.py

# 同时显示最近订单
python skills/alpaca-live-trading/scripts/query_alpaca_account.py --orders

# 以 JSON 格式输出
python skills/alpaca-live-trading/scripts/query_alpaca_account.py --json
```

**输出示例：**
```
💰 Alpaca Paper Trading (模拟交易) 账户状态
============================================================
📊 账户概览
  账户号码: 123456789
  现金余额: $8,523.45
  买入能力: $17,046.90

📦 当前持仓:
  AAPL: 10 股
    成本价: $184.20 | 现价: $185.50 | 市值: $1,855.00
    盈亏: +$13.00 (+0.71%)
  NVDA: 5 股
    成本价: $875.50 | 现价: $900.00 | 市值: $4,500.00
    盈亏: +$122.50 (+2.80%)

总未实现盈亏: +$135.50
```

### 5. 执行交易并同步 `position.jsonl` / `balance.jsonl`

```bash
# 买入
python skills/alpaca-live-trading/scripts/execute_alpaca_trade.py --action buy --symbol AAPL --qty 1

# 卖出
python skills/alpaca-live-trading/scripts/execute_alpaca_trade.py --action sell --symbol AAPL --qty 1

# 输出 JSON
python skills/alpaca-live-trading/scripts/execute_alpaca_trade.py --action buy --symbol NVDA --qty 2 --json
```

**交易后更新文件（skill 内部目录）：**
- `skills/alpaca-live-trading/data/position/position.jsonl`
- `skills/alpaca-live-trading/data/balance/balance.jsonl`

`balance.jsonl` 每条记录包含：
- `account`：账户总览（cash, buying_power, equity, portfolio_value 等）
- `positions`：每只持仓明细（symbol, qty, avg_entry_price, current_price, market_value, unrealized_pl）
- `trade`：本次交易信息（action, symbol, qty, filled_price, order_id）
- 时间字段：同时保留 `timestamp_et`（US/Eastern）和 `timestamp_utc`（UTC），用于跨机器时间同步与防漂移

### 6. 查询最近 N 条统一交易记录（默认 50 条）

```bash
# 默认最近 50 条
python skills/alpaca-live-trading/scripts/query_trade_records.py

# 查询最近 20 条
python skills/alpaca-live-trading/scripts/query_trade_records.py --limit 20

# 输出 JSON
python skills/alpaca-live-trading/scripts/query_trade_records.py --json
```

该脚本会读取并统一展示：
- `position.jsonl`（动作 + 持仓快照）
- `balance.jsonl`（账户总览 + 持仓明细）
- 并优先按 `timestamp_utc` 排序（兼容旧数据）

### 7. 重置本地账户记录状态（清理 jsonl）

```bash
# 重置单 agent 记录文件（会二次确认）
python skills/alpaca-live-trading/scripts/reset_account_state.py

# 跳过确认直接执行
python skills/alpaca-live-trading/scripts/reset_account_state.py --yes
```

该指令会删除：
- `skills/alpaca-live-trading/data/position/position.jsonl`
- `skills/alpaca-live-trading/data/balance/balance.jsonl`

> 注意：只会清理本地记录文件，不会修改 Alpaca 真实账户持仓与余额。下次交易会自动重新创建这两个文件。

## 文件结构

```
skills/alpaca-live-trading/
├── SKILL.md                 # 本文档
├── config.yaml              # API Keys 配置（不提交到 Git）
├── config.example.yaml      # 配置模板
└── scripts/
    ├── _config.py                      # 共享配置加载模块
    ├── query_stock_prices.py           # 查询实时股价
    ├── query_market_news.py            # 查询市场新闻和情绪
    ├── query_polymarket_sentiment.py   # 查询 Polymarket 预测市场情绪
    ├── query_alpaca_account.py         # 查询 Alpaca 账户状态和持仓
    ├── execute_alpaca_trade.py         # 执行交易并更新 position/balance
    ├── query_trade_records.py          # 查询最近 N 条统一交易记录
    └── reset_account_state.py          # 重置本地账户记录（删除 jsonl）
```

## 故障排查

### 常见问题

1. **config.yaml 不存在**
   - 复制模板: `cp config.example.yaml config.yaml`
   - 填入真实的 API Key

2. **缺少 pyyaml**
   - 运行: `pip install pyyaml`

3. **AlphaVantage API 调用限制**
   - 免费版限制: 25 次/天, 5 次/分钟
   - 遇到限制时等待后重试

4. **Alpaca API Key 无效**
   - 确认 config.yaml 中的 Key 正确
   - 确认使用的是 Paper Trading 账户的 Key

5. **alpaca-py 未安装**
   - 运行: `pip install alpaca-py`
