from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable, Optional

from bot_core.data_repository import ConversationsRepository, UserProfilesRepository
from bot_core.services.utils.usage import get_dashboard_stats
from utils.config_utils import get_settings
from utils.db_utils import get_all_table_names, get_table_data, query_db


def _not_in_clause(values: Iterable[int], column_name: str) -> tuple[str, list[Any]]:
    values = list(values)
    if not values:
        return "", []
    placeholders = ", ".join(["?"] * len(values))
    return f"{column_name} NOT IN ({placeholders})", list(values)


class AdminQueryService:
    USER_SORT_FIELDS = {
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
    }
    CONVERSATION_SORT_FIELDS = {
        "conv_id",
        "user_id",
        "character",
        "preset",
        "turns",
        "create_at",
        "update_at",
    }
    GROUP_SORT_FIELDS = {
        "group_id",
        "group_name",
        "call_count",
        "api",
        "char",
        "preset",
        "rate",
        "input_token",
        "output_token",
        "active",
        "update_time",
    }

    def _sanitize_order(self, value: str) -> str:
        return "ASC" if value.lower() == "asc" else "DESC"

    def _sanitize_sort(self, field: str, allowed_fields: set[str], default: str) -> str:
        return field if field in allowed_fields else default

    def _has_user_profile(self, user_id: int) -> bool:
        result = UserProfilesRepository.user_has_profile(user_id)
        return bool(result.get("success") and result.get("data"))

    def _has_group_profile(self, group_id: int) -> bool:
        result = UserProfilesRepository.group_has_profile(group_id)
        return bool(result.get("success") and result.get("data"))

    def _has_detailed_summary(self, conv_id: int | str) -> bool:
        result = ConversationsRepository.dialog_summary_get(int(conv_id))
        return bool(result.get("success") and result.get("data"))

    def dashboard_stats(self, user_role: str, admin_ids: list[int], time_range: str) -> dict[str, Any]:
        if user_role != "viewer":
            return get_dashboard_stats(time_range)

        stats: dict[str, Any] = {}
        where_clause, params = _not_in_clause(admin_ids, "uid")
        user_filter = f"WHERE {where_clause}" if where_clause else ""

        stats["total_users"] = query_db(f"SELECT COUNT(*) FROM users {user_filter}", tuple(params))[0][0]
        conv_where, conv_params = _not_in_clause(admin_ids, "user_id")
        conv_filter = f"WHERE {conv_where}" if conv_where else ""
        stats["total_conversations"] = query_db(
            f"SELECT COUNT(*) FROM conversations {conv_filter}",
            tuple(conv_params),
        )[0][0]

        dialog_query = """
            SELECT COUNT(*)
            FROM dialogs d
            JOIN conversations c ON d.conv_id = c.conv_id
        """
        dialog_params: list[Any] = []
        dialog_where, dialog_admin_params = _not_in_clause(admin_ids, "c.user_id")
        if dialog_where:
            dialog_query += f" WHERE {dialog_where}"
            dialog_params.extend(dialog_admin_params)
        stats["total_dialogs"] = query_db(dialog_query, tuple(dialog_params))[0][0]

        today = datetime.now().strftime("%Y-%m-%d")
        today_conv_query = "SELECT COUNT(*) FROM conversations WHERE date(create_at) = ?"
        today_conv_params: list[Any] = [today]
        if conv_where:
            today_conv_query += f" AND {conv_where}"
            today_conv_params.extend(conv_params)
        stats["today_conversations"] = query_db(today_conv_query, tuple(today_conv_params))[0][0]

        today_dialog_query = """
            SELECT COUNT(*)
            FROM dialogs d
            JOIN conversations c ON d.conv_id = c.conv_id
            WHERE date(d.created_at) = ?
        """
        today_dialog_params: list[Any] = [today]
        if dialog_where:
            today_dialog_query += f" AND {dialog_where}"
            today_dialog_params.extend(dialog_admin_params)
        stats["today_dialogs"] = query_db(today_dialog_query, tuple(today_dialog_params))[0][0]

        token_query = "SELECT SUM(input_tokens), SUM(output_tokens) FROM users"
        if user_filter:
            token_query += f" {user_filter}"
        token_stats = query_db(token_query, tuple(params))[0]
        stats["total_input_tokens"] = token_stats[0] or 0
        stats["total_output_tokens"] = token_stats[1] or 0
        stats["today_group_dialogs"] = 0
        stats["total_group_dialogs"] = 0

        if stats["total_dialogs"] > 0:
            today_ratio = stats["today_dialogs"] / stats["total_dialogs"]
            stats["today_input_tokens"] = int(stats["total_input_tokens"] * today_ratio)
            stats["today_output_tokens"] = int(stats["total_output_tokens"] * today_ratio)
            stats["today_total_tokens"] = (
                stats["today_input_tokens"] + stats["today_output_tokens"]
            )
        else:
            stats["today_input_tokens"] = 0
            stats["today_output_tokens"] = 0
            stats["today_total_tokens"] = 0

        active_users_query = """
            SELECT u.uid, u.user_name, u.first_name, u.last_name, COUNT(d.id) as message_count
            FROM users u
            JOIN conversations c ON u.uid = c.user_id
            JOIN dialogs d ON c.conv_id = d.conv_id
            WHERE date(d.created_at) = ?
        """
        active_users_params: list[Any] = [today]
        if dialog_where:
            active_users_query += f" AND {dialog_where}"
            active_users_params.extend(dialog_admin_params)
        active_users_query += """
            GROUP BY u.uid, u.user_name, u.first_name, u.last_name
            ORDER BY message_count DESC
            LIMIT 5
        """
        stats["active_users"] = query_db(active_users_query, tuple(active_users_params))
        stats["active_groups"] = []
        return stats

    def list_users(
        self,
        *,
        user_role: str,
        admin_ids: list[int],
        page: int,
        per_page: int,
        search_term: str,
        sort_by: str,
        sort_order: str,
    ) -> dict[str, Any]:
        sort_by = self._sanitize_sort(sort_by, self.USER_SORT_FIELDS, "create_at")
        order = self._sanitize_order(sort_order)
        offset = (page - 1) * per_page

        where_clauses: list[str] = []
        params: list[Any] = []
        if user_role == "viewer":
            viewer_where, viewer_params = _not_in_clause(admin_ids, "uid")
            if viewer_where:
                where_clauses.append(viewer_where)
                params.extend(viewer_params)

        if search_term:
            search_param = f"%{search_term}%"
            where_clauses.append(
                "(CAST(uid AS TEXT) LIKE ? OR user_name LIKE ? OR first_name LIKE ? OR last_name LIKE ?)"
            )
            params.extend([search_param, search_param, search_param, search_param])

        base_query = "FROM users"
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)

        rows = query_db(
            f"SELECT * {base_query} ORDER BY {sort_by} {order} LIMIT ? OFFSET ?",
            tuple([*params, per_page, offset]),
        )
        total_users = query_db(f"SELECT COUNT(*) {base_query}", tuple(params))[0][0]

        columns = [
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
        users = [{columns[i]: row[i] for i in range(len(columns))} for row in rows]
        for user in users:
            user["has_profile"] = self._has_user_profile(user["uid"])
        return {
            "users": users,
            "total_users": total_users,
            "total_pages": (total_users + per_page - 1) // per_page,
            "sort_by": sort_by,
            "sort_order": order.lower(),
        }

    def list_conversations(
        self,
        *,
        user_role: str,
        admin_ids: list[int],
        page: int,
        per_page: int,
        search_term: str,
        sort_by: str,
        sort_order: str,
    ) -> dict[str, Any]:
        sort_by = self._sanitize_sort(sort_by, self.CONVERSATION_SORT_FIELDS, "update_at")
        order = self._sanitize_order(sort_order)
        offset = (page - 1) * per_page

        where_clauses = ["c.turns > 0"]
        params: list[Any] = []

        if user_role == "viewer":
            viewer_where, viewer_params = _not_in_clause(admin_ids, "c.user_id")
            if viewer_where:
                where_clauses.append(viewer_where)
                params.extend(viewer_params)

        if search_term:
            search_param = f"%{search_term}%"
            where_clauses.append(
                "(u.user_name LIKE ? OR u.first_name LIKE ? OR u.last_name LIKE ? OR CAST(c.user_id AS TEXT) LIKE ?)"
            )
            params.extend([search_param, search_param, search_param, search_param])

        base_query = """
            FROM conversations c
            LEFT JOIN users u ON c.user_id = u.uid
            WHERE """ + " AND ".join(where_clauses)

        rows = query_db(
            f"""
            SELECT c.id, c.conv_id, c.user_id, c.character, c.preset, c.summary,
                   c.create_at, c.update_at, c.delete_mark, c.turns,
                   u.first_name, u.last_name, u.user_name
            {base_query}
            ORDER BY c.{sort_by} {order}
            LIMIT ? OFFSET ?
            """,
            tuple([*params, per_page, offset]),
        )
        total = query_db(f"SELECT COUNT(*) {base_query}", tuple(params))[0][0]
        columns = [
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
        conversations = [{columns[i]: row[i] for i in range(len(columns))} for row in rows]
        for conversation in conversations:
            conversation["has_detailed_summary"] = self._has_detailed_summary(
                conversation["conv_id"]
            )
        return {
            "conversations": conversations,
            "total_conversations": total,
            "total_pages": (total + per_page - 1) // per_page,
            "sort_by": sort_by,
            "sort_order": order.lower(),
        }

    def get_conversation_detail(
        self,
        *,
        conv_id: str,
        user_role: str,
        admin_ids: list[int],
        page: int,
        per_page: int,
        search_term: str,
    ) -> dict[str, Any]:
        params: list[Any] = [conv_id]

        if user_role == "viewer":
            viewer_where, viewer_params = _not_in_clause(admin_ids, "user_id")
            check_query = "SELECT user_id FROM conversations WHERE conv_id = ?"
            check_params: list[Any] = [conv_id]
            if viewer_where:
                check_query += f" AND {viewer_where}"
                check_params.extend(viewer_params)
            if not query_db(check_query, tuple(check_params)):
                raise PermissionError("Conversation not accessible")

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

        conversation_columns = [
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
        conversation = {
            conversation_columns[i]: conversation_rows[0][i]
            for i in range(len(conversation_columns))
        }

        dialogs_params: list[Any] = [conv_id]
        where_sql = "conv_id = ? AND turn_order != 0"
        if search_term:
            search_param = f"%{search_term}%"
            where_sql += " AND (raw_content LIKE ? OR processed_content LIKE ?)"
            dialogs_params.extend([search_param, search_param])
        total_dialogs = query_db(
            f"SELECT COUNT(*) FROM dialogs WHERE {where_sql}",
            tuple(dialogs_params),
        )[0][0]
        offset = (page - 1) * per_page
        dialog_rows = query_db(
            f"SELECT * FROM dialogs WHERE {where_sql} ORDER BY turn_order ASC LIMIT ? OFFSET ?",
            tuple([*dialogs_params, per_page, offset]),
        )
        dialog_columns = [
            "id",
            "conv_id",
            "role",
            "raw_content",
            "turn_order",
            "created_at",
            "processed_content",
            "msg_id",
        ]
        dialogs = [{dialog_columns[i]: row[i] for i in range(len(dialog_columns))} for row in dialog_rows]
        detailed_summary = query_db(
            "SELECT summary_area, content FROM dialog_summary WHERE conv_id = ?",
            (conv_id,),
        )
        return {
            "conversation": conversation,
            "dialogs": dialogs,
            "detailed_summary": detailed_summary or None,
            "total_pages": (total_dialogs + per_page - 1) // per_page,
            "total_dialogs": total_dialogs,
        }

    def list_groups(
        self,
        *,
        page: int,
        per_page: int,
        search_term: str,
        sort_by: str,
        sort_order: str,
    ) -> dict[str, Any]:
        sort_by = self._sanitize_sort(sort_by, self.GROUP_SORT_FIELDS, "update_time")
        order = self._sanitize_order(sort_order)
        offset = (page - 1) * per_page
        params: list[Any] = []
        where_sql = ""
        if search_term:
            search_param = f"%{search_term}%"
            where_sql = (
                "WHERE CAST(group_id AS TEXT) LIKE ? OR group_name LIKE ? OR members_list LIKE ? OR api LIKE ? OR char LIKE ? OR preset LIKE ?"
            )
            params.extend([search_param] * 6)

        rows = query_db(
            f"SELECT * FROM groups {where_sql} ORDER BY {sort_by} {order} LIMIT ? OFFSET ?",
            tuple([*params, per_page, offset]),
        )
        total_groups = query_db(
            f"SELECT COUNT(*) FROM groups {where_sql}",
            tuple(params),
        )[0][0]

        columns = [
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
        groups = [{columns[i]: row[i] for i in range(len(columns))} for row in rows]
        for group in groups:
            group["has_profile"] = self._has_group_profile(group["group_id"])
        return {
            "groups": groups,
            "total_groups": total_groups,
            "total_pages": (total_groups + per_page - 1) // per_page,
            "sort_by": sort_by,
            "sort_order": order.lower(),
        }

    def get_group_dialogs(
        self,
        *,
        group_id: int,
        page: int,
        per_page: int,
        search_term: str,
    ) -> dict[str, Any]:
        group_rows = query_db("SELECT * FROM groups WHERE group_id = ?", (group_id,))
        if not group_rows:
            raise LookupError("Group not found")

        group_columns = [
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
        group = {group_columns[i]: group_rows[0][i] for i in range(len(group_columns))}
        offset = (page - 1) * per_page

        if search_term:
            dialog_rows = query_db(
                """
                WITH ranked_dialogs AS (
                    SELECT *,
                           ROW_NUMBER() OVER (ORDER BY create_at DESC) as rn
                    FROM group_dialogs
                    WHERE group_id = ?
                )
                SELECT *,
                       ((rn - 1) / ?) + 1 as original_page
                FROM ranked_dialogs
                WHERE msg_text LIKE ?
                ORDER BY create_at DESC
                LIMIT ? OFFSET ?
                """,
                (group_id, per_page, f"%{search_term}%", per_page, offset),
            )
            total_dialogs = query_db(
                "SELECT COUNT(*) FROM group_dialogs WHERE group_id = ? AND msg_text LIKE ?",
                (group_id, f"%{search_term}%"),
            )[0][0]
            columns = [
                "group_id",
                "msg_user",
                "trigger_type",
                "msg_text",
                "msg_user_name",
                "msg_id",
                "raw_response",
                "processed_response",
                "delete_mark",
                "group_name",
                "create_at",
                "rn",
                "original_page",
            ]
        else:
            dialog_rows = query_db(
                "SELECT * FROM group_dialogs WHERE group_id = ? ORDER BY create_at DESC LIMIT ? OFFSET ?",
                (group_id, per_page, offset),
            )
            total_dialogs = query_db(
                "SELECT COUNT(*) FROM group_dialogs WHERE group_id = ?",
                (group_id,),
            )[0][0]
            columns = [
                "group_id",
                "msg_user",
                "trigger_type",
                "msg_text",
                "msg_user_name",
                "msg_id",
                "raw_response",
                "processed_response",
                "delete_mark",
                "group_name",
                "create_at",
            ]

        dialogs = [{columns[i]: row[i] for i in range(len(columns))} for row in dialog_rows]
        return {
            "group": group,
            "dialogs": dialogs,
            "total_dialogs": total_dialogs,
            "total_pages": (total_dialogs + per_page - 1) // per_page,
        }

    def search_everywhere(self, query: str) -> dict[str, Any]:
        results = {"dialogs": [], "users": [], "groups": [], "conversations": []}
        if not query:
            return results

        like = f"%{query}%"
        dialogs_data = query_db(
            """
            SELECT d.*, c.character, c.user_id, u.user_name, u.first_name, u.last_name
            FROM dialogs d
            LEFT JOIN conversations c ON d.conv_id = c.conv_id
            LEFT JOIN users u ON c.user_id = u.uid
            WHERE d.raw_content LIKE ? OR d.processed_content LIKE ?
            ORDER BY d.created_at DESC
            """,
            (like, like),
        )
        dialog_columns = [
            "id",
            "conv_id",
            "role",
            "raw_content",
            "turn_order",
            "created_at",
            "processed_content",
            "msg_id",
            "character",
            "user_id",
            "user_name",
            "first_name",
            "last_name",
        ]
        for row in dialogs_data:
            dialog = {dialog_columns[i]: row[i] for i in range(len(dialog_columns))}
            first_name = dialog.get("first_name") or ""
            last_name = dialog.get("last_name") or ""
            display_name = f"{first_name} {last_name}".strip()
            dialog["display_name"] = display_name or dialog.get("user_name") or "鏈缃?"
            dialog["type"] = "private"
            results["dialogs"].append(dialog)

        group_dialogs_data = query_db(
            """
            SELECT gd.group_id, gd.msg_user, gd.trigger_type, gd.msg_text, gd.msg_user_name,
                   gd.msg_id, gd.raw_response, gd.processed_response, gd.delete_mark,
                   gd.group_name, gd.create_at, g.group_name as groups_group_name,
                   ROW_NUMBER() OVER (ORDER BY gd.create_at DESC) as id
            FROM group_dialogs gd
            LEFT JOIN groups g ON gd.group_id = g.group_id
            WHERE gd.msg_text LIKE ? OR gd.raw_response LIKE ? OR gd.processed_response LIKE ?
            ORDER BY gd.create_at DESC
            """,
            (like, like, like),
        )
        group_dialog_columns = [
            "group_id",
            "msg_user",
            "trigger_type",
            "msg_text",
            "msg_user_name",
            "msg_id",
            "raw_response",
            "processed_response",
            "delete_mark",
            "group_name",
            "create_at",
            "groups_group_name",
            "id",
        ]
        for row in group_dialogs_data:
            dialog = {group_dialog_columns[i]: row[i] for i in range(len(group_dialog_columns))}
            dialog["group_name"] = (
                dialog.get("groups_group_name")
                or dialog.get("group_name")
                or "鏈煡缇ょ粍"
            )
            dialog["type"] = "group"
            results["dialogs"].append(dialog)

        user_rows = query_db(
            """
            SELECT u.uid, u.first_name, u.last_name, u.user_name, u.create_at, u.conversations,
                   u.dialog_turns, u.update_at, u.input_tokens, u.output_tokens,
                   u.account_tier, u.remain_frequency, u.balance
            FROM users u
            WHERE u.user_name LIKE ? OR u.first_name LIKE ? OR u.last_name LIKE ? OR CAST(u.uid AS TEXT) LIKE ?
            ORDER BY u.create_at DESC
            """,
            (like, like, like, like),
        )
        user_columns = [
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
        results["users"] = [{user_columns[i]: row[i] for i in range(len(user_columns))} for row in user_rows]

        group_rows = query_db(
            """
            SELECT g.group_id, g.group_name, g.char, g.call_count, g.active, g.update_time,
                   COUNT(DISTINCT gd.msg_id) as dialog_count
            FROM groups g
            LEFT JOIN group_dialogs gd ON g.group_id = gd.group_id
            WHERE g.group_name LIKE ? OR CAST(g.group_id AS TEXT) LIKE ?
            GROUP BY g.group_id
            ORDER BY g.update_time DESC
            """,
            (like, like),
        )
        group_columns = [
            "group_id",
            "group_name",
            "char",
            "call_count",
            "active",
            "update_time",
            "dialog_count",
        ]
        results["groups"] = [{group_columns[i]: row[i] for i in range(len(group_columns))} for row in group_rows]

        conversation_rows = query_db(
            """
            SELECT c.conv_id, c.user_id, c.character, c.preset, c.summary, c.create_at,
                   c.update_at, u.user_name, u.first_name, u.last_name, COUNT(d.id) as turns
            FROM conversations c
            LEFT JOIN users u ON c.user_id = u.uid
            LEFT JOIN dialogs d ON c.conv_id = d.conv_id
            WHERE c.character LIKE ? OR c.preset LIKE ? OR c.summary LIKE ?
               OR u.user_name LIKE ? OR u.first_name LIKE ? OR u.last_name LIKE ?
               OR CAST(c.user_id AS TEXT) LIKE ?
            GROUP BY c.conv_id
            ORDER BY c.update_at DESC
            """,
            (like, like, like, like, like, like, like),
        )
        conversation_columns = [
            "conv_id",
            "user_id",
            "character",
            "preset",
            "summary",
            "create_at",
            "update_at",
            "user_name",
            "first_name",
            "last_name",
            "turns",
        ]
        results["conversations"] = [
            {conversation_columns[i]: row[i] for i in range(len(conversation_columns))}
            for row in conversation_rows
        ]
        return results

    def database_view(
        self,
        active_table: Optional[str],
        page: int,
        per_page: int,
        search_term: str,
        search_table_term: str = "",
    ) -> dict[str, Any]:
        all_table_names = get_all_table_names()
        table_names = [
            table_name
            for table_name in all_table_names
            if not search_table_term or search_table_term.lower() in table_name.lower()
        ]
        if active_table and active_table not in all_table_names:
            raise LookupError("Table not found")
        return {
            "table_names": table_names,
            "table_data": get_table_data(active_table, page, per_page, search_term) if active_table else {},
        }

    def analysis_items(self, page: int, per_page: int) -> dict[str, Any]:
        pics_dir = os.path.join(get_settings().project_root, "data", "pics")
        files = []
        if os.path.exists(pics_dir):
            files = [
                file_name
                for file_name in os.listdir(pics_dir)
                if file_name.lower().endswith((".jpg", ".png", ".jpeg", ".gif"))
            ]
            files.sort(key=lambda name: int(name.split("_")[-1].split(".")[0]), reverse=True)

        total_items = len(files)
        start = (page - 1) * per_page
        selected = files[start : start + per_page]
        items = []
        for file_name in selected:
            name, _ = os.path.splitext(file_name)
            user_id, _, timestamp_text = name.partition("_")
            try:
                timestamp = int(timestamp_text or 0)
            except ValueError:
                timestamp = 0
            user_info = query_db("SELECT first_name, last_name FROM users WHERE uid = ?", (user_id,))
            user_name = (
                f"{user_info[0][0] or ''} {user_info[0][1] or ''}".strip()
                if user_info
                else "未知用户"
            )
            txt_path = os.path.join(pics_dir, f"{name}.txt")
            content = ""
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r", encoding="utf-8") as file:
                        content = file.read()
                except OSError as error:
                    content = f"璇诲彇鏂囦欢鍑洪敊: {error}"
            items.append(
                {
                    "file_name": file_name,
                    "content": content,
                    "user_name": user_name,
                    "date_time": datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        return {
            "items": items,
            "total_pages": (total_items + per_page - 1) // per_page,
        }
