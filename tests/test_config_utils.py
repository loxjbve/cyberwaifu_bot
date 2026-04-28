from __future__ import annotations

import json

import pytest

from utils import config_utils


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_settings_prefers_config_local_then_config(tmp_path):
    default_path = tmp_path / "default.json"
    config_path = tmp_path / "config.json"
    config_local_path = tmp_path / "config_local.json"

    _write_json(
        default_path,
        {
            "TG_TOKEN": "default-token",
            "auth": {"ADMIN": [1], "WEB_PW": "default-admin", "VIEWER_PW": "default-viewer"},
            "flask": {"secret_key": "default-secret"},
            "database": {"default_path": "./data/default.db", "max_connections": 5},
            "api": {"default_api": "default-api"},
            "user": {"default_char": "default-char", "default_preset": "default-preset"},
        },
    )
    _write_json(
        config_path,
        {
            "TG_TOKEN": "config-token",
            "auth": {"WEB_PW": "config-admin"},
            "api": {"default_api": "config-api"},
            "database": {"default_path": "./data/config.db"},
        },
    )
    _write_json(
        config_local_path,
        {
            "TG_TOKEN": "local-token",
            "auth": {"WEB_PW": "local-admin", "VIEWER_PW": "local-viewer"},
            "database": {"default_path": "./data/local.db"},
        },
    )

    settings = config_utils.load_settings(
        force_reload=True,
        default_config_path=str(default_path),
        config_path=str(config_path),
        config_local_path=str(config_local_path),
    )

    assert settings.telegram_token == "local-token"
    assert settings.web.admin_password == "local-admin"
    assert settings.web.viewer_password == "local-viewer"
    assert settings.default_api == "config-api"
    assert settings.database.path.endswith("data\\local.db") or settings.database.path.endswith(
        "data/local.db"
    )


def test_validate_settings_requires_runtime_secrets(settings_factory):
    settings = settings_factory(
        telegram_token="",
        admin_password="",
        viewer_password="viewer-pass",
        secret_key="",
    )

    with pytest.raises(ValueError, match="WEB_PW"):
        config_utils.validate_settings(settings)

    settings = settings_factory(
        telegram_token="",
        admin_password="admin-pass",
        viewer_password="viewer-pass",
        secret_key="secret-key",
    )

    with pytest.raises(ValueError, match="TG_TOKEN"):
        config_utils.validate_settings(settings, require_bot_token=True)
