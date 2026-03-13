import sys
import sqlite3
import unittest
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from _config import get_risk_config, get_strategy_config  # noqa: E402
from order_builder import build_trade_plan  # noqa: E402
from risk_guard import apply_risk_guard  # noqa: E402
from strategy_engine import run_strategies  # noqa: E402


class ConfigParsingTests(unittest.TestCase):
    def test_strategy_config_defaults_and_clamp(self):
        cfg = {"strategy": {"enabled": "true", "name": "w_bottom_breakout", "min_confidence": 9}}
        parsed = get_strategy_config(cfg)
        self.assertTrue(parsed["enabled"])
        self.assertEqual(parsed["name"], "w_bottom_breakout")
        self.assertEqual(parsed["min_confidence"], 1.0)

    def test_risk_config_defaults(self):
        parsed = get_risk_config({})
        self.assertGreaterEqual(parsed["max_position_pct"], 0.0)
        self.assertGreaterEqual(parsed["max_positions"], 1)
        self.assertGreaterEqual(parsed["max_trade_notional"], 0.0)


class StrategyEngineTests(unittest.TestCase):
    def test_run_strategies_generates_signals(self):
        context = {
            "ranking": [
                {"ticker": "NVDA", "momentum_score": 0.30},
                {"ticker": "AAPL", "momentum_score": -0.2},
            ],
            "selected_top_tickers": ["NVDA", "AAPL"],
            "market_gate_score": 0.2,
            "quotes": [
                {"symbol": "NVDA", "price": 100.0, "technical": {"recommend_all": 0.3}},
                {"symbol": "AAPL", "price": 50.0, "technical": {"recommend_all": 0.1}},
            ],
        }
        result = run_strategies(["news_momentum", "market_gate_trend"], context, min_confidence=0.5)
        self.assertIn("signals_accepted", result)
        self.assertGreaterEqual(len(result["signals_accepted"]), 1)

    def test_run_w_bottom_breakout_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "stock_daily.sqlite"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE stock_daily (
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    PRIMARY KEY(symbol, trade_date)
                )
                """
            )

            # Build a simple W-bottom-like series.
            prices = [100.0] * 120
            prices[20] = 82.0
            prices[45] = 100.0
            prices[70] = 84.0
            prices[95] = 98.0
            prices[119] = 99.5
            for i, close in enumerate(prices):
                dt = f"2025-01-{(i % 28) + 1:02d}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO stock_daily(symbol, trade_date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("TEST", f"{dt}-{i:03d}", close * 0.99, close * 1.01, close * 0.98, close, 1000000),
                )
            conn.commit()
            conn.close()

            context = {
                "universe_tickers": ["TEST"],
                "history_db_path": str(db_path),
                "strategy_prefilter_top_k": 10,
                "quotes": [{"symbol": "TEST", "price": 99.5, "technical": {"recommend_all": 0.2}}],
            }
            result = run_strategies(["w_bottom_breakout"], context, min_confidence=0.0)
            self.assertIn("signals_all", result)
            self.assertGreaterEqual(len(result["signals_all"]), 1)
            self.assertEqual(result["signals_all"][0]["strategy"], "w_bottom_breakout")


class OrderAndRiskTests(unittest.TestCase):
    def test_build_trade_plan_and_risk_guard(self):
        signals = [
            {
                "strategy": "news_momentum",
                "symbol": "NVDA",
                "action": "buy",
                "confidence": 0.8,
                "price": 100.0,
                "reason": "strong",
            },
            {
                "strategy": "news_momentum",
                "symbol": "AAPL",
                "action": "sell",
                "confidence": 0.9,
                "price": 50.0,
                "reason": "weak",
            },
        ]
        risk_cfg = {
            "max_position_pct": 0.1,
            "max_positions": 5,
            "max_trade_notional": 2000,
        }
        account = {"cash": 10000, "buying_power": 10000}
        positions = [{"symbol": "AAPL", "qty": 10}]

        built = build_trade_plan(
            signals=signals,
            risk_config=risk_cfg,
            account_snapshot=account,
            positions_snapshot=positions,
        )
        self.assertGreaterEqual(len(built["trade_plan"]), 1)

        guarded = apply_risk_guard(
            trade_plan=built["trade_plan"],
            risk_config=risk_cfg,
            account_snapshot=account,
            positions_snapshot=positions,
        )
        self.assertIn("accepted_plan", guarded)
        self.assertIn("rejections", guarded)


if __name__ == "__main__":
    unittest.main()
