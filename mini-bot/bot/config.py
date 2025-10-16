"""Configuration loader for the mini trading bot."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_ENV_PATH = Path(".env")
DEFAULT_TAU = 0.6


def _load_env(path: Path) -> Dict[str, str]:
    env_vars: Dict[str, str] = {}
    if not path.exists():
        return env_vars
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_vars[key.strip()] = value.strip()
    return env_vars


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    value_str = str(value).strip().lower()
    if value_str in {"1", "true", "yes", "y", "on"}:
        return True
    if value_str in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip('"')


def _load_yaml(text: str) -> Optional[Dict[str, Any]]:
    if yaml is not None:
        return yaml.safe_load(text) or {}

    lines = text.splitlines()
    root: Dict[str, Any] = {}
    stack: list[tuple[int, Dict[str, Any]]] = [(-1, root)]
    for raw in lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not value:
            new_dict: Dict[str, Any] = {}
            parent[key] = new_dict
            stack.append((indent, new_dict))
        else:
            parent[key] = _parse_scalar(value)
    return root


@dataclass
class OrderConfig:
    ladder_levels: int = 3
    timeout_bars: int = 1
    post_only: bool = True


@dataclass
class ATRConfig:
    window: int = 14
    k_sl: float = 2.5
    k_tp: float = 3.5


@dataclass
class VenueConfig:
    name: str = "binance"
    testnet: bool = True


@dataclass
class TradingConfig:
    timeframe: str = "4h"
    symbol: str = "BTC/USDT:USDT"
    leverage: float = 3
    risk_pct: float = 0.01
    daily_loss_limit_pct: float = 0.03
    max_positions: int = 1
    atr: ATRConfig = field(default_factory=ATRConfig)
    order: OrderConfig = field(default_factory=OrderConfig)
    venue: VenueConfig = field(default_factory=VenueConfig)
    tau: float = DEFAULT_TAU


@dataclass
class TelegramConfig:
    enabled: bool = True
    chat_id: Optional[int] = None


@dataclass
class MonitoringConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


@dataclass
class Config:
    trading: TradingConfig = field(default_factory=TradingConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    raw: Dict[str, Any] = field(default_factory=dict)


def load_config(
    env_path: Path = DEFAULT_ENV_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    overrides: Optional[Dict[str, Any]] = None,
) -> Config:
    """Load configuration from .env and YAML files."""

    overrides = overrides or {}
    env_data = _load_env(env_path)

    yaml_data: Dict[str, Any] = {}
    if config_path.exists():
        yaml_text = config_path.read_text()
        yaml_data = _load_yaml(yaml_text)
        if yaml_data is None:
            yaml_data = {}
    

    def _deep_get(data: Dict[str, Any], path: str, default: Any) -> Any:
        parts = path.split(".")
        cur: Any = data
        for part in parts:
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    trading = TradingConfig(
        timeframe=overrides.get(
            "trading.timeframe", env_data.get("TIMEFRAME", _deep_get(yaml_data, "trading.timeframe", TradingConfig.timeframe))
        ),
        symbol=overrides.get(
            "trading.symbol", env_data.get("SYMBOL", _deep_get(yaml_data, "trading.symbol", TradingConfig.symbol))
        ),
        leverage=float(
            overrides.get(
                "trading.leverage",
                env_data.get("LEVERAGE", _deep_get(yaml_data, "trading.leverage", TradingConfig.leverage)),
            )
        ),
        risk_pct=float(
            overrides.get(
                "trading.risk_pct",
                env_data.get("RISK_PCT", _deep_get(yaml_data, "trading.risk_pct", TradingConfig.risk_pct)),
            )
        ),
        daily_loss_limit_pct=float(
            overrides.get(
                "trading.daily_loss_limit_pct",
                env_data.get(
                    "DAILY_LOSS_LIMIT_PCT",
                    _deep_get(yaml_data, "trading.daily_loss_limit_pct", TradingConfig.daily_loss_limit_pct),
                ),
            )
        ),
        max_positions=int(
            overrides.get(
                "trading.max_positions",
                env_data.get("MAX_POSITIONS", _deep_get(yaml_data, "trading.max_positions", TradingConfig.max_positions)),
            )
        ),
        atr=ATRConfig(
            window=int(
                overrides.get(
                    "trading.atr.window",
                    env_data.get("ATR_WINDOW", _deep_get(yaml_data, "trading.atr.window", TradingConfig.atr.window)),
                )
            ),
            k_sl=float(
                overrides.get(
                    "trading.atr.k_sl",
                    env_data.get("ATR_K_SL", _deep_get(yaml_data, "trading.atr.k_sl", TradingConfig.atr.k_sl)),
                )
            ),
            k_tp=float(
                overrides.get(
                    "trading.atr.k_tp",
                    env_data.get("ATR_K_TP", _deep_get(yaml_data, "trading.atr.k_tp", TradingConfig.atr.k_tp)),
                )
            ),
        ),
        order=OrderConfig(
            ladder_levels=int(
                overrides.get(
                    "trading.order.ladder_levels",
                    env_data.get(
                        "ORDER_LADDER_LEVELS",
                        _deep_get(yaml_data, "trading.order.ladder_levels", TradingConfig.order.ladder_levels),
                    ),
                )
            ),
            timeout_bars=int(
                overrides.get(
                    "trading.order.timeout_bars",
                    env_data.get(
                        "ORDER_TIMEOUT_BARS",
                        _deep_get(yaml_data, "trading.order.timeout_bars", TradingConfig.order.timeout_bars),
                    ),
                )
            ),
            post_only=_parse_bool(
                overrides.get(
                    "trading.order.post_only",
                    env_data.get(
                        "ORDER_POST_ONLY",
                        _deep_get(yaml_data, "trading.order.post_only", OrderConfig().post_only),
                    ),
                ),
                OrderConfig().post_only,
            ),
        ),
        venue=VenueConfig(
            name=overrides.get(
                "trading.venue.name",
                env_data.get("EXCHANGE", _deep_get(yaml_data, "trading.venue.name", TradingConfig.venue.name)),
            ),
            testnet=_parse_bool(
                overrides.get(
                    "trading.venue.testnet",
                    env_data.get(
                        "VENUE_TESTNET",
                        _deep_get(yaml_data, "trading.venue.testnet", VenueConfig().testnet),
                    ),
                ),
                VenueConfig().testnet,
            ),
        ),
        tau=float(
            overrides.get(
                "trading.tau",
                env_data.get("TAU", _deep_get(yaml_data, "trading.tau", TradingConfig.tau)),
            )
        ),
    )

    telegram_chat_id = overrides.get(
        "monitoring.telegram.chat_id",
        env_data.get(
            "TELEGRAM_CHAT_ID",
            _deep_get(yaml_data, "monitoring.telegram.chat_id", TelegramConfig().chat_id),
        ),
    )
    if telegram_chat_id not in (None, ""):
        try:
            telegram_chat_id = int(telegram_chat_id)
        except (TypeError, ValueError):
            telegram_chat_id = str(telegram_chat_id)
    else:
        telegram_chat_id = None

    monitoring = MonitoringConfig(
        telegram=TelegramConfig(
            enabled=_parse_bool(
                overrides.get(
                    "monitoring.telegram.enabled",
                    env_data.get(
                        "TELEGRAM_ENABLED",
                        _deep_get(yaml_data, "monitoring.telegram.enabled", TelegramConfig().enabled),
                    ),
                ),
                TelegramConfig().enabled,
            ),
            chat_id=telegram_chat_id,
        )
    )

    return Config(trading=trading, monitoring=monitoring, raw={"env": env_data, "yaml": yaml_data})


__all__ = [
    "ATRConfig",
    "Config",
    "DEFAULT_TAU",
    "MonitoringConfig",
    "OrderConfig",
    "TelegramConfig",
    "TradingConfig",
    "VenueConfig",
    "load_config",
]
