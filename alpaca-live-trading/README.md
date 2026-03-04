# alpaca-live-trading 同步机制说明

本文档说明当前在 `alpaca-live-trading` 中实现的 AlphaVantage 日线同步方案。

## 目标

- 使用 AlphaVantage 拉取美股日线数据
- 数据落地到本地 SQLite
- 支持首次全量、后续增量同步
- 支持单股票与多股票批量同步
- 严格控制 API 调用速率（默认 75 次/分钟）

## 脚本位置

- `scripts/sync_alpha_daily_to_sqlite.py`

## 数据库设计

默认数据库文件：

- `data/stock_daily.sqlite`

核心表：

- `stock_daily`

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

## 同步策略

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

## 配置来源

脚本通过 `scripts/_config.py` 读取：

- `config.yaml` -> `alphavantage.api_key`

请确保 `config.yaml` 已正确配置 AlphaVantage API Key。

## 后续可扩展方向

- 增加同步审计表（记录每次批量任务耗时、成功/失败明细）
- 增加重试与指数退避策略（针对瞬时网络抖动）
- 按 symbol 并发拉取（在总限速约束下）
- 接入策略引擎直接消费 `stock_daily` 数据
