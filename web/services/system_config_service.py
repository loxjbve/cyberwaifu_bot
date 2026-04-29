from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Callable

from utils.config_utils import AppSettings, get_settings, load_settings


def _deep_get(source: dict[str, Any], path: str, default: Any = None) -> Any:
    value: Any = source
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return default
    return value


def _deep_set(target: dict[str, Any], path: str, value: Any) -> None:
    cursor = target
    parts = path.split(".")
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    cursor[parts[-1]] = value


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = deepcopy(value)


class SystemConfigService:
    RESTART_REQUIRED_LABELS = {
        "TG_TOKEN": "Bot Token",
        "flask.secret_key": "Flask Secret Key",
        "web.host": "Web Host",
        "web.port": "Web Port",
        "web.debug": "Web Debug",
        "database.default_path": "Database Path",
        "database.max_connections": "Database Max Connections",
        "paths.characters_path": "Characters Path",
        "paths.prompt_path": "Prompt Path",
        "features.start_web": "Start Web",
        "features.start_monitor": "Start Monitor",
        "plugins.enabled": "Plugins Enabled",
        "plugins.items.trading.lifecycle.monitor.enabled": "Trading Monitor Enabled",
    }
    LEGACY_AUTH_KEYS = ("ADMIN", "WEB_PW", "VIEWER_PW")

    def __init__(
        self,
        project_root: str,
        *,
        settings_provider: Callable[..., AppSettings] = get_settings,
        settings_reloader: Callable[..., AppSettings] = load_settings,
    ) -> None:
        self.project_root = project_root
        self.settings_provider = settings_provider
        self.settings_reloader = settings_reloader

    @property
    def restart_required_fields(self) -> list[str]:
        return list(self.RESTART_REQUIRED_LABELS.keys())

    def get_payload(self) -> dict[str, Any]:
        active_raw = deepcopy(self._settings().raw)
        config = self._build_form_config(active_raw)
        options = self._build_options(active_raw, config)
        return {
            "config": config,
            "options": options,
            "config_local_path": self._settings().config_local_path,
            "restart_required_fields": self.restart_required_fields,
            "restart_required_labels": self.RESTART_REQUIRED_LABELS,
        }

    def save_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("JSON object required")

        current_effective = self._build_form_config(deepcopy(self._settings().raw))
        candidate = deepcopy(current_effective)
        _deep_update(candidate, payload)
        validated = self._validate_config(candidate)

        local_data = self._load_local_data()
        self._apply_managed_config(local_data, validated)
        self._write_local_data(local_data)
        self.settings_reloader(force_reload=True)

        changed_restart_fields = [
            field
            for field in self.restart_required_fields
            if _deep_get(current_effective, field) != _deep_get(validated, field)
        ]
        return {
            "success": True,
            "message": "Saved",
            "restart_required": bool(changed_restart_fields),
            "restart_required_fields": changed_restart_fields,
            "restart_required_labels": {
                field: self.RESTART_REQUIRED_LABELS[field] for field in changed_restart_fields
            },
        }

    def _settings(self) -> AppSettings:
        return self.settings_provider()

    def _config_local_path(self) -> str:
        settings = self._settings()
        if settings.config_local_path:
            return settings.config_local_path
        return os.path.join(self.project_root, "config", "config_local.json")

    def _load_local_data(self) -> dict[str, Any]:
        local_path = self._config_local_path()
        if not os.path.exists(local_path):
            return {}
        with open(local_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError("config_local.json must contain a JSON object")
        return data

    def _write_local_data(self, payload: dict[str, Any]) -> None:
        local_path = self._config_local_path()
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def _build_form_config(self, active_raw: dict[str, Any]) -> dict[str, Any]:
        auth = active_raw.get("auth", {}) if isinstance(active_raw.get("auth"), dict) else {}
        api_list = self._normalize_api_list(active_raw.get("api_list", []))
        fallback_api = api_list[0]["name"] if api_list else ""
        default_api = str(_deep_get(active_raw, "api.default_api", fallback_api) or fallback_api)
        config = {
            "TG_TOKEN": str(active_raw.get("TG_TOKEN", "") or ""),
            "auth": {
                "ADMIN": [int(admin_id) for admin_id in auth.get("ADMIN", []) or []],
                "WEB_PW": str(auth.get("WEB_PW", active_raw.get("WEB_PW", "")) or ""),
                "VIEWER_PW": str(
                    auth.get("VIEWER_PW", active_raw.get("VIEWER_PW", "")) or ""
                ),
            },
            "flask": {
                "secret_key": str(_deep_get(active_raw, "flask.secret_key", "") or ""),
            },
            "web": {
                "host": str(_deep_get(active_raw, "web.host", "0.0.0.0") or "0.0.0.0"),
                "port": int(_deep_get(active_raw, "web.port", 8081) or 8081),
                "debug": bool(_deep_get(active_raw, "web.debug", False)),
            },
            "session": {
                "timeout": int(_deep_get(active_raw, "session.timeout", 3600) or 3600),
            },
            "security": {
                "max_login_attempts": int(
                    _deep_get(active_raw, "security.max_login_attempts", 5) or 5
                ),
                "lockout_duration": int(
                    _deep_get(active_raw, "security.lockout_duration", 300) or 300
                ),
            },
            "api": {
                "default_api": default_api,
                "max_tokens": int(_deep_get(active_raw, "api.max_tokens", 8000) or 8000),
                "semaphore_limit": int(
                    _deep_get(active_raw, "api.semaphore_limit", 5) or 5
                ),
            },
            "analysis": {
                "default_api": str(
                    _deep_get(active_raw, "analysis.default_api", default_api) or default_api
                ),
            },
            "fuck_or_not_api": str(active_raw.get("fuck_or_not_api", default_api) or default_api),
            "q_command_api": str(
                active_raw.get("q_command_api", _deep_get(active_raw, "api.q_command_api", default_api))
                or _deep_get(active_raw, "api.q_command_api", default_api)
                or default_api
            ),
            "api_list": api_list,
            "user": {
                "default_char": str(_deep_get(active_raw, "user.default_char", "") or ""),
                "default_preset": str(_deep_get(active_raw, "user.default_preset", "") or ""),
                "default_stream": str(_deep_get(active_raw, "user.default_stream", "no") or "no"),
                "default_frequency": int(
                    _deep_get(active_raw, "user.default_frequency", 200) or 200
                ),
                "default_balance": float(
                    _deep_get(active_raw, "user.default_balance", 1.5) or 1.5
                ),
            },
            "dialog": {
                "private_history_limit": int(
                    _deep_get(active_raw, "dialog.private_history_limit", 60) or 60
                ),
                "group_history_limit": int(
                    _deep_get(active_raw, "dialog.group_history_limit", 10) or 10
                ),
            },
            "group": {
                "default_rate": float(_deep_get(active_raw, "group.default_rate", 0.05) or 0.05),
            },
            "sign": {
                "default_frequency": int(
                    _deep_get(active_raw, "sign.default_frequency", 50) or 50
                ),
                "max_frequency": int(_deep_get(active_raw, "sign.max_frequency", 100) or 100),
            },
            "database": {
                "default_path": str(
                    _deep_get(active_raw, "database.default_path", "./data/data.db")
                    or "./data/data.db"
                ),
                "max_connections": int(
                    _deep_get(active_raw, "database.max_connections", 5) or 5
                ),
            },
            "paths": {
                "characters_path": str(
                    _deep_get(active_raw, "paths.characters_path", "./characters")
                    or "./characters"
                ),
                "prompt_path": str(
                    _deep_get(active_raw, "paths.prompt_path", "./prompts/prompts.json")
                    or "./prompts/prompts.json"
                ),
            },
            "features": {
                "start_web": bool(_deep_get(active_raw, "features.start_web", True)),
                "start_monitor": bool(_deep_get(active_raw, "features.start_monitor", True)),
            },
            "plugins": {
                "enabled": bool(_deep_get(active_raw, "plugins.enabled", True)),
                "items": {
                    "trading": {
                        "lifecycle": {
                            "monitor": {
                                "enabled": bool(
                                    _deep_get(
                                        active_raw,
                                        "plugins.items.trading.lifecycle.monitor.enabled",
                                        _deep_get(active_raw, "features.start_monitor", True),
                                    )
                                ),
                            }
                        }
                    }
                },
            },
        }
        return config

    def _build_options(
        self,
        active_raw: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        api_names = [item["name"] for item in config["api_list"] if item.get("name")]
        characters = self._list_characters(
            self._resolve_configured_path(_deep_get(active_raw, "paths.characters_path", "./characters"))
        )
        presets = self._list_presets(
            self._resolve_configured_path(
                _deep_get(active_raw, "paths.prompt_path", "./prompts/prompts.json")
            )
        )
        return {
            "api_names": self._with_current_value(
                api_names,
                [
                    _deep_get(config, "api.default_api", ""),
                    _deep_get(config, "analysis.default_api", ""),
                    config.get("fuck_or_not_api", ""),
                    config.get("q_command_api", ""),
                ],
            ),
            "characters": self._with_current_value(
                characters,
                [_deep_get(config, "user.default_char", "")],
            ),
            "presets": self._with_current_preset(
                presets,
                _deep_get(config, "user.default_preset", ""),
            ),
        }

    @staticmethod
    def _with_current_value(options: list[str], current_values: list[str]) -> list[str]:
        result = [item for item in options if item]
        for value in current_values:
            if value and value not in result:
                result.append(value)
        return sorted(result)

    @staticmethod
    def _with_current_preset(
        options: list[dict[str, str]],
        current_value: str,
    ) -> list[dict[str, str]]:
        if current_value and all(option.get("name") != current_value for option in options):
            options = [*options, {"name": current_value, "display": current_value}]
        return sorted(options, key=lambda item: item.get("display", item.get("name", "")))

    def _resolve_configured_path(self, value: str) -> str:
        if os.path.isabs(value):
            return value
        return os.path.join(self.project_root, value.lstrip("./"))

    @staticmethod
    def _normalize_api_list(api_list: Any) -> list[dict[str, Any]]:
        if not isinstance(api_list, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in api_list:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "name": str(item.get("name", "") or ""),
                    "key": str(item.get("key", "") or ""),
                    "url": str(item.get("url", "") or ""),
                    "model": str(item.get("model", "") or ""),
                    "group": int(item.get("group", 0) or 0),
                    "multiple": int(item.get("multiple", 1) or 1),
                }
            )
        return normalized

    @staticmethod
    def _list_characters(characters_path: str) -> list[str]:
        if not os.path.isdir(characters_path):
            return []
        result: list[str] = []
        for filename in os.listdir(characters_path):
            name, ext = os.path.splitext(filename)
            if ext.lower() not in {".json", ".txt"}:
                continue
            result.append(name)
        return sorted(set(result))

    @staticmethod
    def _list_presets(prompt_path: str) -> list[dict[str, str]]:
        if not os.path.exists(prompt_path):
            return []
        try:
            with open(prompt_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []

        preset_list = payload.get("prompt_set_list", [])
        if not isinstance(preset_list, list):
            return []

        result: list[dict[str, str]] = []
        for item in preset_list:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()
            if not name:
                continue
            display = str(item.get("display", name) or name).strip()
            result.append({"name": name, "display": display})
        return result

    def _validate_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_list = self._validate_api_list(payload.get("api_list", []))
        api_names = [item["name"] for item in api_list]
        auth = payload.get("auth", {}) if isinstance(payload.get("auth"), dict) else {}

        validated = {
            "TG_TOKEN": self._as_string(payload.get("TG_TOKEN", "")),
            "auth": {
                "ADMIN": self._validate_admin_ids(auth.get("ADMIN", [])),
                "WEB_PW": self._require_string(auth.get("WEB_PW", ""), "Admin password"),
                "VIEWER_PW": self._require_string(
                    auth.get("VIEWER_PW", ""),
                    "Viewer password",
                ),
            },
            "flask": {
                "secret_key": self._require_string(
                    _deep_get(payload, "flask.secret_key", ""),
                    "Flask secret key",
                ),
            },
            "web": {
                "host": self._require_string(_deep_get(payload, "web.host", ""), "Web host"),
                "port": self._require_int(_deep_get(payload, "web.port", 8081), "Web port", minimum=1, maximum=65535),
                "debug": bool(_deep_get(payload, "web.debug", False)),
            },
            "session": {
                "timeout": self._require_int(
                    _deep_get(payload, "session.timeout", 3600),
                    "Session timeout",
                    minimum=60,
                ),
            },
            "security": {
                "max_login_attempts": self._require_int(
                    _deep_get(payload, "security.max_login_attempts", 5),
                    "Max login attempts",
                    minimum=1,
                ),
                "lockout_duration": self._require_int(
                    _deep_get(payload, "security.lockout_duration", 300),
                    "Lockout duration",
                    minimum=1,
                ),
            },
            "api": {
                "default_api": self._require_choice(
                    _deep_get(payload, "api.default_api", ""),
                    "Default API",
                    api_names,
                ),
                "max_tokens": self._require_int(
                    _deep_get(payload, "api.max_tokens", 8000),
                    "Max tokens",
                    minimum=1,
                ),
                "semaphore_limit": self._require_int(
                    _deep_get(payload, "api.semaphore_limit", 5),
                    "Semaphore limit",
                    minimum=1,
                ),
            },
            "analysis": {
                "default_api": self._require_choice(
                    _deep_get(payload, "analysis.default_api", ""),
                    "Analysis default API",
                    api_names,
                ),
            },
            "fuck_or_not_api": self._require_choice(
                payload.get("fuck_or_not_api", ""),
                "Image rating API",
                api_names,
            ),
            "q_command_api": self._require_choice(
                payload.get("q_command_api", ""),
                "Q command API",
                api_names,
            ),
            "api_list": api_list,
            "user": {
                "default_char": self._require_string(
                    _deep_get(payload, "user.default_char", ""),
                    "Default character",
                ),
                "default_preset": self._require_string(
                    _deep_get(payload, "user.default_preset", ""),
                    "Default preset",
                ),
                "default_stream": self._require_choice(
                    _deep_get(payload, "user.default_stream", "no"),
                    "Default stream",
                    ["yes", "no"],
                ),
                "default_frequency": self._require_int(
                    _deep_get(payload, "user.default_frequency", 200),
                    "Default frequency",
                    minimum=0,
                ),
                "default_balance": self._require_float(
                    _deep_get(payload, "user.default_balance", 1.5),
                    "Default balance",
                    minimum=0,
                ),
            },
            "dialog": {
                "private_history_limit": self._require_int(
                    _deep_get(payload, "dialog.private_history_limit", 60),
                    "Private history limit",
                    minimum=1,
                ),
                "group_history_limit": self._require_int(
                    _deep_get(payload, "dialog.group_history_limit", 10),
                    "Group history limit",
                    minimum=1,
                ),
            },
            "group": {
                "default_rate": self._require_float(
                    _deep_get(payload, "group.default_rate", 0.05),
                    "Default group rate",
                    minimum=0,
                    maximum=1,
                ),
            },
            "sign": {
                "default_frequency": self._require_int(
                    _deep_get(payload, "sign.default_frequency", 50),
                    "Default sign frequency",
                    minimum=0,
                ),
                "max_frequency": self._require_int(
                    _deep_get(payload, "sign.max_frequency", 100),
                    "Max sign frequency",
                    minimum=1,
                ),
            },
            "database": {
                "default_path": self._require_string(
                    _deep_get(payload, "database.default_path", ""),
                    "Database path",
                ),
                "max_connections": self._require_int(
                    _deep_get(payload, "database.max_connections", 5),
                    "Database max connections",
                    minimum=1,
                ),
            },
            "paths": {
                "characters_path": self._require_string(
                    _deep_get(payload, "paths.characters_path", ""),
                    "Characters path",
                ),
                "prompt_path": self._require_string(
                    _deep_get(payload, "paths.prompt_path", ""),
                    "Prompt path",
                ),
            },
            "features": {
                "start_web": bool(_deep_get(payload, "features.start_web", True)),
                "start_monitor": bool(_deep_get(payload, "features.start_monitor", True)),
            },
            "plugins": {
                "enabled": bool(_deep_get(payload, "plugins.enabled", True)),
                "items": {
                    "trading": {
                        "lifecycle": {
                            "monitor": {
                                "enabled": bool(
                                    _deep_get(
                                        payload,
                                        "plugins.items.trading.lifecycle.monitor.enabled",
                                        True,
                                    )
                                ),
                            }
                        }
                    }
                },
            },
        }
        return validated

    @staticmethod
    def _as_string(value: Any) -> str:
        return str(value or "").strip()

    def _require_string(self, value: Any, label: str) -> str:
        text = self._as_string(value)
        if not text:
            raise ValueError(f"{label} is required")
        return text

    def _require_int(
        self,
        value: Any,
        label: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} must be an integer") from error
        if minimum is not None and result < minimum:
            raise ValueError(f"{label} must be >= {minimum}")
        if maximum is not None and result > maximum:
            raise ValueError(f"{label} must be <= {maximum}")
        return result

    def _require_float(
        self,
        value: Any,
        label: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} must be a number") from error
        if minimum is not None and result < minimum:
            raise ValueError(f"{label} must be >= {minimum}")
        if maximum is not None and result > maximum:
            raise ValueError(f"{label} must be <= {maximum}")
        return result

    def _require_choice(self, value: Any, label: str, choices: list[str]) -> str:
        text = self._require_string(value, label)
        if text not in choices:
            raise ValueError(f"{label} must be one of: {', '.join(choices)}")
        return text

    def _validate_admin_ids(self, value: Any) -> list[int]:
        if not isinstance(value, list):
            raise ValueError("Admin IDs must be a list")
        admin_ids: list[int] = []
        for item in value:
            try:
                admin_ids.append(int(item))
            except (TypeError, ValueError) as error:
                raise ValueError("Admin IDs must contain integers") from error
        return admin_ids

    def _validate_api_list(self, value: Any) -> list[dict[str, Any]]:
        normalized = self._normalize_api_list(value)
        if not normalized:
            raise ValueError("API list must contain at least one item")

        names: set[str] = set()
        validated: list[dict[str, Any]] = []
        for index, item in enumerate(normalized, start=1):
            name = self._require_string(item.get("name", ""), f"API #{index} name")
            if name in names:
                raise ValueError(f"Duplicate API name: {name}")
            names.add(name)
            validated.append(
                {
                    "name": name,
                    "key": self._as_string(item.get("key", "")),
                    "url": self._require_string(item.get("url", ""), f"API #{index} url"),
                    "model": self._require_string(item.get("model", ""), f"API #{index} model"),
                    "group": self._require_int(item.get("group", 0), f"API #{index} group"),
                    "multiple": self._require_int(
                        item.get("multiple", 1),
                        f"API #{index} multiple",
                        minimum=1,
                    ),
                }
            )
        return validated

    def _apply_managed_config(self, target: dict[str, Any], validated: dict[str, Any]) -> None:
        for legacy_key in self.LEGACY_AUTH_KEYS:
            target.pop(legacy_key, None)

        managed_paths = {
            "TG_TOKEN": validated["TG_TOKEN"],
            "auth.ADMIN": validated["auth"]["ADMIN"],
            "auth.WEB_PW": validated["auth"]["WEB_PW"],
            "auth.VIEWER_PW": validated["auth"]["VIEWER_PW"],
            "flask.secret_key": validated["flask"]["secret_key"],
            "web.host": validated["web"]["host"],
            "web.port": validated["web"]["port"],
            "web.debug": validated["web"]["debug"],
            "session.timeout": validated["session"]["timeout"],
            "security.max_login_attempts": validated["security"]["max_login_attempts"],
            "security.lockout_duration": validated["security"]["lockout_duration"],
            "api.default_api": validated["api"]["default_api"],
            "api.max_tokens": validated["api"]["max_tokens"],
            "api.semaphore_limit": validated["api"]["semaphore_limit"],
            "analysis.default_api": validated["analysis"]["default_api"],
            "fuck_or_not_api": validated["fuck_or_not_api"],
            "q_command_api": validated["q_command_api"],
            "api_list": validated["api_list"],
            "user.default_char": validated["user"]["default_char"],
            "user.default_preset": validated["user"]["default_preset"],
            "user.default_stream": validated["user"]["default_stream"],
            "user.default_frequency": validated["user"]["default_frequency"],
            "user.default_balance": validated["user"]["default_balance"],
            "dialog.private_history_limit": validated["dialog"]["private_history_limit"],
            "dialog.group_history_limit": validated["dialog"]["group_history_limit"],
            "group.default_rate": validated["group"]["default_rate"],
            "sign.default_frequency": validated["sign"]["default_frequency"],
            "sign.max_frequency": validated["sign"]["max_frequency"],
            "database.default_path": validated["database"]["default_path"],
            "database.max_connections": validated["database"]["max_connections"],
            "paths.characters_path": validated["paths"]["characters_path"],
            "paths.prompt_path": validated["paths"]["prompt_path"],
            "features.start_web": validated["features"]["start_web"],
            "features.start_monitor": validated["features"]["start_monitor"],
            "plugins.enabled": validated["plugins"]["enabled"],
            "plugins.items.trading.lifecycle.monitor.enabled": _deep_get(
                validated,
                "plugins.items.trading.lifecycle.monitor.enabled",
                True,
            ),
        }
        for path, value in managed_paths.items():
            _deep_set(target, path, deepcopy(value))
