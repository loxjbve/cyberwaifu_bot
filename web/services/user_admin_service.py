from __future__ import annotations

from datetime import datetime
from typing import Any

from bot_core.data_repository import (
    ConversationsRepository,
    GroupsRepository,
    UserConfigRepository,
    UserProfilesRepository,
    UsersRepository,
)
from utils.db_utils import query_db, revise_db


class UserAdminService:
    USER_COLUMNS = [
        "uid",
        "first_name",
        "last_name",
        "user_name",
        "create_at",
        "conversations",
        "dialog_turns",
        "update_at",
        "input_tokens",
        "output_tokens",
        "account_tier",
        "remain_frequency",
        "balance",
    ]
    USER_CONFIG_COLUMNS = ["uid", "char", "api", "preset", "conv_id", "stream", "nick"]
    CONVERSATION_COLUMNS = [
        "id",
        "conv_id",
        "user_id",
        "character",
        "preset",
        "summary",
        "create_at",
        "update_at",
        "delete_mark",
        "turns",
        "first_name",
        "last_name",
        "user_name",
    ]
    DIALOG_COLUMNS = [
        "id",
        "conv_id",
        "role",
        "raw_content",
        "turn_order",
        "created_at",
        "processed_content",
        "msg_id",
    ]
    GROUP_COLUMNS = [
        "group_id",
        "members_list",
        "call_count",
        "keywords",
        "active",
        "api",
        "char",
        "preset",
        "input_token",
        "group_name",
        "update_time",
        "rate",
        "output_token",
        "disabled_topics",
    ]

    def _row_to_dict(self, row: tuple[Any, ...], columns: list[str]) -> dict[str, Any]:
        return {columns[index]: row[index] for index in range(min(len(row), len(columns)))}

    def _ensure_user_visible(self, user_id: int, user_role: str, admin_ids: list[int]) -> None:
        if user_role == "viewer" and user_id in admin_ids:
            raise PermissionError("User not accessible")

    def _ensure_conversation_visible(
        self,
        conv_id: int,
        user_role: str,
        admin_ids: list[int],
    ) -> None:
        if user_role != "viewer":
            return

        conversation_rows = query_db(
            "SELECT user_id FROM conversations WHERE conv_id = ?",
            (conv_id,),
        )
        if not conversation_rows or conversation_rows[0][0] in admin_ids:
            raise PermissionError("Conversation not accessible")

    def get_message_page(self, group_id: int, msg_id: int, *, per_page: int = 50) -> dict[str, int]:
        msg_data = query_db(
            "SELECT create_at FROM group_dialogs WHERE group_id = ? AND msg_id = ?",
            (group_id, msg_id),
        )
        if not msg_data:
            raise LookupError("Message not found")

        count_result = query_db(
            "SELECT COUNT(*) FROM group_dialogs WHERE group_id = ? AND create_at > ?",
            (group_id, msg_data[0][0]),
        )
        messages_after = count_result[0][0] if count_result else 0
        return {"page": (messages_after // per_page) + 1}

    def export_group_dialogs(self, group_id: int) -> dict[str, Any]:
        export_result = GroupsRepository.group_dialog_export_data_get(group_id)
        if not export_result.get("success") or not export_result.get("data"):
            raise LookupError(export_result.get("error") or "Export failed")

        export_data = export_result["data"]
        group = export_data.get("group") or {}
        dialogs = export_data.get("dialogs") or []
        conversations = []
        for dialog in dialogs:
            conversations.append(
                {
                    "dialog_id": dialog["msg_id"],
                    "user_message": {
                        "content": dialog["msg_text"],
                        "user_name": dialog["msg_user_name"],
                        "user_id": dialog["msg_user"],
                        "trigger_type": dialog["trigger_type"],
                        "time": dialog["create_at"],
                    },
                    "ai_response": {
                        "processed_response": dialog["processed_response"],
                        "raw_response": dialog["raw_response"],
                        "time": dialog["create_at"],
                    },
                }
            )

        return {
            "success": True,
            **export_data,
            "group_info": {
                "group_id": group.get("group_id", group_id),
                "group_name": export_data["export_meta"].get("group_name") or "Unnamed Group",
                "character": group.get("char") or "Unset",
                "preset": group.get("preset") or "Default",
                "export_time": export_data["export_meta"]["exported_at"],
                "total_conversations": len(conversations),
            },
            "conversations": conversations,
        }

    def get_user_detail(
        self,
        user_id: int,
        *,
        user_role: str,
        admin_ids: list[int],
    ) -> dict[str, Any]:
        self._ensure_user_visible(user_id, user_role, admin_ids)

        user_rows = query_db("SELECT * FROM users WHERE uid = ?", (user_id,))
        if not user_rows:
            raise LookupError("User not found")

        user_config_rows = query_db("SELECT * FROM user_config WHERE uid = ?", (user_id,))
        conversations_count_rows = query_db(
            "SELECT COUNT(*) FROM conversations WHERE user_id = ?",
            (user_id,),
        )
        profiles_result = UserProfilesRepository.user_profile_get(user_id)

        return {
            "user": self._row_to_dict(user_rows[0], self.USER_COLUMNS),
            "config": (
                self._row_to_dict(user_config_rows[0], self.USER_CONFIG_COLUMNS)
                if user_config_rows
                else None
            ),
            "conversations_count": conversations_count_rows[0][0] if conversations_count_rows else 0,
            "profiles": profiles_result.get("data", []),
        }

    def update_user(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        user_fields = [
            "user_name",
            "first_name",
            "last_name",
            "account_tier",
            "balance",
            "remain_frequency",
        ]
        for field in user_fields:
            if field not in payload:
                continue
            result = UsersRepository.user_info_update(user_id, field, payload[field])
            if not result.get("success"):
                raise RuntimeError(result.get("error") or f"Failed to update {field}")

        update_time_result = UsersRepository.user_info_update(
            user_id,
            "update_at",
            str(datetime.now()),
        )
        if not update_time_result.get("success"):
            raise RuntimeError(update_time_result.get("error") or "Failed to update timestamp")

        config_payload = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        if "nick" in payload and "nick" not in config_payload:
            config_payload["nick"] = payload["nick"]

        config_fields = ["char", "api", "preset", "stream", "nick"]
        if any(field in config_payload for field in config_fields):
            create_result = UserConfigRepository.user_config_create(
                user_id,
                nick=config_payload.get("nick"),
            )
            if not create_result.get("success"):
                raise RuntimeError(create_result.get("error") or "Failed to create config")

        for field in config_fields:
            if field not in config_payload:
                continue
            result = UserConfigRepository.user_config_arg_update(
                user_id,
                field,
                config_payload[field],
            )
            if not result.get("success"):
                raise RuntimeError(result.get("error") or f"Failed to update config {field}")

        return {"success": True, "message": "User updated"}

    def update_conversation_summary(self, conv_id: int, summary: str) -> None:
        result = ConversationsRepository.conversation_private_summary_add(conv_id, summary)
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "Failed to save summary")

    def export_private_dialogs(
        self,
        conv_id: int,
        *,
        user_role: str,
        admin_ids: list[int],
    ) -> dict[str, Any]:
        self._ensure_conversation_visible(conv_id, user_role, admin_ids)

        conversation_rows = query_db(
            """
            SELECT c.*, u.first_name, u.last_name, u.user_name
            FROM conversations c
            LEFT JOIN users u ON c.user_id = u.uid
            WHERE c.conv_id = ?
            """,
            (conv_id,),
        )
        if not conversation_rows:
            raise LookupError("Conversation not found")

        dialog_rows = query_db(
            "SELECT * FROM dialogs WHERE conv_id = ? AND turn_order != 0 ORDER BY turn_order ASC",
            (conv_id,),
        )

        return {
            "success": True,
            "conversation": self._row_to_dict(conversation_rows[0], self.CONVERSATION_COLUMNS),
            "dialogs": [self._row_to_dict(row, self.DIALOG_COLUMNS) for row in dialog_rows],
        }

    def get_conversation_summary(self, conv_id: int) -> dict[str, Any]:
        conversation_rows = query_db(
            "SELECT summary FROM conversations WHERE conv_id = ?",
            (conv_id,),
        )
        if not conversation_rows:
            raise LookupError("Conversation not found")
        return {
            "success": True,
            "summary": conversation_rows[0][0] or "鏆傛棤鎽樿",
        }

    def edit_message(self, dialog_id: int, content: str) -> dict[str, Any]:
        affected_rows = revise_db(
            "UPDATE dialogs SET processed_content = ? WHERE id = ?",
            (content, dialog_id),
        )
        if affected_rows <= 0:
            raise LookupError("Message not found")
        return {"success": True, "message": "Message updated"}

    def get_group_detail(self, group_id: int) -> dict[str, Any]:
        group_rows = query_db("SELECT * FROM groups WHERE group_id = ?", (group_id,))
        if not group_rows:
            raise LookupError("Group not found")
        return self._row_to_dict(group_rows[0], self.GROUP_COLUMNS)

    def update_group(self, group_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = [
            "group_name",
            "active",
            "rate",
            "char",
            "api",
            "preset",
            "keywords",
            "disabled_topics",
        ]
        updates = {field: payload[field] for field in allowed_fields if field in payload}
        if not updates:
            return {"success": True, "message": "No changes"}

        updates["update_time"] = str(datetime.now())
        set_clause = ", ".join(f"{key} = ?" for key in updates.keys())
        params = list(updates.values()) + [group_id]
        affected_rows = revise_db(
            f"UPDATE groups SET {set_clause} WHERE group_id = ?",
            tuple(params),
        )
        if affected_rows <= 0:
            raise LookupError("Group not found")
        return {"success": True, "message": "Group updated"}

    def get_group_profiles(self, group_id: int) -> list[dict[str, Any]]:
        result = UserProfilesRepository.group_profiles_get(group_id)
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "Failed to load profiles")
        return result.get("data", [])

    def save_group_profile(self, group_id: int, user_id: int, profile_json: str) -> dict[str, Any]:
        result = UserProfilesRepository.group_profile_update_or_create(
            group_id,
            user_id,
            profile_json,
        )
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "Failed to save profile")
        return {"success": True, "message": "Profile updated"}
