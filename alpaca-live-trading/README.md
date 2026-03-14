# alpaca-live-trading 同步与数据准备说明

本文档说明当前在 `alpaca-live-trading` 中实现的 AlphaVantage 数据同步方案（含日线与基本面）。

## 目标

- 使用 AlphaVantage 拉取美股日线数据
- 数据落地到本地 SQLite
- 支持首次全量、后续增量同步
- 支持单股票与多股票批量同步
- 严格控制 API 调用速率（默认 75 次/分钟）

## 脚本位置

- `scripts/sync_alpha_daily_to_sqlite.py`
- `scripts/sync_alpha_fundamentals_to_sqlite.py`
- `scripts/query_fundamentals_sqlite.py`
- `scripts/query_prices_sqlite.py`

## 数据库设计

默认数据库文件：

- `data/stock_daily.sqlite`

核心表：

- `stock_daily`
- `fundamentals_quarterly`
- `fundamentals_overview_daily`
- `sync_audit`

字段与约束：

- `symbol`（TEXT, NOT NULL）
- `trade_date`（TEXT, NOT NULL）
- `open` / `high` / `low` / `close`（REAL, NOT NULL）
- `volume`（INTEGER, NOT NULL）
- `source`（TEXT, NOT NULL, 默认 `alphavantage`）
- `created_at_utc` / `updated_at_utc`（TEXT, NOT NULL）
- 主键：`PRIMARY KEY (symbol, trade_date)`
- 索引：`idx_stock_daily_symbol_date(symbol, trade_date)`

说明：

- 主键保证同一股票同一交易日唯一
- 采用 `ON CONFLICT ... DO UPDATE` 保证重复同步幂等

## 日线同步策略

当前已实现三段式策略：

1. 首次同步（DB 中无该 symbol 历史）：
   - 使用 `outputsize=full` 全量拉取
2. 后续增量同步（DB 中已有历史）：
   - 使用 `outputsize=compact` 拉取近 100 条左右日线
   - 只写入 `trade_date > 最新库内日期` 的记录
3. 兜底回退（避免 compact 覆盖不足）：
   - 若 API 显示存在更新，但 compact 没有任何可增量记录
   - 自动回退 `outputsize=full` 再拉一次，补齐缺失区间

脚本输出会显示本次模式：

- `Fetch mode: full`
- `Fetch mode: compact`
- `Fetch mode: full(fallback)`

## 交易日与周末处理

- 通过 AlphaVantage 返回的 `Time Series (Daily)` 作为“最新可用交易日”基准
- 周末和美股休市日没有新 bar 时，会自然显示 `up-to-date`
- 不会因自然休市误判为同步失败

## 限速机制

- 默认 `75` 次/分钟（付费版上限场景）
- 采用滑动窗口限速器
- 批量同步时所有 symbol 共享同一个限速器

可通过参数调整：

- `--max-calls-per-minute`

## 基本面同步（5年季度）

`scripts/sync_alpha_fundamentals_to_sqlite.py` 会拉取以下接口并入库：

- `OVERVIEW`
- `INCOME_STATEMENT`
- `BALANCE_SHEET`
- `CASH_FLOW`

季度表（`fundamentals_quarterly`）主要字段：

- 收入/利润：`revenue`, `operating_income`, `net_income`
- 现金流：`operating_cashflow`, `capital_expenditures`, `free_cashflow`
- 真实性辅助：`change_in_receivables`, `change_in_inventory`
- 资产负债：`total_assets`, `total_liabilities`, `total_shareholder_equity`, `cash_and_short_term_investments`, `current_debt`, `long_term_debt`

overview 快照表（`fundamentals_overview_daily`）主要字段：

- 估值：`market_cap`, `pe_ratio`
- 质量指标：`profit_margin`, `operating_margin_ttm`, `roe_ttm`, `roa_ttm`
- short-interest 代理字段：`short_ratio`, `shares_short`, `shares_short_prior_month`

## 用法

### 1) 单股票同步

```bash
python scripts/sync_alpha_daily_to_sqlite.py --symbol AAPL
```

### 2) 多股票批量同步

```bash
python scripts/sync_alpha_daily_to_sqlite.py --symbols AAPL,MSFT,NVDA
```

### 3) 单+多组合（会自动去重）

```bash
python scripts/sync_alpha_daily_to_sqlite.py --symbol AAPL --symbols AAPL,MSFT
```

### 4) 自定义限速与 DB 路径

```bash
python scripts/sync_alpha_daily_to_sqlite.py \
  --symbols AAPL,MSFT,NVDA \
  --max-calls-per-minute 75 \
  --db-path ./data/stock_daily.sqlite
```

### 5) 基本面同步（单只/批量/默认池）

```bash
# 单只
python scripts/sync_alpha_fundamentals_to_sqlite.py --symbol AAPL --years 5

# 批量
python scripts/sync_alpha_fundamentals_to_sqlite.py --symbols AAPL,NVDA,BABA --years 5 --with-audit

# 默认101池（可配分批）
python scripts/sync_alpha_fundamentals_to_sqlite.py --default-pool --years 5 --batch-size 20 --with-audit
```

### 6) 本地基本面查询

