---
name: polymarket-5m-arb-monitor
description: Monitor Polymarket "Bitcoin Up or Down - 5 min" market every 30 seconds, compare with Alpaca BTC spot/minute bars, and flag fee-adjusted arbitrage opportunities. Use when user asks for 5-minute BTC up/down monitoring, refresh loop, or arbitrage scanning with fee threshold.
---

# Polymarket 5M Arb Monitor

每 30 秒轮询一次 Polymarket 的 `Bitcoin Up or Down - 5 min` 盘口，结合 Alpaca 的 `BTC/USD` 分钟线估计未来 5 分钟上涨概率，并按手续费阈值筛选信号。

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
```

## 关键参数

- `--interval-seconds`：轮询间隔，默认 `30`
- `--fee-rate`：利润门槛（小数），默认 `0.0015`
- `--history-bars`：Alpaca 分钟线回看条数，默认 `300`
- `--neighbors`：KNN 近邻数量，默认 `80`
- `--polls`：轮询次数，`0` 为无限循环
- `--output-jsonl`：监控输出落盘路径（默认 `data/arb_monitor.jsonl`）
- `--pid-file`：监控 PID 文件（默认 `data/monitor.pid`）
- `--stop`：根据 PID 文件停止监控
- `--auto-trade`：命中 `ARBITRAGE` 后自动下单
- `--trade-notional-usd`：每笔自动交易金额（USD）
- `--trade-cooldown-seconds`：两次自动交易最小间隔秒数

## 输出说明

每轮输出字段（简化）：

- `signal`：`ARBITRAGE` 或 `NO_EDGE`
- `best_side`：`UP` 或 `DOWN`
- `best_edge`：模型概率与盘口概率的差值（已和手续费阈值比较）
- `pm_up_prob` / `pm_down_prob`：Polymarket 概率
- `model_up_prob`：基于 Alpaca 分钟线估计的 5 分钟上涨概率
- `alpaca_spot_price`：当前现货近似价（分钟线最后收盘）
- `auto_trade`：自动下单结果（是否执行、方向、订单号、失败原因）

## 策略备注

该监控是统计套利信号，不是确定性无风险套利。执行前建议再做：

1. 盘口深度与滑点检查
2. 网络延迟与成交延迟检查
3. 持续 2-3 轮确认信号稳定后再下单
