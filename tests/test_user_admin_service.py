from __future__ import annotations

import pytest

from web.services.admin_query_service import AdminQueryService
from web.services.user_admin_service import UserAdminService


def _insert_user(revise_db, user_id: int, *, user_name: str, first_name: str = "Test", last_name: str = "User"):
    revise_db(
        """
        INSERT INTO users (
            uid, first_name, last_name, user_name, create_at, conversations,
            dialog_turns, update_at, input_tokens, output_tokens,
            account_tier, remain_frequency, balance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            first_name,
            last_name,
            user_name,
            "2026-01-01 00:00:00",
            0,
            0,
            "2026-01-01 00:00:00",
            0,
            0,
            0,
            100,
            1.5,
        ),
    )


def test_update_user_creates_config_and_updates_fields(sqlite_backend):
    revise_db = sqlite_backend["revise_db"]
    query_db = sqlite_backend["query_db"]
    service = UserAdminService()

    _insert_user(revise_db, 1, user_name="old_name")

    result = service.update_user(
        1,
        {
            "user_name": "new_name",
            "first_name": "Alice",
            "last_name": "Bot",
            "account_tier": 2,
            "balance": 9.5,
            "remain_frequency": 88,
            "config": {
                "char": "char-a",
                "api": "api-a",
                "preset": "preset-a",
                "stream": "yes",
                "nick": "Ali",
            },
        },
    )

    assert result["success"] is True
    user_row = query_db(
        "SELECT user_name, first_name, last_name, account_tier, balance, remain_frequency FROM users WHERE uid = ?",
        (1,),
    )[0]
    config_row = query_db(
        "SELECT char, api, preset, stream, nick FROM user_config WHERE uid = ?",
        (1,),
    )[0]

    assert user_row == ("new_name", "Alice", "Bot", 2, 9.5, 88)
    assert config_row == ("char-a", "api-a", "preset-a", "yes", "Ali")


def test_export_private_dialogs_blocks_viewer_from_admin_owned_conversation(sqlite_backend):
    revise_db = sqlite_backend["revise_db"]
    service = UserAdminService()

    _insert_user(revise_db, 1, user_name="regular_user")
    _insert_user(revise_db, 999, user_name="admin_user")
    revise_db(
        """
        INSERT INTO conversations (
            conv_id, user_id, character, preset, summary, create_at,
            update_at, delete_mark, turns
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (101, 1, "char-a", "preset-a", "", "2026-01-01", "2026-01-01", "no", 2),
    )
    revise_db(
        """
        INSERT INTO conversations (
            conv_id, user_id, character, preset, summary, create_at,
            update_at, delete_mark, turns
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (202, 999, "char-b", "preset-b", "", "2026-01-01", "2026-01-01", "no", 2),
    )
    revise_db(
        "INSERT INTO dialogs (conv_id, role, raw_content, turn_order, created_at, processed_content, msg_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (101, "user", "hello", 1, "2026-01-01", "hello", 1),
    )
    revise_db(
        "INSERT INTO dialogs (conv_id, role, raw_content, turn_order, created_at, processed_content, msg_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (101, "assistant", "hi", 2, "2026-01-01", "hi", 2),
    )
    revise_db(
        "INSERT INTO dialogs (conv_id, role, raw_content, turn_order, created_at, processed_content, msg_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (202, "user", "secret", 1, "2026-01-01", "secret", 3),
    )

    payload = service.export_private_dialogs(
        101,
        user_role="viewer",
        admin_ids=[999],
    )
    assert payload["conversation"]["user_id"] == 1
    assert len(payload["dialogs"]) == 2

    with pytest.raises(PermissionError):
        service.export_private_dialogs(
            202,
            user_role="viewer",
            admin_ids=[999],
        )


def test_admin_query_service_defaults_invalid_sort_and_filters_admin_ids(sqlite_backend):
    revise_db = sqlite_backend["revise_db"]
    service = AdminQueryService()

    _insert_user(revise_db, 1, user_name="regular_user")
    _insert_user(revise_db, 999, user_name="admin_user")
    revise_db(
        "INSERT INTO user_profiles (user_id, group_id, profile_json, last_updated) VALUES (?, ?, ?, ?)",
        (1, 77, '{"summary":"profile"}', "2026-01-01"),
    )

    result = service.list_users(
        user_role="viewer",
        admin_ids=[999],
        page=1,
        per_page=20,
        search_term="",
        sort_by="uid; DROP TABLE users",
        sort_order="asc",
    )

    assert result["sort_by"] == "create_at"
    assert result["sort_order"] == "asc"
    assert result["total_users"] == 1
    assert [user["uid"] for user in result["users"]] == [1]
    assert result["users"][0]["has_profile"] is True
