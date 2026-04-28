from __future__ import annotations

import logging
import os
import re
import sqlite3

from utils.schema_migration import check_and_migrate_database_schema

logger = logging.getLogger(__name__)


def ensure_database_exists(db_path: str, sql_path: str) -> None:
    if os.path.exists(db_path):
        return

    logger.info("Database file missing, initializing from %s", sql_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(sql_path, "r", encoding="utf-8") as file:
        sql_script = file.read()
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(sql_script)
    finally:
        conn.close()


def _fallback_table_check(db_path: str, sql_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        with open(sql_path, "r", encoding="utf-8") as file:
            sql_content = file.read()
        create_table_statements = [
            stmt.strip()
            for stmt in sql_content.split(";")
            if "CREATE TABLE" in stmt.upper()
        ]

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {table[0] for table in cursor.fetchall()}

        for stmt in create_table_statements:
            stmt_upper = stmt.upper()
            if "CREATE TABLE" not in stmt_upper:
                continue
            create_table_pos = stmt_upper.find("CREATE TABLE")
            table_part = stmt[create_table_pos + len("CREATE TABLE") :].strip()
            table_name = table_part.split("(")[0].strip()
            if table_name in existing_tables:
                continue

            logger.warning("Missing table %s detected, creating it", table_name)
            cursor.execute(stmt)
            conn.commit()
    finally:
        conn.close()


def _check_and_create_indexes(db_path: str, sql_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        with open(sql_path, "r", encoding="utf-8") as file:
            sql_content = file.read()

        index_statements = re.findall(
            r"create\s+index\s+[^;]+;",
            sql_content,
            re.IGNORECASE | re.DOTALL,
        )
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';"
        )
        existing_indexes = {index[0] for index in cursor.fetchall()}

        for stmt in index_statements:
            stmt = stmt.strip()
            if not stmt:
                continue
            index_match = re.search(r"create\s+index\s+(\w+)", stmt, re.IGNORECASE)
            if not index_match:
                continue
            index_name = index_match.group(1)
            if index_name in existing_indexes:
                continue
            try:
                cursor.execute(stmt)
                conn.commit()
                logger.info("Created missing index %s", index_name)
            except sqlite3.Error as error:
                logger.warning("Failed to create index %s: %s", index_name, error)
    finally:
        conn.close()


def prepare_database(db_path: str, sql_path: str) -> None:
    ensure_database_exists(db_path, sql_path)
    try:
        check_and_migrate_database_schema(db_path=db_path, sql_path=sql_path)
    except Exception as error:
        logger.error("Schema migration failed, falling back to table check: %s", error)
        _fallback_table_check(db_path, sql_path)
    _check_and_create_indexes(db_path, sql_path)
