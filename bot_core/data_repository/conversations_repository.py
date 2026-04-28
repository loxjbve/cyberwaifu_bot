"""
conversations_repository.py - 对话相关表(conversations, dialogs, group_user_conversations, group_user_dialogs, dialog_summary)相关的CRUD操作
"""

import datetime
import logging
from typing import List, Optional, Tuple, Union

from utils.db_utils import query_db, revise_db
from utils.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class ConversationsRepository:
    """对话相关表相关的数据库操作"""

    @staticmethod
    def _update_conversation_timestamp(conv_id: int, create_at: str, table_name: str) -> dict:
        """
        辅助函数：更新对话表的时间戳

        Args:
            conv_id: 会话ID
            create_at: 创建时间
            table_name: 表名

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = f"UPDATE {table_name} SET update_at = ? WHERE conv_id = ?"
            result = revise_db(command, (create_at, conv_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新对话时间戳失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_create(conv_id: int, userid: int, character: str, preset: str) -> dict:
        """
        创建一条新的私聊对话记录，并更新用户的update_at时间

        Args:
            conv_id: 会话ID
            userid: 用户ID
            character: 角色名称
            preset: 预设名称

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            create_at = str(datetime.datetime.now())

            # 更新用户的update_at时间
            from utils.db_utils import user_info_update
            user_update_result = user_info_update(userid, "update_at", create_at)
            if not user_update_result:
                return {
                    "success": False,
                    "error": "更新用户时间戳失败"
                }

            command = "INSERT INTO conversations (conv_id, user_id, character, preset, create_at, update_at, delete_mark) VALUES (?, ?, ?, ?, ?, ?, 'yes')"
            result = revise_db(command, (conv_id, userid, character, preset, create_at, create_at))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"创建私聊对话失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_save(conv_id: int) -> dict:
        """
        将私聊对话的delete_mark设置为'no'，表示保存该对话

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = "UPDATE conversations SET delete_mark = 'no' WHERE conv_id = ?"
            result = revise_db(command, (conv_id,))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"保存私聊对话失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_get(conv_id: int) -> dict:
        """
        获取指定私聊对话的角色和预设

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "data": Optional[Tuple[str, str]] (character, preset) 元组，如果未找到则返回None,
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT character, preset FROM conversations WHERE conv_id = ?"
            result = query_db(command, (conv_id,))

            data = result[0] if result else None

            return {
                "success": True,
                "data": data
            }
        except Exception as e:
            logger.error(f"获取私聊对话失败: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_detail_get(conv_id: int) -> dict:
        try:
            command = """
                SELECT conv_id, user_id, character, preset, delete_mark, create_at, update_at, turns
                FROM conversations
                WHERE conv_id = ?
            """
            result = query_db(command, (conv_id,))
            return {
                "success": True,
                "data": result[0] if result else None,
            }
        except Exception as e:
            logger.error(f"获取私聊对话详情失败: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e),
            }

    @staticmethod
    def conversation_latest_message_id_get(conv_id: int) -> dict:
        """
        获取指定会话的最新两条消息的msg_id列表

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "data": List[int] (msg_id列表，如果未找到则返回空列表),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT msg_id FROM dialogs WHERE conv_id = ? ORDER BY turn_order DESC LIMIT 2;"
            result = query_db(command, (conv_id,))

            msg_ids = [row[0] for row in result] if result else []

            return {
                "success": True,
                "data": msg_ids
            }
        except Exception as e:
            logger.error(f"获取最新消息ID失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def conversation_delete_messages(conv_id: int, msg_id: int) -> dict:
        """
        删除指定 conv_id 和 msg_id 的消息记录。如果存在多个 msg_id 相同的行，只删除 id 最大的那一行

        Args:
            conv_id: 会话ID
            msg_id: 消息ID

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            # 1. 获取具有相同 conv_id 和 msg_id 的所有记录，并按 id 降序排序
            query = "SELECT id FROM dialogs WHERE conv_id = ? AND msg_id = ? ORDER BY id DESC"
            rows = query_db(query, (conv_id, msg_id))

            if not rows:
                logger.debug(f"未找到 conv_id 为 {conv_id} 且 msg_id 为 {msg_id} 的消息记录")
                return {
                    "success": False,
                    "error": "未找到匹配的消息记录"
                }

            # 2. 删除 id 最大的那一条记录
            max_id = rows[0][0]
            delete_command = "DELETE FROM dialogs WHERE id = ?"
            result = revise_db(delete_command, (max_id,))

            if result > 0:
                logger.debug(f"成功删除消息记录，conv_id: {conv_id}, msg_id: {msg_id}, id: {max_id}")
            else:
                logger.debug(f"删除消息记录失败，conv_id: {conv_id}, msg_id: {msg_id}, id: {max_id}")

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"删除消息记录时发生错误: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_group_config_get(conv_id: int, group_id: int) -> dict:
        """
        获取指定群聊用户会话关联的群组的角色和预设

        Args:
            conv_id: 会话ID
            group_id: 群组ID

        Returns:
            dict: {
                "success": bool,
                "data": Optional[Tuple[str, str]] (char, preset) 元组，如果未找到则返回None,
                "error": str (如果有错误)
            }
        """
        try:
            if group_id:
                command = "SELECT char, preset FROM groups WHERE group_id = ?"
                result = query_db(command, (group_id,))
            else:
                command = "SELECT group_id FROM group_user_conversations WHERE conv_id = ?"
                result = query_db(command, (conv_id,))
                if result:
                    group_id = result[0][0]
                    command = "SELECT char, preset FROM groups WHERE group_id = ?"
                    result = query_db(command, (group_id,))

            data = result[0] if result else None

            return {
                "success": True,
                "data": data
            }
        except Exception as e:
            logger.error(f"获取群聊配置失败: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_update(conv_id: int, char: str, preset: str) -> dict:
        """
        更新指定私聊对话的角色和预设

        Args:
            conv_id: 会话ID
            char: 角色名称
            preset: 预设名称

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = "UPDATE conversations SET character = ?, preset = ? WHERE conv_id = ?"
            result = revise_db(command, (char, preset, conv_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新私聊对话失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_arg_update(conv_id: int, field: str, value: Union[int, str], increment: bool = False) -> dict:
        """
        更新私聊对话表(conversations)中的指定字段

        Args:
            conv_id: 会话ID
            field: 要更新的字段名
            value: 新的字段值或增量值
            increment: 是否为增量更新，默认为False

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            if increment:
                command = f"UPDATE conversations SET {field} = COALESCE({field}, 0) + ? WHERE conv_id = ?"
            else:
                command = f"UPDATE conversations SET {field} = ? WHERE conv_id = ?"

            result = revise_db(command, (value, conv_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新私聊对话字段失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_delete(conv_id: int) -> dict:
        """
        将指定私聊对话的delete_mark设置为'yes'，标记为删除

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = "UPDATE conversations SET delete_mark = ? WHERE conv_id = ?"
            result = revise_db(command, ("yes", conv_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"删除私聊对话失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_check(conv_id: int) -> dict:
        """
        检查具有指定conv_id的私聊对话是否存在

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "data": bool (True表示不存在，False表示存在),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT conv_id FROM conversations WHERE conv_id = ?"
            result = query_db(command, (conv_id,))

            exists = not bool(result)

            return {
                "success": True,
                "data": exists
            }
        except Exception as e:
            logger.error(f"检查私聊对话存在性失败: {e}")
            return {
                "success": False,
                "data": True,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_get_user(conv_id: int) -> dict:
        """
        获取指定私聊对话的用户ID

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "data": Optional[int] (用户ID，如果未找到则返回None),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT user_id FROM conversations WHERE conv_id = ?"
            result = query_db(command, (conv_id,))

            user_id = result[0][0] if result and result[0] else None

            return {
                "success": True,
                "data": user_id
            }
        except Exception as e:
            logger.error(f"获取私聊对话用户ID失败: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    @staticmethod
    def conversation_private_summary_add(conv_id: int, summary: str) -> dict:
        """
        为指定私聊对话添加或更新总结

        Args:
            conv_id: 会话ID
            summary: 对话总结

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = "UPDATE conversations SET summary = ? WHERE conv_id = ?"
            result = revise_db(command, (summary, conv_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"添加私聊对话总结失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_group_create(conv_id: int, user_id: int, user_name: str, group_id: int, group_name: str) -> dict:
        """
        为指定用户在指定群组中创建一条新的群聊用户会话记录，并更新群组的update_time

        Args:
            conv_id: 会话ID
            user_id: 用户ID
            user_name: 用户名
            group_id: 群组ID
            group_name: 群组名

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            create_at = str(datetime.datetime.now())

            # 更新群组的update_time
            from utils.db_utils import group_info_update
            group_update_result = group_info_update(group_id, "update_time", create_at)
            if not group_update_result:
                return {
                    "success": False,
                    "error": "更新群组时间戳失败"
                }

            command = "INSERT INTO group_user_conversations (user_id, user_name, group_id, group_name, conv_id, create_at, delete_mark) VALUES (?, ?, ?, ?, ?, ?, 'no')"
            result = revise_db(command, (user_id, user_name, group_id, group_name, conv_id, create_at))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"创建群聊对话失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_group_check(conv_id: int) -> dict:
        """
        检查具有指定conv_id且未标记删除的群聊用户会话是否存在

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "data": bool (True表示不存在，False表示存在),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT conv_id FROM group_user_conversations WHERE conv_id = ? AND delete_mark = 'no'"
            result = query_db(command, (conv_id,))

            exists = not bool(result)

            return {
                "success": True,
                "data": exists
            }
        except Exception as e:
            logger.error(f"检查群聊对话存在性失败: {e}")
            return {
                "success": False,
                "data": True,
                "error": str(e)
            }

    @staticmethod
    def conversation_group_get(group_id: int, user_id: int) -> dict:
        """
        获取指定用户在指定群组中未标记删除的群聊用户会话ID

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            dict: {
                "success": bool,
                "data": Optional[int] (会话ID，如果未找到则返回None),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT conv_id FROM group_user_conversations WHERE group_id = ? AND user_id = ? AND delete_mark = 'no'"
            result = query_db(command, (group_id, user_id))

            conv_id = result[0][0] if result else None

            return {
                "success": True,
                "data": conv_id
            }
        except Exception as e:
            logger.error(f"获取群聊对话ID失败: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    @staticmethod
    def conversation_group_update(group_id: int, user_id: int, field: str, value: Union[int, str]) -> dict:
        """
        更新指定用户在指定群组中未标记删除的群聊用户会话的指定字段

        Args:
            group_id: 群组ID
            user_id: 用户ID
            field: 要更新的字段名
            value: 新的字段值

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = f"UPDATE group_user_conversations SET {field} = COALESCE({field}, 0) + ? WHERE group_id = ? AND user_id = ? AND delete_mark = 'no'"
            result = revise_db(command, (value, group_id, user_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新群聊对话字段失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_group_delete(group_id: int, user_id: int) -> dict:
        """
        将指定用户在指定群组中的群聊用户会话标记为删除(delete_mark = 'yes')

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = "UPDATE group_user_conversations SET delete_mark = 'yes' WHERE group_id = ? AND user_id = ?"
            result = revise_db(command, (group_id, user_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"删除群聊对话失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_turns_update(conv_id: int, turn_num: int, chat_type: str = "private") -> dict:
        """
        更新指定会话的对话轮数

        Args:
            conv_id: 会话ID
            turn_num: 新的对话轮数
            chat_type: 对话类型，'private' 或 'group'

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            if chat_type == "private":
                table = "conversations"
            elif chat_type == "group":
                table = "group_user_conversations"
            else:
                return {
                    "success": False,
                    "error": f"未知的 chat_type '{chat_type}'"
                }

            command = f"UPDATE {table} SET turns = ? WHERE conv_id = ?"
            result = revise_db(command, (turn_num, conv_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新对话轮数失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def conversation_group_turns_increment(conv_id: int, turns_increase: int = 0) -> dict:
        try:
            command = """
                UPDATE group_user_conversations
                SET turns = COALESCE(turns, 0) + ?
                WHERE conv_id = ?
            """
            result = revise_db(command, (turns_increase, conv_id))
            return {
                "success": result > 0,
                "data": result,
            }
        except Exception as e:
            logger.error(f"递增群聊对话轮数失败: {e}")
            return {
                "success": False,
                "data": 0,
                "error": str(e),
            }

    @staticmethod
    def dialog_content_add(conv_id: int, role: str, turn_order: int, raw_content: str, processed_content: str, msg_id: Optional[int] = None, chat_type: str = "private") -> dict:
        """
        添加对话内容到相应的对话表，并更新对应会话表的update_at时间戳

        Args:
            conv_id: 会话ID
            role: 角色（如 'user', 'assistant'）
            turn_order: 对话轮次
            raw_content: 原始对话内容
            processed_content: 处理后的对话内容
            msg_id: 消息ID，仅对私聊 ('private') 有效
            chat_type: 对话类型，'private' 或 'group'

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            create_at = str(datetime.datetime.now())

            if chat_type == "private":
                dialog_table = "dialogs"
                conversation_table = "conversations"
                if msg_id is None:
                    return {
                        "success": False,
                        "error": "私聊对话内容添加时 msg_id 不能为空"
                    }
                insert_command = f"INSERT INTO {dialog_table} (conv_id, role, raw_content, turn_order, created_at, processed_content, msg_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
                params = (conv_id, role, raw_content, turn_order, create_at, processed_content, msg_id)
            elif chat_type == "group":
                dialog_table = "group_user_dialogs"
                conversation_table = "group_user_conversations"
                insert_command = f"INSERT INTO {dialog_table} (conv_id, role, raw_content, turn_order, created_at, processed_content) VALUES (?, ?, ?, ?, ?, ?)"
                params = (conv_id, role, raw_content, turn_order, create_at, processed_content)
            else:
                return {
                    "success": False,
                    "error": f"未知的 chat_type '{chat_type}'"
                }

            result = revise_db(insert_command, params)
            if result:
                timestamp_result = ConversationsRepository._update_conversation_timestamp(conv_id, create_at, conversation_table)
                return timestamp_result
            return {
                "success": False,
                "error": "插入对话内容失败"
            }
        except Exception as e:
            logger.error(f"添加对话内容失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def dialog_new_content_add(conv_id: int, turn: int) -> dict:
        """
        在 dialogs 表中插入一条只有 conv_id 和 turn_order 的记录

        Args:
            conv_id: 会话ID
            turn: 对话轮次

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = "INSERT INTO dialogs (conv_id, turn_order) VALUES (?, ?)"
            result = revise_db(command, (conv_id, turn))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"添加新对话内容失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def dialog_latest_del(conv_id: int) -> dict:
        """
        删除指定conv_id中turn_order最大的记录

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "data": int (受影响的行数),
                "error": str (如果有错误)
            }
        """
        try:
            # 步骤1：查询指定conv_id中最大的turn_order
            query_cmd = "SELECT MAX(turn_order) FROM dialogs WHERE conv_id = ?"
            result = query_db(query_cmd, (conv_id,))

            # 检查查询结果，如果没有记录，则返回0
            max_turn_order = result[0][0] if result and result[0][0] is not None else None
            if max_turn_order is None:
                return {
                    "success": True,
                    "data": 0
                }

            # 步骤2：删除该conv_id中turn_order最大的记录
            delete_cmd = "DELETE FROM dialogs WHERE conv_id = ? AND turn_order = ?"
            affected_rows = revise_db(delete_cmd, (conv_id, max_turn_order))

            return {
                "success": True,
                "data": affected_rows
            }
        except Exception as e:
            logger.error(f"删除最新对话失败: {e}")
            return {
                "success": False,
                "data": 0,
                "error": str(e)
            }

    @staticmethod
    def dialog_turn_get(conv_id: int, chat_type: str = "private") -> dict:
        """
        获取指定会话的当前对话轮数

        Args:
            conv_id: 会话ID
            chat_type: 对话类型，'private' 或 'group'

        Returns:
            dict: {
                "success": bool,
                "data": int (最大轮次数，如果不存在则返回 0),
                "error": str (如果有错误)
            }
        """
        try:
            if chat_type == "private":
                table_name = "dialogs"
            elif chat_type == "group":
                table_name = "group_user_dialogs"
            else:
                return {
                    "success": False,
                    "data": 0,
                    "error": f"未知的 chat_type '{chat_type}'"
                }

            command = f"SELECT MAX(turn_order) FROM {table_name} WHERE conv_id = ?"
            result = query_db(command, (conv_id,))

            max_turn = result[0][0] if result and result[0][0] is not None else 0

            return {
                "success": True,
                "data": max_turn
            }
        except Exception as e:
            logger.error(f"获取对话轮数失败: {e}")
            return {
                "success": False,
                "data": 0,
                "error": str(e)
            }

    @staticmethod
    def dialog_content_load(conv_id: int, chat_type: str = "private", raw: bool = False) -> dict:
        """
        加载指定会话的对话内容

        Args:
            conv_id: 会话ID
            chat_type: 对话类型，'private' 或 'group'
            raw: 是否返回原始内容，默认为False，返回处理后的内容

        Returns:
            dict: {
                "success": bool,
                "data": Optional[List[Tuple]] (对话内容列表),
                "error": str (如果有错误)
            }
        """
        try:
            if chat_type == "group":
                table_name = "group_user_dialogs"
            else:  # 默认为 'private' 或其他未知类型也查私聊表
                table_name = "dialogs"
                if chat_type != "private":
                    logger.warning(f"未知的 chat_type '{chat_type}'，默认查询 '{table_name}' 表")

            if raw:
                command = f"SELECT role, turn_order, raw_content FROM {table_name} WHERE conv_id = ?"
            else:
                command = f"SELECT role, turn_order, processed_content FROM {table_name} WHERE conv_id = ?"

            result = query_db(command, (conv_id,))

            return {
                "success": True,
                "data": result if result else []
            }
        except Exception as e:
            logger.error(f"加载对话内容失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def dialog_content_with_timestamps_load(conv_id: int, chat_type: str = "private") -> dict:
        try:
            table_name = "group_user_dialogs" if chat_type == "group" else "dialogs"
            command = f"""
                SELECT role, turn_order, processed_content, created_at
                FROM {table_name}
                WHERE conv_id = ?
                ORDER BY turn_order ASC
            """
            result = query_db(command, (conv_id,))
            return {
                "success": True,
                "data": result if result else [],
            }
        except Exception as e:
            logger.error(f"加载带时间戳的对话内容失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e),
            }

    @staticmethod
    def dialog_last_input_get(conv_id: int) -> dict:
        """
        获取指定会话中最新的用户输入内容

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "data": str (最新的用户输入原始内容，如果不存在则返回空字符串),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT raw_content FROM dialogs WHERE conv_id = ? AND role = 'user' ORDER BY turn_order DESC LIMIT 1;"
            result = query_db(command, (conv_id,))

            content = result[0][0] if result else ""

            return {
                "success": True,
                "data": content
            }
        except Exception as e:
            logger.error(f"获取最后输入失败: {e}")
            return {
                "success": False,
                "data": "",
                "error": str(e)
            }

    @staticmethod
    def dialog_summary_get(conv_id: int) -> dict:
        """
        获取指定会话的总结

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "data": List[dict] (总结内容的列表，每个元素为字典，包含 'summary_area' 和 'content' 字段),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT summary_area, content FROM dialog_summary WHERE conv_id = ?"
            result = query_db(command, (conv_id,))

            if result:
                summaries = [{"summary_area": row[0], "content": row[1]} for row in result]
                return {
                    "success": True,
                    "data": summaries
                }
            else:
                return {
                    "success": True,
                    "data": []
                }
        except Exception as e:
            logger.error(f"获取对话摘要失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def dialog_summary_location_get(conv_id: int) -> dict:
        """
        获取指定对话已总结到的最大轮数

        Args:
            conv_id: 会话ID

        Returns:
            dict: {
                "success": bool,
                "data": Optional[int] (已总结到的最大轮数),
                "error": str (如果有错误)
            }
        """
        try:
            summaries_result = ConversationsRepository.dialog_summary_get(conv_id)
            if not summaries_result["success"]:
                return summaries_result

            summaries = summaries_result["data"]
            if not summaries:
                return {
                    "success": True,
                    "data": None
                }

            max_turn = 0
            for summary in summaries:
                # 解析summary_area字段,格式为"起始轮数-结束轮数"
                try:
                    end_turn = int(summary['summary_area'].split('-')[1])
                    max_turn = max(max_turn, end_turn)
                except (ValueError, IndexError):
                    continue

            return {
                "success": True,
                "data": max_turn if max_turn > 0 else None
            }
        except Exception as e:
            logger.error(f"获取摘要位置失败: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    @staticmethod
    def dialog_summary_add(conv_id: int, summary_area: str, content: str) -> dict:
        """
        向指定会话添加总结

        Args:
            conv_id: 会话ID
            summary_area: 总结区域标识，例如 '1-30'
            content: 总结内容

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = "INSERT INTO dialog_summary (conv_id, summary_area, content) VALUES (?, ?, ?)"
            result = revise_db(command, (conv_id, summary_area, content))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"添加对话摘要失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
