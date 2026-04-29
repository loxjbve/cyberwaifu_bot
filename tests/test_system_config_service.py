from __future__ import annotations

import json
import time
from pathlib import Path

from flask import Flask

from utils.config_utils import AppSettings, DatabaseSettings, FeatureFlags, WebSettings
from utils import auth_utils
from web.blueprints import api as api_module
from web.blueprints.api import api_bp
from web.services.system_config_service import SystemConfigService


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _build_raw_config() -> dict:
    return {
        "TG_TOKEN": "token-1",
        "auth": {
            "ADMIN": [7001],
            "WEB_PW": "admin-pass",
            "VIEWER_PW": "viewer-pass",
        },
        "flask": {
            "secret_key": "secret-key",
            "session_cookie_secure": False,
        },
        "web": {
            "host": "127.0.0.1",
            "port": 8081,
            "debug": False,
        },
        "session": {
            "timeout": 3600,
        },
        "security": {
            "max_login_attempts": 5,
            "lockout_duration": 300,
        },
        "api": {
            "default_api": "primary",
            "max_tokens": 8000,
            "semaphore_limit": 5,
            "q_command_api": "backup",
        },
        "analysis": {
            "default_api": "backup",
        },
        "fuck_or_not_api": "primary",
        "q_command_api": "backup",
        "api_list": [
            {
                "name": "primary",
                "key": "key-1",
                "url": "https://example.com/primary",
                "model": "model-1",
                "group": 0,
                "multiple": 1,
            },
            {
                "name": "backup",
                "key": "key-2",
                "url": "https://example.com/backup",
                "model": "model-2",
                "group": 1,
                "multiple": 2,
            },
        ],
        "user": {
            "default_char": "hero_public",
            "default_preset": "Default_meeting",
            "default_stream": "no",
            "default_frequency": 200,
            "default_balance": 1.5,
        },
        "dialog": {
            "private_history_limit": 60,
            "group_history_limit": 10,
        },
        "group": {
            "default_rate": 0.05,
        },
        "sign": {
            "default_frequency": 50,
            "max_frequency": 100,
        },
        "database": {
            "default_path": "./data/data.db",
            "max_connections": 5,
        },
        "paths": {
            "characters_path": "./characters",
            "prompt_path": "./prompts/prompts.json",
            "config_path": "./config/config.json",
            "config_local": "./config/config_local.json",
        },
        "features": {
            "start_web": True,
            "start_monitor": True,
        },
        "plugins": {
            "enabled": True,
            "items": {
                "trading": {
                    "lifecycle": {
                        "monitor": {
                            "enabled": True,
                        }
                    }
                },
                "custom_plugin": {
                    "enabled": False,
                },
            },
        },
    }


def _build_settings(project_root: Path, raw: dict, local_path: Path) -> AppSettings:
    return AppSettings(
        project_root=str(project_root),
        raw=raw,
        default_config_path=str(project_root / "config" / "default_config.json"),
        config_path=str(project_root / "config" / "config.json"),
        config_local_path=str(local_path),
        telegram_token=str(raw.get("TG_TOKEN", "")),
        admin_ids=tuple(int(item) for item in raw.get("auth", {}).get("ADMIN", []) or []),
        default_api=str(raw.get("api", {}).get("default_api", "")),
        default_char=str(raw.get("user", {}).get("default_char", "")),
        default_preset=str(raw.get("user", {}).get("default_preset", "")),
        default_stream=str(raw.get("user", {}).get("default_stream", "no")),
        default_frequency=int(raw.get("user", {}).get("default_frequency", 200)),
        default_balance=float(raw.get("user", {}).get("default_balance", 1.5)),
        database=DatabaseSettings(
            path=str(raw.get("database", {}).get("default_path", "./data/data.db")),
            max_connections=int(raw.get("database", {}).get("max_connections", 5)),
        ),
        web=WebSettings(
            admin_password=str(raw.get("auth", {}).get("WEB_PW", "")),
            viewer_password=str(raw.get("auth", {}).get("VIEWER_PW", "")),
            secret_key=str(raw.get("flask", {}).get("secret_key", "")),
            host=str(raw.get("web", {}).get("host", "127.0.0.1")),
            port=int(raw.get("web", {}).get("port", 8081)),
            debug=bool(raw.get("web", {}).get("debug", False)),
            session_timeout=int(raw.get("session", {}).get("timeout", 3600)),
            max_login_attempts=int(raw.get("security", {}).get("max_login_attempts", 5)),
            lockout_duration=int(raw.get("security", {}).get("lockout_duration", 300)),
        ),
        features=FeatureFlags(
            start_web=bool(raw.get("features", {}).get("start_web", True)),
            start_monitor=bool(raw.get("features", {}).get("start_monitor", True)),
        ),
    )


