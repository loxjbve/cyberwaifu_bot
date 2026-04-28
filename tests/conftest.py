from __future__ import annotations

import sqlite3
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.config_utils import AppSettings, DatabaseSettings, FeatureFlags, WebSettings


def build_settings(
    *,
    telegram_token: str = "test-token",
    admin_password: str = "admin-pass",
    viewer_password: str = "viewer-pass",
    secret_key: str = "secret-key",
    admin_ids: tuple[int, ...] = (999,),
    database_path: str = "test.db",
) -> AppSettings:
    return AppSettings(
        project_root=str(PROJECT_ROOT),
        raw={},
        default_config_path="default.json",
        config_path="config.json",
        config_local_path="config_local.json",
        telegram_token=telegram_token,
        admin_ids=admin_ids,
        default_api="default-api",
        default_char="default-char",
        default_preset="default-preset",
        default_stream="no",
        default_frequency=200,
        default_balance=1.5,
        database=DatabaseSettings(path=database_path, max_connections=5),
        web=WebSettings(
            admin_password=admin_password,
            viewer_password=viewer_password,
            secret_key=secret_key,
            host="127.0.0.1",
            port=8081,
            debug=False,
            session_timeout=3600,
            max_login_attempts=5,
            lockout_duration=300,
        ),
        features=FeatureFlags(start_web=True, start_monitor=True),
    )


@pytest.fixture
def settings_factory():
    return build_settings


@pytest.fixture
def sqlite_backend(tmp_path, monkeypatch):
    connection = sqlite3.connect(tmp_path / "test.db")
    schema = (PROJECT_ROOT / "data" / "database.sql").read_text(encoding="utf-8")
    connection.executescript(schema)
    connection.commit()

    def query_db(command: str, params=()):
        cursor = connection.execute(command, params)
        return cursor.fetchall()

    def revise_db(command: str, params=()):
        cursor = connection.execute(command, params)
        connection.commit()
        return cursor.rowcount

    def get_all_table_names():
        rows = query_db(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in rows]

    import bot_core.data_repository.conversations_repository as conversations_repository
    import bot_core.data_repository.groups_repository as groups_repository
    import bot_core.data_repository.user_config_repository as user_config_repository
    import bot_core.data_repository.user_profiles_repository as user_profiles_repository
    import bot_core.data_repository.users_repository as users_repository
    import web.services.admin_query_service as admin_query_service
    import web.services.user_admin_service as user_admin_service

    modules = [
        conversations_repository,
        groups_repository,
        user_config_repository,
        user_profiles_repository,
        users_repository,
        admin_query_service,
        user_admin_service,
    ]
    for module in modules:
        monkeypatch.setattr(module, "query_db", query_db, raising=False)
        monkeypatch.setattr(module, "revise_db", revise_db, raising=False)

    monkeypatch.setattr(admin_query_service, "get_all_table_names", get_all_table_names)
    monkeypatch.setattr(admin_query_service, "get_table_data", lambda *args, **kwargs: {})

    yield {
        "connection": connection,
        "query_db": query_db,
        "revise_db": revise_db,
    }

    connection.close()
