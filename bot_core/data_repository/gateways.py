from __future__ import annotations

import logging
import random
from typing import Any, Iterable, Optional

from bot_core.data_repository.conv_model import Conversation, DialogMessage, Group, GroupConfig, User
from bot_core.data_repository.conversations_repository import ConversationsRepository
from bot_core.data_repository.groups_repository import GroupsRepository
from bot_core.data_repository.sign_repository import SignRepository
from bot_core.data_repository.user_config_repository import UserConfigRepository
from bot_core.data_repository.user_profiles_repository import UserProfilesRepository
from bot_core.data_repository.users_repository import UsersRepository
from utils.db_utils import query_db, revise_db

logger = logging.getLogger(__name__)


class DataAccessError(RuntimeError):
    pass


def _unwrap_result(result: dict, *, default: Any = None, action: str = "database call") -> Any:
    if result.get("success"):
        return result.get("data", default)
    raise DataAccessError(f"{action} failed: {result.get('error', 'unknown error')}")


class UserGateway:
    def __init__(self) -> None:
        self.users = UsersRepository()
        self.user_config = UserConfigRepository()
        self.sign = SignRepository()

    def get_by_id(self, user_id: int) -> Optional[User]:
        user_info = _unwrap_result(
            self.users.user_info_get(user_id),
            default={},
            action=f"load user {user_id}",
        )
        if not user_info:
            return None

        user_config = _unwrap_result(
            self.user_config.user_config_get(user_id),
            default={},
            action=f"load user config {user_id}",
        )
        sign_info = _unwrap_result(
            self.sign.user_sign_info_get(user_id),
            default={},
            action=f"load user sign {user_id}",
        )

        combined = {
            "uid": user_id,
            **user_info,
            **user_config,
            **sign_info,
        }
        return User.model_validate(combined)

    def get_or_create(
        self,
        *,
        user_id: int,
        first_name: str,
        last_name: str,
        user_name: str,
    ) -> User:
        user = self.get_by_id(user_id)
        if user:
            return user

        if not self.users.user_info_create(user_id, first_name, last_name, user_name)["success"]:
            raise DataAccessError(f"Failed to create user {user_id}")

        nick = f"{first_name or ''} {last_name or ''}".strip()
        config_result = self.user_config.user_config_create(user_id, nick=nick)
        if not config_result["success"]:
            raise DataAccessError(f"Failed to create default config for user {user_id}")

        user = self.get_by_id(user_id)
        if not user:
            raise DataAccessError(f"Unable to reload user {user_id} after creation")
        return user

    def update_profile_if_changed(
        self,
        *,
        user_id: int,
        first_name: str,
        last_name: str,
        username: str,
    ) -> bool:
        current_user = self.get_by_id(user_id)
        if not current_user:
            return False

        updates = {
            "first_name": first_name,
            "last_name": last_name,
            "user_name": username,
        }

        changed = False
        for field, value in updates.items():
            if getattr(current_user, field) != value:
                changed = True
                if not self.users.user_info_update(user_id, field, value)["success"]:
                    raise DataAccessError(f"Failed to update user {user_id} field {field}")

        return changed


