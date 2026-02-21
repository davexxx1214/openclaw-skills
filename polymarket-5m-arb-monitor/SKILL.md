---
name: polymarket-5m-arb-monitor
description: Monitor Polymarket "Bitcoin Up or Down - 5 min" market every 30 seconds, compare with Alpaca BTC spot/minute bars, and flag fee-adjusted arbitrage opportunities. Use when user asks for 5-minute BTC up/down monitoring, refresh loop, or arbitrage scanning with fee threshold.
---

# Polymarket 5M Arb Monitor

每 30 秒轮询一次 Polymarket 的 `Bitcoin Up or Down - 5 min` 盘口，结合 Alpaca 的 `BTC/USD` 现货价格，并按策略规则筛选信号。

默认手续费门槛：`0.15%`（`--fee-rate 0.0015`）。

## 依赖

```bash
pip install requests pyyaml alpaca-py
```

## 配置

默认读取 `polymarket-5m-arb-monitor/config.yaml`：

```yaml
alpaca:
  api_key: "..."
  secret_key: "..."
  paper: true
```

也可以通过 `--config` 指定其他配置文件。

## 运行方式

```bash
# 单次测试（轮询1次）
python polymarket-5m-arb-monitor/scripts/monitor_btc_5m_arb.py --polls 1

# 持续监控（每30秒）
python polymarket-5m-arb-monitor/scripts/monitor_btc_5m_arb.py

# JSON 输出，便于程序消费
python polymarket-5m-arb-monitor/scripts/monitor_btc_5m_arb.py --json

# 停止正在运行的监控进程
python polymarket-5m-arb-monitor/scripts/monitor_btc_5m_arb.py --stop

# 发现套利机会后自动交易（单笔 $100，冷却300秒）
python polymarket-5m-arb-monitor/scripts/monitor_btc_5m_arb.py \
  --auto-trade \
  --trade-notional-usd 100 \
  --trade-cooldown-seconds 300

# 仅采集回测数据（不交易）
python polymarket-5m-arb-monitor/scripts/collect_btc_5m_backtest_data.py \
  --interval-seconds 30 --json

# 严格回测（按 Polymarket 已结算结果）
python polymarket-5m-arb-monitor/scripts/run_strict_backtest.py --json
```

## 关键参数

- `--interval-seconds`：轮询间隔，默认 `30`
- `--fee-rate`：利润门槛（小数），默认 `0.0015`
- `--strategy-mode`：`bucket_follow`（默认）或 `model_edge`
- `--history-bars`：Alpaca 分钟线回看条数，默认 `300`
- `--neighbors`：KNN 近邻数量，默认 `80`
- `--polls`：轮询次数，`0` 为无限循环
- `--output-jsonl`：监控输出落盘路径（默认 `data/arb_monitor.jsonl`）
- `--pid-file`：监控 PID 文件（默认 `data/monitor.pid`）
- `--stop`：根据 PID 文件停止监控
- `--auto-trade`：命中 `ARBITRAGE` 后自动下单
- `--trade-notional-usd`：每笔自动交易金额（USD）
- `--trade-cooldown-seconds`：两次自动交易最小间隔秒数
- `--confidence-min/--confidence-max`：`bucket_follow` 的置信度区间（`|p_up-p_down|`）
- `--max-prob-min/--max-prob-max`：`bucket_follow` 的 `max(p_up,p_down)` 区间

## 输出说明

每轮输出字段（简化）：

- `signal`：`ARBITRAGE` 或 `NO_EDGE`
- `best_side`：`UP` 或 `DOWN`
- `best_edge`：`model_edge` 下为模型边际；`bucket_follow` 下为置信度 `|p_up-p_down|`
- `pm_up_prob` / `pm_down_prob`：Polymarket 概率
- `strategy_mode`：当前策略模式
- `bucket_hit` / `bucket_metrics`：`bucket_follow` 的入桶与区间信息
- `model_up_prob`：仅 `model_edge` 模式下输出
- `alpaca_spot_price`：当前现货近似价（优先 latest quote）
- `auto_trade`：自动下单结果（是否执行、方向、订单号、失败原因）

## 策略备注

当前默认执行策略：`bucket_follow`（来自严格回测筛选）

- 置信度区间：`|p_up-p_down| ∈ [0.01, 0.02)`
- 最大概率区间：`max(p_up,p_down) ∈ [0.505, 0.510)`
- 桶命中时，按盘口高概率方向交易

该监控是统计套利信号，不是确定性无风险套利。执行前建议再做：

1. 盘口深度与滑点检查
2. 网络延迟与成交延迟检查
3. 持续 2-3 轮确认信号稳定后再下单