```bash
# 文本输出
python scripts/query_fundamentals_sqlite.py --symbol BABA --quarters 8

# JSON输出
python scripts/query_fundamentals_sqlite.py --symbol BABA --quarters 8 --json
```

### 7) 本地历史股价查询（SQLite）

```bash
# 最近30天（默认）
python scripts/query_prices_sqlite.py --symbol BABA

# 多股票 + 指定天数
python scripts/query_prices_sqlite.py --symbols AAPL,NVDA,BABA --days 60

# 指定日期区间 + JSON
python scripts/query_prices_sqlite.py --symbol BABA --start-date 2026-02-01 --end-date 2026-03-31 --json
```

## 配置来源

脚本通过 `scripts/_config.py` 读取：

- `config.yaml` -> `alphavantage.api_key`

请确保 `config.yaml` 已正确配置 AlphaVantage API Key。

## 当前进度（W-Bottom 数据准备）

已完成：

- 日线增量同步脚本（首次 full，后续 compact，fallback full）
- 日线脚本增强：`--default-pool`、`--batch-size`、`--with-audit`
- 基本面同步脚本（5年季度窗口）并已验证 AAPL/NVDA/BABA
- 本地基本面查询脚本（避免手写 SQL）
- pipeline 支持单策略配置（`strategy.name`）并优先读取
- pipeline 支持两轮筛选：
  - 第一轮：按策略（如 `w_bottom_breakout`）筛出候选（`prefilter_top_k` 是上限，不保底）
  - 第二轮：对候选 + 基准ETF 做 AlphaVantage 新闻/基本面 + tvscreener + Polymarket 深度分析，并生成交易计划

待完成（TODO，当前仍未实现）：

- 计算 `w_bottom_breakout` 特征表（RPS120/RPS250、波动率、EV、FCF/EV、short-interest 代理）并落库
- 增加数据完整性校验脚本（覆盖率、可计算率、ready 结论）
- 在 README 增加“特征脚本 + 校验脚本”使用示例（待上述脚本落地后补充）

## 两轮策略流程（当前推荐）

在 `config.yaml` 中配置：

```yaml
strategy:
  enabled: true
  name: w_bottom_breakout
  min_confidence: 0.6
  prefilter_top_k: 10
```

运行：

```bash
# 仅分析，不下单
python scripts/run_analysis_trade_pipeline.py

# 分析 + 自动执行（受 market gate + risk guard 控制）
python scripts/run_analysis_trade_pipeline.py --execute-trades
```

### 二阶段会收集哪些数据

第二阶段分析池为：`第一阶段候选 + benchmark_tickers(默认 QQQ,SPY)`。

- AlphaVantage 新闻情绪：`fetch_news_per_ticker`（每只默认 5 条，可通过 `--news-limit` 调整）
- AlphaVantage 基本面：`fetch_fundamentals_for_symbol`（`OVERVIEW / INCOME_STATEMENT / BALANCE_SHEET / CASH_FLOW / EARNINGS`）
- tvscreener 价格与技术面：`get_quote`（当前会用到 `technical.recommend_all` 与价格）
- Polymarket 市场赔率：`get_financial_sentiment`（用于市场门控）
- 本地账户快照：`data/position/position.jsonl`、`data/balance/balance.jsonl`（用于仓位与风控）

> 说明：当前实现中二阶段仍然会采集 AlphaVantage 与 Polymarket 信息，结果写入
> `skills/alpaca-live-trading/data/analysis_pipeline_latest.json` 的
> `alpha_vantage.*` 与 `polymarket_sentiment` 字段。

### 二阶段如何决定“是否交易、怎么交易”

1) Round2 综合评分（仅对第一阶段候选）  

- `fundamental_score`（50%）：ROE、净利率、营收环比、FCF环比
- `technical_score`（30%）：`recommend_all`
- `news_score`（20%）：新闻动量（带时效衰减 + 少样本惩罚）

2) Round2 通过规则  

- 优先保留 `score >= 0.4` 的标的
- 若没有任何标的达标，则回退为 round2 排名前 `top_k`

3) 融合第一阶段信号  

- 最终置信度：`0.7 * stage1_confidence + 0.3 * round2_score`
- 仅保留在 `round2_pass_symbols` 内的信号

4) 生成交易计划（order_builder）  

- 每笔预算：`min(available_cash * max_position_pct, max_trade_notional)`
- 买入：`qty = floor(per_trade_budget / price)`
- 卖出：默认卖当前持仓的一半（至少 1 股）

5) 风控拦截（risk_guard）  

- 拦截条件：`exceed_max_trade_notional` / `exceed_max_position_pct` / `exceed_max_positions`

6) 是否实际下单  

- 仅当命令包含 `--execute-trades` 时才会执行
- 且需通过市场门控：`market_gate_score >= market_gate_threshold`（默认阈值 `-0.05`）
- 不满足时会保留分析与计划结果，但不会实际下单

## 后续可扩展方向

- 增加重试与指数退避策略（针对瞬时网络抖动）
- 按 symbol 并发拉取（在总限速约束下）
- 接入策略引擎直接消费 `stock_daily` + `fundamentals_*` 数据
