from __future__ import annotations

import logging
import os
import sqlite3
import threading
from sqlite3 import Error
from typing import Optional

logger = logging.getLogger(__name__)


def normalize_db_path(db_file: str, project_root: str) -> str:
    if os.path.isabs(db_file):
        return db_file
    return os.path.join(project_root, db_file.lstrip("./"))


class DatabaseConnectionPool:
    """Thread-safe SQLite connection pool."""

    def __init__(self, db_file: str, max_connections: int) -> None:
        self.db_file = db_file
        self.max_connections = max_connections or 5
        self.connections: list[sqlite3.Connection] = []
        self.connection_locks: list[threading.Lock] = []
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        for _ in range(self.max_connections):
            self.connections.append(self._new_connection())
            self.connection_locks.append(threading.Lock())

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_file,
            check_same_thread=False,
            timeout=30.0,
        )
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.commit()
        return conn

    def get_connection(self) -> tuple[Optional[sqlite3.Connection], int]:
        for index, lock in enumerate(self.connection_locks):
            if lock.acquire(blocking=False):
                return self.connections[index], index

        try:
            return self._new_connection(), -1
        except Error as error:
            logger.error("Failed to create temporary database connection: %s", error)
            return None, -1

    def release_connection(self, index: int) -> None:
        if 0 <= index < len(self.connection_locks):
            self.connection_locks[index].release()

    def close_all(self) -> None:
        for conn in self.connections:
            try:
                conn.close()
            except Error:
                pass
        self.connections = []
        self.connection_locks = []

    def trigger_wal_checkpoint(self) -> bool:
        conn, conn_index = self.get_connection()
        if not conn:
            logger.error("Unable to acquire database connection for WAL checkpoint")
            return False

        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            logger.info("Triggered WAL checkpoint")
            return True
        except sqlite3.Error as error:
            logger.error("Failed to trigger WAL checkpoint: %s", error)
            return False
        finally:
            if conn_index >= 0:
                self.release_connection(conn_index)
            else:
                conn.close()
