from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from db.bootstrap import prepare_database
from db.executor import execute_db_operation, execute_raw_sql
from db.pool import DatabaseConnectionPool, normalize_db_path
from utils.config_utils import AppSettings, get_settings

logger = logging.getLogger(__name__)


class DatabaseRuntime:
    def __init__(
        self,
        *,
        db_path: str,
        max_connections: int,
        project_root: str,
        sql_path: Optional[str] = None,
    ) -> None:
        self.project_root = project_root
        self.db_path = normalize_db_path(db_path, project_root)
        self.max_connections = max_connections
        self.sql_path = sql_path or os.path.join(project_root, "data", "database.sql")
        self.pool: Optional[DatabaseConnectionPool] = None
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        prepare_database(self.db_path, self.sql_path)
        self.pool = DatabaseConnectionPool(self.db_path, self.max_connections)
        self._initialized = True

    def query(self, command: str, params: tuple = ()) -> list[Any]:
        self.initialize()
        if not self.pool:
            return []
        return execute_db_operation(self.pool, "query", command, params)

    def execute(self, command: str, params: tuple = ()) -> int:
        self.initialize()
        if not self.pool:
            return 0
        return int(execute_db_operation(self.pool, "update", command, params))

    def execute_raw(self, command: str) -> list[Any] | int | str:
        self.initialize()
        if not self.pool:
            return "Database pool not initialized"
        return execute_raw_sql(self.pool, command)

    def close(self) -> None:
        if self.pool:
            self.pool.close_all()
        self.pool = None
        self._initialized = False

    def checkpoint(self) -> bool:
        self.initialize()
        if not self.pool:
            return False
        return self.pool.trigger_wal_checkpoint()


_runtime: Optional[DatabaseRuntime] = None


def _build_runtime_from_settings(settings: AppSettings) -> DatabaseRuntime:
    return DatabaseRuntime(
        db_path=settings.database.path,
        max_connections=settings.database.max_connections,
        project_root=settings.project_root,
    )


def initialize_database_runtime(
    settings: Optional[AppSettings] = None,
    *,
    db_path: Optional[str] = None,
    max_connections: Optional[int] = None,
    project_root: Optional[str] = None,
    sql_path: Optional[str] = None,
) -> DatabaseRuntime:
    global _runtime

    if db_path is not None and max_connections is not None and project_root is not None:
        runtime = DatabaseRuntime(
            db_path=db_path,
            max_connections=max_connections,
            project_root=project_root,
            sql_path=sql_path,
        )
    else:
        runtime_settings = settings or get_settings()
        runtime = _build_runtime_from_settings(runtime_settings)

    runtime.initialize()
    _runtime = runtime
    return runtime


def get_database_runtime(settings: Optional[AppSettings] = None) -> DatabaseRuntime:
    global _runtime
    if _runtime is None:
        runtime_settings = settings or get_settings()
        _runtime = _build_runtime_from_settings(runtime_settings)
    return _runtime


def close_database_runtime() -> None:
    global _runtime
    if _runtime is None:
        return
    _runtime.close()
    _runtime = None


def manual_wal_checkpoint() -> bool:
    return get_database_runtime().checkpoint()
