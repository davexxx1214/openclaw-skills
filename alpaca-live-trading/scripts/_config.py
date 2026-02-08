"""
共享配置加载模块

从 skills/alpaca-live-trading/config.yaml 读取 API Key 配置。
所有 skill 脚本统一通过此模块获取配置，不依赖项目根目录 .env。

用法:
    from _config import load_config
    config = load_config()
    api_key = config["alphavantage"]["api_key"]
"""

import sys
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:
    print("❌ 缺少 pyyaml 依赖，请安装: pip install pyyaml")
    sys.exit(1)

# Skill 根目录: skills/alpaca-live-trading/
SKILL_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = SKILL_ROOT / "config.yaml"
CONFIG_EXAMPLE_FILE = SKILL_ROOT / "config.example.yaml"


def load_config(config_path: Path = None) -> Dict[str, Any]:
    """
    加载 config.yaml 配置文件

    Args:
        config_path: 配置文件路径，默认为 skills/alpaca-live-trading/config.yaml

    Returns:
        配置字典

    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: 配置文件格式错误
    """
    if config_path is None:
        config_path = CONFIG_FILE

    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        print(f"   请复制模板并填入真实 API Key:")
        print(f"   cp {CONFIG_EXAMPLE_FILE} {CONFIG_FILE}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        print(f"❌ 配置文件格式错误: {config_path}")
        sys.exit(1)

    return config


def get_alphavantage_key(config: Dict[str, Any] = None) -> str:
    """获取 AlphaVantage API Key"""
    if config is None:
        config = load_config()
    key = config.get("alphavantage", {}).get("api_key", "")
    if not key or key.startswith("your_"):
        print("❌ AlphaVantage API Key 未配置，请在 config.yaml 中填入真实 Key")
        sys.exit(1)
    return key


def get_alpaca_credentials(config: Dict[str, Any] = None) -> tuple:
    """
    获取 Alpaca API 凭证

    Args:
        config: 配置字典，为空则自动加载

    Returns:
        (api_key, secret_key, paper) 元组，paper 为 bool 表示是否模拟交易
    """
    if config is None:
        config = load_config()
    alpaca_config = config.get("alpaca", {})
    api_key = alpaca_config.get("api_key", "")
    secret_key = alpaca_config.get("secret_key", "")
    paper = alpaca_config.get("paper", True)
    if not api_key or api_key.startswith("your_") or not secret_key or secret_key.startswith("your_"):
        print("❌ Alpaca API 凭证未配置，请在 config.yaml 中填入真实 Key")
        sys.exit(1)
    return api_key, secret_key, paper
