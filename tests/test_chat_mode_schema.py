from __future__ import annotations

import sqlite3
from pathlib import Path

from utils.schema_migration import check_and_migrate_database_schema


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_schema_migration_adds_chat_mode_columns(tmp_path):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE user_config (
            uid INT UNIQUE,
            char TEXT,
            api TEXT,
            preset TEXT,
            conv_id INT,
            stream TEXT,
            nick TEXT
        );
        CREATE TABLE groups (
            group_id integer primary key,
            members_list ANY,
            call_count integer,
            keywords ANY,
            active INT,
            api TEXT,
            char TEXT,
            preset TEXT,
            input_token integer,
            group_name TEXT,
            update_time ANY,
            rate REAL,
            output_token integer,
            disabled_topics TEXT
        );
        INSERT INTO user_config (uid, char, api, preset, stream, nick)
        VALUES (1, 'char-a', 'api-a', 'preset-a', 'no', 'tester');
        INSERT INTO groups (group_id, api, char, preset)
        VALUES (-100, 'api-g', 'char-g', 'preset-g');
        """
    )
    conn.commit()
    conn.close()

    assert check_and_migrate_database_schema(
        db_path=str(db_path),
        sql_path=str(PROJECT_ROOT / "data" / "database.sql"),
    )

    conn = sqlite3.connect(db_path)
    try:
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(user_config)")}
        group_columns = {row[1] for row in conn.execute("PRAGMA table_info(groups)")}
        assert "chat_mode" in user_columns
        assert "chat_mode" in group_columns
    finally:
        conn.close()
