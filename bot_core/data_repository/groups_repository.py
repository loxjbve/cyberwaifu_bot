"""
groups_repository.py - 群组相关表(groups, group_dialogs)相关的CRUD操作
"""

import datetime
import json
import logging
from typing import List, Any, Optional, Tuple

from utils.db_utils import query_db, revise_db, get_config, DEFAULT_API, DEFAULT_CHAR, DEFAULT_PRESET
from utils.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class GroupsRepository:
    """Repository for groups and group dialog records."""

    @staticmethod
    def _row_to_dict(row: Tuple[Any, ...], columns: List[str]) -> dict:
        """Convert a database row into a JSON-serializable dictionary."""
        return {
            columns[i]: row[i]
            for i in range(min(len(row), len(columns)))
        }
    @staticmethod
    def group_check_update(group_id: int) -> dict:
        """
        检查群组信息是否需要更新（基于上次更新时间是否超过5分钟）

        Args:
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "data": bool (True表示需要更新或群组不存在，False表示不需要更新),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT update_time FROM groups WHERE group_id = ?"
            result = query_db(command, (group_id,))

            if result:
                # 尝试解析带微秒的时间格式，如果失败则尝试不带微秒的格式
                time_str = str(result[0][0])
                try:
                    update_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    update_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

                needs_update = update_time < datetime.datetime.now() - datetime.timedelta(minutes=5)
                return {
                    "success": True,
                    "data": needs_update
                }
            return {
                "success": True,
                "data": True  # 群组不存在，需要更新
            }
        except Exception as e:
            logger.error(f"检查群组更新状态失败: {e}")
            return {
                "success": False,
                "data": True,
                "error": str(e)
            }

    @staticmethod
    def group_config_get(group_id: int) -> dict:
        """
        获取指定群组的配置

        Args:
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "data": Optional[Tuple[str, str, str]] (api, char, preset) 元组，如果未找到则返回None,
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT api, char, preset FROM groups WHERE group_id = ?"
            result = query_db(command, (group_id,))

            data = result[0] if result else None

            return {
                "success": True,
                "data": data
            }
        except Exception as e:
            logger.error(f"获取群组配置失败: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    @staticmethod
    def group_config_arg_update(group_id: int, field: str, value: Any) -> dict:
        """
        更新群组配置表中的指定字段

        Args:
            group_id: 群组ID
            field: 要更新的字段名
            value: 新的字段值

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = f"UPDATE groups SET {field} = ? WHERE group_id = ?"
            result = revise_db(command, (value, group_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新群组配置字段失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def group_name_get(group_id: int) -> dict:
        """
        获取指定群组的名称

        Args:
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "data": str (群组名称，如果未找到则返回空字符串),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT group_name FROM groups WHERE group_id = ?"
            result = query_db(command, (group_id,))

            group_name = result[0][0] if result and result[0][0] else ""

            return {
                "success": True,
                "data": group_name
            }
        except Exception as e:
            logger.error(f"获取群组名称失败: {e}")
            return {
                "success": False,
                "data": "",
                "error": str(e)
            }

    @staticmethod
    def group_admin_list_get(group_id: int) -> dict:
        """
        获取指定群组的管理员列表（从JSON字符串解析）

        Args:
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "data": List[str] (管理员列表，如果解析失败或无数据则返回空列表),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT members_list FROM groups WHERE group_id = ?"
            result = query_db(command, (group_id,))

            admin_list = json.loads(result[0][0]) if result and result[0][0] else []

            return {
                "success": True,
                "data": admin_list
            }
        except Exception as e:
            logger.error(f"获取群管理员列表失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def group_keyword_get(group_id: int) -> dict:
        """
        获取指定群组的关键词列表（从JSON字符串解析）

        Args:
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "data": List[str] (关键词列表，如果解析失败或无数据则返回空列表),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT keywords FROM groups WHERE group_id = ?"
            result = query_db(command, (group_id,))

            keywords = json.loads(result[0][0]) if result and result[0][0] else []

            return {
                "success": True,
                "data": keywords
            }
        except Exception as e:
            logger.error(f"获取群组关键词失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def group_keyword_set(group_id: int, keywords: List[str]) -> dict:
        """
        设置指定群组的关键词列表（序列化为JSON字符串存储）

        Args:
            group_id: 群组ID
            keywords: 关键词列表

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            keywords_str = json.dumps(keywords, ensure_ascii=False)
            command = "UPDATE groups SET keywords = ? WHERE group_id = ?"
            result = revise_db(command, (keywords_str, group_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"设置群组关键词失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def group_info_create(group_id: int) -> dict:
        """
        为指定group_id创建一条新的群组记录，使用默认API、角色和预设

        Args:
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = "INSERT INTO groups (group_id, api, char, preset) VALUES (?, ?, ?, ?)"
            result = revise_db(command, (group_id, DEFAULT_API, DEFAULT_CHAR, DEFAULT_PRESET))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"为新群组创建记录失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def group_dialog_initial_add(group_id: int, msg_user_id: int, msg_user_name: str, msg_text: str, msg_id: int, group_name: str) -> dict:
        """
        向 group_dialogs 表中插入一条初始的用户消息记录。AI回复相关字段在此阶段留空

        Args:
            group_id: 群组ID
            msg_user_id: 消息发送者用户ID
            msg_user_name: 消息发送者用户名
            msg_text: 消息文本内容
            msg_id: Telegram消息ID
            group_name: 群组名称

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            create_at = str(datetime.datetime.now())
            command = """
                INSERT INTO group_dialogs
                (group_id, msg_user, msg_user_name, msg_text, msg_id, group_name, create_at, delete_mark)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'no')
            """
            params = (group_id, msg_user_id, msg_user_name, msg_text, msg_id, group_name, create_at)

            # 使用 try-except 避免因为重复 msg_id 而崩溃
            try:
                result = revise_db(command, params)
                return {
                    "success": result > 0
                }
            except Exception as e:
                if "UNIQUE constraint" in str(e) or "重复" in str(e):
                    logger.warning(f"尝试插入重复的 group_dialogs 记录失败: msg_id={msg_id}, group_id={group_id}")
                    return {
                        "success": False,
                        "error": f"重复的消息ID: {msg_id}"
                    }
                raise e
        except Exception as e:
            logger.error(f"添加群组初始对话失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def group_dialog_response_update(group_id: int, msg_id: int, trigger_type: str, raw_response: str, processed_response: str) -> dict:
        """
        在 group_dialogs 表中更新AI的回复内容和触发类型

        Args:
            group_id: 群组ID
            msg_id: 原始用户消息的ID
            trigger_type: 触发回复的类型 ('reply', '@', 'keyword', 'random')
            raw_response: LLM返回的原始响应
            processed_response: 处理后用于显示的响应

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = """
                UPDATE group_dialogs
                SET trigger_type = ?, raw_response = ?, processed_response = ?
                WHERE group_id = ? AND msg_id = ?
            """
            params = (trigger_type, raw_response, processed_response, group_id, msg_id)
            result = revise_db(command, params)

            if result == 0:
                logger.warning(f"更新群聊对话回复失败，未找到匹配记录: group_id={group_id}, msg_id={msg_id}")
                return {
                    "success": False,
                    "error": "未找到匹配的记录"
                }

            return {
                "success": True
            }
        except Exception as e:
            logger.error(f"更新群聊对话回复失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def group_dialog_update(msg_id: int, field: str, value: Any, group_id: int) -> dict:
        """
        更新group_dialogs表中指定消息的指定字段

        Args:
            msg_id: 消息ID
            field: 要更新的字段名
            value: 新的字段值
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = f"UPDATE group_dialogs SET {field} = ? WHERE msg_id = ? AND group_id = ?"
            result = revise_db(command, (value, msg_id, group_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新群组对话字段失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def group_dialog_get(group_id: int, num: int) -> dict:
        """
        获取指定group_id的最新num条群聊消息，按msg_id降序排序

        Args:
            group_id: 群组ID
            num: 获取消息数量

        Returns:
            dict: {
                "success": bool,
                "data": List[Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]] (消息列表，每个元组包含(msg_text, msg_user_name, processed_response, create_at)),
                "error": str (如果有错误)
            }
        """
        try:
            command = """
                      SELECT msg_text, msg_user_name, processed_response, create_at
                      FROM (SELECT msg_text, msg_user_name, processed_response, create_at, msg_id \
                            FROM group_dialogs \
                            WHERE group_id = ? \
                            ORDER BY msg_id DESC \
                            LIMIT ?) sub
                      ORDER BY msg_id ASC \
                      """
            result = query_db(command, (group_id, num))

            return {
                "success": True,
                "data": result if result else []
            }
        except Exception as e:
            logger.error(f"获取群组对话失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def group_dialog_export_data_get(group_id: int) -> dict:
        """
        Export full stored group chat history as a JSON-ready payload.

        Args:
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "data": Optional[dict],
                "error": str
            }
        """
        try:
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
            dialog_columns = [
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

            group_rows = query_db(
                "SELECT * FROM groups WHERE group_id = ? LIMIT 1",
                (group_id,),
            )
            dialog_rows = query_db(
                """
                SELECT * FROM group_dialogs
                WHERE group_id = ?
                ORDER BY create_at ASC, msg_id ASC
                """,
                (group_id,),
            )

            if not group_rows and not dialog_rows:
                return {
                    "success": False,
                    "data": None,
                    "error": "群组不存在或没有可导出的群聊记录",
                }

            group_record = (
                GroupsRepository._row_to_dict(group_rows[0], group_columns)
                if group_rows
                else {"group_id": group_id}
            )
            dialogs = [
                GroupsRepository._row_to_dict(row, dialog_columns)
                for row in (dialog_rows or [])
            ]
            group_name = (
                group_record.get("group_name")
                or (dialogs[0].get("group_name") if dialogs else "")
                or ""
            )

            return {
                "success": True,
                "data": {
                    "export_meta": {
                        "export_type": "group_dialogs",
                        "schema_version": 1,
                        "exported_at": datetime.datetime.now().isoformat(),
                        "group_id": group_id,
                        "group_name": group_name,
                        "has_group_record": bool(group_rows),
                        "dialog_count": len(dialogs),
                    },
                    "group": group_record,
                    "dialogs": dialogs,
                }
            }
        except Exception as e:
            logger.error(f"导出群聊记录失败: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    @staticmethod
    def group_info_update(group_id: int, field: str, value: Any, increase: bool = False) -> dict:
        """
        更新 groups 表中指定群组的指定字段

        Args:
            group_id: 群组ID
            field: 要更新的字段名
            value: 新的字段值
            increase: 是否为增量更新，默认为False

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            if not increase:
                command = f"UPDATE groups SET {field} = ? WHERE group_id = ?"
            else:
                command = f"UPDATE groups SET {field} = COALESCE({field}, 0) + ? WHERE group_id = ?"

            result = revise_db(command, (value, group_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新群组信息失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def group_rate_get(group_id: int) -> dict:
        """
        获取指定群组的回复频率(rate)

        Args:
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "data": float (回复频率，如果未设置或查询失败则返回配置中的默认值),
                "error": str (如果有错误)
            }
        """
        try:
            command = f"SELECT rate FROM groups WHERE group_id = ?"
            result = query_db(command, (group_id,))

            default_rate = get_config("group.default_rate", 0.05)
            rate = result[0][0] if result and result[0] and result[0][0] is not None else default_rate

            return {
                "success": True,
                "data": rate
            }
        except Exception as e:
            logger.error(f"获取群组回复频率失败: {e}")
            default_rate = get_config("group.default_rate", 0.05)
            return {
                "success": False,
                "data": default_rate,
                "error": str(e)
            }

    @staticmethod
    def group_disabled_topics_get(group_id: int) -> dict:
        """
        获取指定群组的禁用话题列表（从JSON字符串解析）

        Args:
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "data": List[str] (禁用话题列表，如果解析失败或无数据则返回空列表),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT disabled_topics FROM groups WHERE group_id = ?"
            result = query_db(command, (group_id,))

            disabled_topics = json.loads(result[0][0]) if result and result[0][0] else []

            return {
                "success": True,
                "data": disabled_topics
            }
        except Exception as e:
            logger.error(f"获取群组禁用话题失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def group_disabled_topics_set(group_id: int, topics: List[str]) -> dict:
        """
        设置指定群组的禁用话题列表（序列化为JSON字符串存储）

        Args:
            group_id: 群组ID
            topics: 禁用话题列表

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            topics_str = json.dumps(topics, ensure_ascii=False)
            command = "UPDATE groups SET disabled_topics = ? WHERE group_id = ?"
            result = revise_db(command, (topics_str, group_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"设置群组禁用话题失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
