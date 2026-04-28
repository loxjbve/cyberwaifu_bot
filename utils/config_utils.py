"""
Unified configuration loading and compatibility helpers.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(project_root, "config", "default_config.json")
CONFIG_PATH = os.path.join(project_root, "config", "config.json")
CONFIG_LOCAL_PATH = os.path.join(project_root, "config", "config_local.json")

_config: Dict[str, Any] = {}
_default_config: Dict[str, Any] = {}
_user_config: Dict[str, Any] = {}
_settings: Optional["AppSettings"] = None


@dataclass(frozen=True)
class DatabaseSettings:
    path: str
    max_connections: int


@dataclass(frozen=True)
class WebSettings:
    admin_password: str
    viewer_password: str
    secret_key: str
    host: str
    port: int
    debug: bool
    session_timeout: int
    max_login_attempts: int
    lockout_duration: int


@dataclass(frozen=True)
class FeatureFlags:
    start_web: bool
    start_monitor: bool


@dataclass(frozen=True)
class AppSettings:
    project_root: str
    raw: Dict[str, Any]
    default_config_path: str
    config_path: str
    config_local_path: str
    telegram_token: str
    admin_ids: tuple[int, ...]
    default_api: str
    default_char: str
    default_preset: str
    default_stream: str
    default_frequency: int
    default_balance: float
    database: DatabaseSettings
    web: WebSettings
    features: FeatureFlags

    def get(self, key: Optional[str] = None, default: Any = None) -> Any:
        if key is None:
            return self.raw

        value: Any = self.raw
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value


def load_json_file(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def _deep_update(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _resolve_paths(
    default_config_path: Optional[str],
    config_path: Optional[str],
    config_local_path: Optional[str],
) -> tuple[str, str, str]:
    return (
        default_config_path or DEFAULT_CONFIG_PATH,
        config_path or os.environ.get("CONFIG_PATH", CONFIG_PATH),
        config_local_path or os.environ.get("CONFIG_LOCAL_PATH", CONFIG_LOCAL_PATH),
    )


def _build_settings(
    merged_config: Dict[str, Any],
    default_config_path: str,
    config_path: str,
    config_local_path: str,
) -> AppSettings:
    database_path = os.environ.get("DB_PATH", get_path("default_path", merged_config))
    if database_path and not os.path.isabs(database_path):
        database_path = os.path.join(project_root, database_path.lstrip("./"))

    admin_ids_raw = merged_config.get("auth", {}).get("ADMIN", merged_config.get("ADMIN", []))
    admin_ids = tuple(int(admin_id) for admin_id in admin_ids_raw or [])

    return AppSettings(
        project_root=project_root,
        raw=merged_config,
        default_config_path=default_config_path,
        config_path=config_path,
        config_local_path=config_local_path,
        telegram_token=str(merged_config.get("TG_TOKEN", "") or ""),
        admin_ids=admin_ids,
        default_api=str(merged_config.get("api", {}).get("default_api", "gemini-2.5")),
        default_char=str(merged_config.get("user", {}).get("default_char", "cuicuishark_public")),
        default_preset=str(merged_config.get("user", {}).get("default_preset", "Default_meeting")),
        default_stream=str(merged_config.get("user", {}).get("default_stream", "no")),
        default_frequency=int(merged_config.get("user", {}).get("default_frequency", 200)),
        default_balance=float(merged_config.get("user", {}).get("default_balance", 1.5)),
        database=DatabaseSettings(
            path=database_path,
            max_connections=int(merged_config.get("database", {}).get("max_connections", 5)),
        ),
        web=WebSettings(
            admin_password=str(
                merged_config.get("auth", {}).get("WEB_PW", merged_config.get("WEB_PW", ""))
            ),
            viewer_password=str(
                merged_config.get("auth", {}).get(
                    "VIEWER_PW", merged_config.get("VIEWER_PW", "")
                )
            ),
            secret_key=str(merged_config.get("flask", {}).get("secret_key", "")),
            host=str(merged_config.get("web", {}).get("host", "0.0.0.0")),
            port=int(merged_config.get("web", {}).get("port", 8081)),
            debug=bool(merged_config.get("web", {}).get("debug", False)),
            session_timeout=int(merged_config.get("session", {}).get("timeout", 3600)),
            max_login_attempts=int(
                merged_config.get("security", {}).get("max_login_attempts", 5)
            ),
            lockout_duration=int(
                merged_config.get("security", {}).get("lockout_duration", 300)
            ),
        ),
        features=FeatureFlags(
            start_web=bool(merged_config.get("features", {}).get("start_web", True)),
            start_monitor=bool(merged_config.get("features", {}).get("start_monitor", True)),
        ),
    )


def load_settings(
    *,
    force_reload: bool = False,
    default_config_path: Optional[str] = None,
    config_path: Optional[str] = None,
    config_local_path: Optional[str] = None,
) -> AppSettings:
    global _config, _default_config, _user_config, _settings

    if _settings is not None and not force_reload:
        return _settings

    resolved_default_path, resolved_config_path, resolved_local_path = _resolve_paths(
        default_config_path,
        config_path,
        config_local_path,
    )

    try:
        _default_config = load_json_file(resolved_default_path)
    except Exception as error:
        logger.error("Failed to load default config: %s", error)
        _default_config = {}

    _user_config = {}
    try:
        if os.path.exists(resolved_config_path):
            _deep_update(_user_config, load_json_file(resolved_config_path))
            logger.info("Loaded config from %s", resolved_config_path)
        if os.path.exists(resolved_local_path):
            _deep_update(_user_config, load_json_file(resolved_local_path))
            logger.info("Loaded local config from %s", resolved_local_path)
    except Exception as error:
        logger.error("Failed to load user config: %s", error)
        _user_config = {}

    _config = dict(_default_config)
    _deep_update(_config, _user_config)

    _settings = _build_settings(
        merged_config=_config,
        default_config_path=resolved_default_path,
        config_path=resolved_config_path,
        config_local_path=resolved_local_path,
    )
    return _settings


def init_config() -> None:
    load_settings(force_reload=True)


def get_settings(force_reload: bool = False) -> AppSettings:
    return load_settings(force_reload=force_reload)


def get_config(key: Optional[str] = None, default: Any = None) -> Any:
    settings = load_settings()
    return settings.get(key, default)


def get_path(path_key: str, config: Optional[Dict[str, Any]] = None) -> str:
    source = config or get_config()
    path = source.get("database", {}).get(path_key) if path_key == "default_path" else source.get("paths", {}).get(path_key)
    if path and isinstance(path, str) and path.startswith("./"):
        return os.path.join(project_root, path[2:])
    return path or ""


def get_api_config(api_name: Optional[str] = None) -> tuple[str, str, str]:
    if api_name is None:
        api_name = get_config("api.default_api")

    api_list = get_config("api_list", [])
    for api_config_item in api_list:
        if api_config_item.get("name") == api_name:
            return (
                api_config_item.get("key", ""),
                api_config_item.get("url", ""),
                api_config_item.get("model", ""),
            )

    raise ValueError(f"未找到名为 '{api_name}' 的 API 配置")


def get_api_multiple(api_name: Optional[str] = None) -> int:
    if api_name is None:
        api_name = get_config("api.default_api")

    api_list = get_config("api_list", [])
    for api in api_list:
        if api.get("name") == api_name:
            return api.get("multiple", 1)

    return 1


def validate_settings(settings: Optional[AppSettings] = None, *, require_bot_token: bool = False) -> None:
    active_settings = settings or load_settings()

    if require_bot_token and not active_settings.telegram_token:
        raise ValueError("TG_TOKEN is required for bot runtime")
    if not active_settings.web.admin_password:
        raise ValueError("WEB_PW/auth.WEB_PW is required")
    if not active_settings.web.viewer_password:
        raise ValueError("VIEWER_PW/auth.VIEWER_PW is required")
    if not active_settings.web.secret_key:
        raise ValueError("flask.secret_key is required")


load_settings()

BOT_TOKEN = get_settings().telegram_token
ADMIN_LIST = list(get_settings().admin_ids)
DEFAULT_API = get_settings().default_api
DEFAULT_CHAR = get_settings().default_char
DEFAULT_PRESET = get_settings().default_preset
DEFAULT_STREAM = get_settings().default_stream
DEFAULT_FREQUENCY = get_settings().default_frequency
DEFAULT_BALANCE = get_settings().default_balance
