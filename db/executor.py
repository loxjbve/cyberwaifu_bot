from __future__ import annotations

import logging
import sqlite3
from typing import Any

from .pool import DatabaseConnectionPool

logger = logging.getLogger(__name__)


def execute_db_operation(
    pool: DatabaseConnectionPool,
    operation_type: str,
    command: str,
    params: tuple = (),
) -> list[Any] | int:
    conn, conn_index = pool.get_connection()
    if not conn:
        return [] if operation_type == "query" else 0

    try:
        cursor = conn.cursor()
        cursor.execute(command, params)
        if operation_type == "query":
            return cursor.fetchall()

        conn.commit()
        return cursor.rowcount
    except sqlite3.Error as error:
        logger.error("Database %s failed: %s", operation_type, error, exc_info=True)
        if operation_type != "query":
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
        return [] if operation_type == "query" else 0
    finally:
        if conn_index >= 0:
            pool.release_connection(conn_index)
        else:
            conn.close()


def execute_raw_sql(
    pool: DatabaseConnectionPool,
    command: str,
) -> list[Any] | int | str:
    conn, conn_index = pool.get_connection()
    if not conn:
        return "Unable to acquire database connection"

    try:
        cursor = conn.cursor()
        cursor.execute(command)
        if command.strip().upper().startswith("SELECT"):
            return cursor.fetchall()

        conn.commit()
        return cursor.rowcount
    except sqlite3.Error as error:
        logger.error("Raw SQL execution failed: %s", error, exc_info=True)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return f"SQL error: {error}"
    finally:
        if conn_index >= 0:
            pool.release_connection(conn_index)
        else:
            conn.close()