def _prepare_project(tmp_path: Path) -> tuple[dict, AppSettings, Path]:
    raw = _build_raw_config()
    local_path = tmp_path / "config" / "config_local.json"
    _write_json(tmp_path / "config" / "config.json", {"example": True})
    _write_json(tmp_path / "characters" / "hero_public.json", {"name": "Hero"})
    _write_json(
        tmp_path / "prompts" / "prompts.json",
        {
            "prompt_set_list": [
                {"name": "Default_meeting", "display": "Default Meeting"},
                {"name": "Night_chat", "display": "Night Chat"},
            ]
        },
    )
    settings = _build_settings(tmp_path, raw, local_path)
    return raw, settings, local_path


def test_system_config_service_payload_returns_options_and_restart_fields(tmp_path):
    raw, settings, local_path = _prepare_project(tmp_path)
    service = SystemConfigService(
        str(tmp_path),
        settings_provider=lambda: settings,
        settings_reloader=lambda force_reload=True: settings,
    )

    payload = service.get_payload()

    assert payload["config"]["TG_TOKEN"] == raw["TG_TOKEN"]
    assert payload["options"]["api_names"] == ["backup", "primary"]
    assert payload["options"]["characters"] == ["hero_public"]
    assert payload["options"]["presets"][0]["name"] == "Default_meeting"
    assert payload["config_local_path"] == str(local_path)
    assert "TG_TOKEN" in payload["restart_required_fields"]


def test_system_config_service_creates_local_file_and_preserves_unknown_fields(tmp_path):
    raw, settings, local_path = _prepare_project(tmp_path)
    _write_json(
        local_path,
        {
            "custom": {"keep": True},
            "WEB_PW": "legacy-admin",
            "VIEWER_PW": "legacy-viewer",
            "ADMIN": [9000],
            "plugins": {
                "items": {
                    "custom_plugin": {
                        "enabled": False,
                    }
                }
            },
        },
    )

    reload_calls = []

    def _reload(force_reload=True):
        reload_calls.append(force_reload)
        return settings

    service = SystemConfigService(
        str(tmp_path),
        settings_provider=lambda: settings,
        settings_reloader=_reload,
    )
    payload = service.get_payload()["config"]
    payload["auth"]["ADMIN"] = [123, 456]
    payload["auth"]["WEB_PW"] = "new-admin"
    payload["auth"]["VIEWER_PW"] = "new-viewer"
    payload["api"]["default_api"] = "backup"
    payload["plugins"]["items"]["trading"]["lifecycle"]["monitor"]["enabled"] = False

    result = service.save_config(payload)
    saved = json.loads(local_path.read_text(encoding="utf-8"))

    assert reload_calls == [True]
    assert result["restart_required"] is True
    assert saved["custom"] == {"keep": True}
    assert saved["auth"]["ADMIN"] == [123, 456]
    assert saved["auth"]["WEB_PW"] == "new-admin"
    assert saved["auth"]["VIEWER_PW"] == "new-viewer"
    assert saved["api"]["default_api"] == "backup"
    assert saved["plugins"]["items"]["trading"]["lifecycle"]["monitor"]["enabled"] is False
    assert saved["plugins"]["items"]["custom_plugin"]["enabled"] is False
    assert "WEB_PW" not in saved
    assert "VIEWER_PW" not in saved
    assert "ADMIN" not in saved


def test_system_config_service_creates_missing_local_file(tmp_path):
    _, settings, local_path = _prepare_project(tmp_path)
    service = SystemConfigService(
        str(tmp_path),
        settings_provider=lambda: settings,
        settings_reloader=lambda force_reload=True: settings,
    )

    assert not local_path.exists()

    service.save_config(service.get_payload()["config"])

    assert local_path.exists()


def test_system_config_api_reads_and_writes_local_file(tmp_path, monkeypatch):
    _, settings, local_path = _prepare_project(tmp_path)
    _write_json(local_path, {"custom": {"keep": True}})

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = settings.web.secret_key
    app.register_blueprint(api_bp)

    monkeypatch.setattr(auth_utils, "get_settings", lambda force_reload=False: settings)
    monkeypatch.setattr(api_module, "get_settings", lambda force_reload=False: settings)
    monkeypatch.setattr(api_module, "load_settings", lambda force_reload=True: settings)

    client = app.test_client()
    with client.session_transaction() as session:
        session["logged_in"] = True
        session["user_permission"] = "admin"
        session["user_role"] = "admin"
        session["last_activity"] = time.time()

    get_response = client.get("/api/system-config")
    assert get_response.status_code == 200
    get_payload = get_response.get_json()
    assert get_payload["config"]["auth"]["WEB_PW"] == "admin-pass"

    payload = get_payload["config"]
    payload["auth"]["WEB_PW"] = "changed-admin"
    payload["api"]["default_api"] = "backup"

    put_response = client.put("/api/system-config", json=payload)
    assert put_response.status_code == 200
    assert put_response.get_json()["success"] is True

    saved = json.loads(local_path.read_text(encoding="utf-8"))
    assert saved["auth"]["WEB_PW"] == "changed-admin"
    assert saved["api"]["default_api"] == "backup"
    assert saved["custom"] == {"keep": True}