class ConversationGateway:
    def __init__(self) -> None:
        self.conversations = ConversationsRepository()
        self.users = UsersRepository()
        self.user_config = UserConfigRepository()

    def get_private(self, conv_id: int) -> Optional[Conversation]:
        record = query_db(
            """
            SELECT conv_id, user_id, character, preset, delete_mark, create_at, update_at, turns
            FROM conversations
            WHERE conv_id = ?
            """,
            (conv_id,),
        )
        if not record:
            return None

        row = record[0]
        summaries = self.get_summaries(conv_id)
        history_rows = _unwrap_result(
            self.conversations.dialog_content_load(conv_id, "private", raw=False),
            default=[],
            action=f"load conversation history {conv_id}",
        )
        raw_rows = _unwrap_result(
            self.conversations.dialog_content_load(conv_id, "private", raw=True),
            default=[],
            action=f"load raw history {conv_id}",
        )
        raw_by_turn = {raw_turn: raw_content for _, raw_turn, raw_content in raw_rows}

        history = [
            DialogMessage.model_validate(
                {
                    "role": role,
                    "turn": turn_order,
                    "raw_content": raw_by_turn.get(turn_order, processed_content),
                    "processed_content": processed_content,
                    "created_at": row_time,
                }
            )
            for role, turn_order, processed_content, row_time in query_db(
                """
                SELECT role, turn_order, processed_content, created_at
                FROM dialogs
                WHERE conv_id = ?
                ORDER BY turn_order ASC
                """,
                (conv_id,),
            )
        ]

        return Conversation.model_validate(
            {
                "conv_id": row[0],
                "user_id": row[1],
                "character": row[2],
                "preset": row[3],
                "delete_mark": row[4] == "yes",
                "created_at": row[5],
                "updated_at": row[6],
                "turns": row[7] or 0,
                "summaries": summaries,
                "history": history,
            }
        )

    def create_private(self, user: User) -> Conversation:
        for _ in range(5):
            conv_id = random.randint(10000000, 99999999)
            if not self.conversations.conversation_private_check(conv_id)["data"]:
                continue

            created = self.conversations.conversation_private_create(
                conv_id,
                user.id,
                user.character,
                user.preset,
            )
            if not created["success"]:
                continue

            if not self.user_config.user_config_arg_update(user.id, "conv_id", conv_id)["success"]:
                raise DataAccessError(f"Failed to set active conversation for user {user.id}")

            self.users.user_conversations_count_update(user.id)
            conversation = self.get_private(conv_id)
            if conversation:
                return conversation

        raise DataAccessError(f"Failed to create private conversation for user {user.id}")

    def get_group_conversation_id(self, group_id: int, user_id: int) -> Optional[int]:
        return _unwrap_result(
            self.conversations.conversation_group_get(group_id, user_id),
            default=None,
            action=f"load group conversation for {group_id}/{user_id}",
        )

    def create_group_conversation(self, user: User, group: Group) -> int:
        for _ in range(5):
            conv_id = random.randint(10000000, 99999999)
            if not self.conversations.conversation_group_check(conv_id)["data"]:
                continue
            result = self.conversations.conversation_group_create(
                conv_id,
                user.id,
                user.user_name or "",
                group.id,
                group.name or "",
            )
            if result["success"]:
                return conv_id
        raise DataAccessError(f"Failed to create group conversation for user {user.id}")

    def get_turn_count(self, conv_id: int, chat_type: str = "private") -> int:
        return int(
            _unwrap_result(
                self.conversations.dialog_turn_get(conv_id, chat_type),
                default=0,
                action=f"load turn count for conversation {conv_id}",
            )
        )

    def update_turns(self, conv_id: int, turns: int, chat_type: str = "private") -> None:
        result = self.conversations.conversation_turns_update(conv_id, turns, chat_type)
        if not result["success"]:
            raise DataAccessError(
                f"Failed to update turns for conversation {conv_id}: {result.get('error')}"
            )

    def append_dialogs(
        self,
        conv_id: int,
        dialogs: Iterable[dict[str, Any]],
        *,
        chat_type: str = "private",
    ) -> None:
        for dialog in dialogs:
            result = self.conversations.dialog_content_add(
                conv_id=conv_id,
                role=dialog["role"],
                turn_order=dialog["turn_order"],
                raw_content=dialog["raw_content"],
                processed_content=dialog["processed_content"],
                msg_id=dialog.get("message_id"),
                chat_type=chat_type,
            )
            if not result["success"]:
                raise DataAccessError(
                    f"Failed to append dialog to {conv_id}: {result.get('error')}"
                )

    def delete_message(self, conv_id: int, message_id: int) -> None:
        result = self.conversations.conversation_delete_messages(conv_id, message_id)
        if not result["success"]:
            raise DataAccessError(
                f"Failed to delete message {message_id} in {conv_id}: {result.get('error')}"
            )

    def get_latest_message_ids(self, conv_id: int) -> list[int]:
        return list(
            _unwrap_result(
                self.conversations.conversation_latest_message_id_get(conv_id),
                default=[],
                action=f"load latest message ids for {conv_id}",
            )
        )

    def get_last_input_text(self, conv_id: int) -> str:
        return str(
            _unwrap_result(
                self.conversations.dialog_last_input_get(conv_id),
                default="",
                action=f"load last input for {conv_id}",
            )
        )

    def get_summaries(self, conv_id: int) -> list[dict[str, Any]]:
        return list(
            _unwrap_result(
                self.conversations.dialog_summary_get(conv_id),
                default=[],
                action=f"load summaries for {conv_id}",
            )
        )


class GroupGateway:
    def __init__(self) -> None:
        self.groups = GroupsRepository()
        self.conversations = ConversationsRepository()
        self.user_profiles = UserProfilesRepository()

    def get_group(self, group_id: int) -> Group:
        group_name = _unwrap_result(
            self.groups.group_name_get(group_id),
            default="",
            action=f"load group name {group_id}",
        )
        return Group(id=group_id, name=group_name or "")

    def get_runtime_config(self, group_id: int) -> GroupConfig:
        config = _unwrap_result(
            self.groups.group_config_get(group_id),
            default=None,
            action=f"load group config {group_id}",
        )
        if not config:
            return GroupConfig()
        api, char, preset = config
        return GroupConfig(api=api, char=char, preset=preset)

    def update_dialog_response(
        self,
        *,
        group_id: int,
        message_id: int,
        trigger_type: str,
        raw_response: str,
        processed_response: str,
    ) -> None:
        result = self.groups.group_dialog_response_update(
            group_id=group_id,
            msg_id=message_id,
            trigger_type=trigger_type,
            raw_response=raw_response,
            processed_response=processed_response,
        )
        if not result["success"]:
            raise DataAccessError(
                f"Failed to update group dialog response {group_id}/{message_id}: {result.get('error')}"
            )

    def update_dialog_field(self, *, group_id: int, message_id: int, field: str, value: Any) -> None:
        result = self.groups.group_dialog_update(message_id, field, value, group_id)
        if not result["success"]:
            raise DataAccessError(
                f"Failed to update group dialog field {field} for {group_id}/{message_id}: {result.get('error')}"
            )

    def update_group_conversation_turn(self, conv_id: int, turns_increase: int = 0) -> None:
        affected_rows = revise_db(
            "UPDATE group_user_conversations SET turns = COALESCE(turns, 0) + ? WHERE conv_id = ?",
            (turns_increase, conv_id),
        )
        if affected_rows <= 0:
            raise DataAccessError(f"Failed to update group conversation turns for {conv_id}")

    def update_group_stats(
        self,
        group_id: int,
        *,
        call_count_increase: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        updates = [
            ("call_count", call_count_increase),
            ("input_token", input_tokens),
            ("output_token", output_tokens),
        ]
        for field, value in updates:
            if value <= 0:
                continue
            result = self.groups.group_info_update(group_id, field, value, increase=True)
            if not result["success"]:
                raise DataAccessError(
                    f"Failed to update {field} for group {group_id}: {result.get('error')}"
                )

    def user_profiles(self) -> UserProfilesRepository:
        return self.user_profiles
