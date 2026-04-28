"""
users_repository.py - 用户表(users)相关的CRUD操作
"""

import datetime
import logging
from typing import Any, List, Optional, Tuple, Union

from utils.config_utils import get_default_balance, get_default_frequency
from utils.db_utils import query_db, revise_db
from utils.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class UsersRepository:
    """用户表相关的数据库操作"""

    @staticmethod
    def user_info_check(userid: int) -> dict:
        """
        检查用户是否在users表中存在

        Args:
            userid: 用户ID

        Returns:
            dict: {
                "success": bool,
                "exists": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT uid FROM users WHERE uid = ?"
            result = query_db(command, (userid,))
            exists = bool(result)

            return {
                "success": True,
                "exists": exists
            }
        except Exception as e:
            logger.error(f"检查用户存在性失败: {e}")
            return {
                "success": False,
                "exists": False,
                "error": str(e)
            }

    @staticmethod
    def user_conversations_get(userid: int) -> dict:
        """
        获取用户未标记为删除的私聊对话列表

        Args:
            userid: 用户ID

        Returns:
            dict: {
                "success": bool,
                "data": List[Tuple] (conv_id, character, summary, update_at, turns),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT conv_id, character, summary, update_at, turns FROM conversations WHERE user_id = ? AND delete_mark = 'no'"
            result = query_db(command, (userid,))

            return {
                "success": True,
                "data": result if result else []
            }
        except Exception as e:
            logger.error(f"获取用户对话列表失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def user_all_conversations_get(userid: int) -> dict:
        """
        获取用户所有的私聊对话列表，包括已删除的

        Args:
            userid: 用户ID

        Returns:
            dict: {
                "success": bool,
                "data": List[Tuple] (conv_id, character, summary, update_at, turns),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT conv_id, character, summary, update_at, turns FROM conversations WHERE user_id = ?"
            result = query_db(command, (userid,))

            return {
                "success": True,
                "data": result if result else []
            }
        except Exception as e:
            logger.error(f"获取用户所有对话列表失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def user_conversations_get_for_dialog(userid: int) -> dict:
        """
        获取用户未标记为删除的私聊对话列表，用于dialog命令

        Args:
            userid: 用户ID

        Returns:
            dict: {
                "success": bool,
                "data": List[Tuple] (conv_id, character, turns, update_at, summary),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT conv_id, character, turns, update_at, summary FROM conversations WHERE user_id = ? AND delete_mark = 'no' ORDER BY update_at DESC"
            result = query_db(command, (userid,))

            return {
                "success": True,
                "data": result if result else []
            }

        except Exception as e:
            logger.error(f"获取用户对话列表（用于dialog）失败: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    @staticmethod
    def user_conversations_count_update(user_id: int) -> dict:
        """
        重新计算并更新用户的私聊对话总数

        Args:
            user_id: 用户ID

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            # 使用 user_all_conversations_get 获取所有对话列表
            conversations_result = UsersRepository.user_all_conversations_get(user_id)
            if not conversations_result["success"]:
                return conversations_result

            count = len(conversations_result["data"]) if conversations_result["data"] else 0

            # 使用 user_info_update 更新 users 表中的 conversations 字段
            update_result = UsersRepository.user_info_update(user_id, 'conversations', count)

            return update_result
        except Exception as e:
            logger.error(f"更新用户对话总数失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def user_info_get(userid: int) -> dict:
        """
        获取用户的基本信息

        Args:
            userid: 用户ID

        Returns:
            dict: {
                "success": bool,
                "data": dict (first_name, last_name, user_name, account_tier, remain_frequency, balance, uid),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT first_name, last_name, user_name, account_tier, remain_frequency, balance, uid FROM users WHERE uid = ?"
            result = query_db(command, (userid,))

            if result:
                return {
                    "success": True,
                    "data": {
                        "first_name": result[0][0],
                        "last_name": result[0][1],
                        "user_name": result[0][2],
                        "account_tier": result[0][3],
                        "remain_frequency": result[0][4],
                        "balance": result[0][5],
                        "uid": result[0][6]
                    }
                }
            else:
                return {
                    "success": True,
                    "data": {}
                }
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return {
                "success": False,
                "data": {},
                "error": str(e)
            }

    @staticmethod
    def user_info_usage_get(userid: int, column_name: str) -> dict:
        """
        获取用户users表中指定列的信息

        Args:
            userid: 用户ID
            column_name: 要查询的列名

        Returns:
            dict: {
                "success": bool,
                "data": Any,
                "error": str (如果有错误)
            }
        """
        try:
            # SQL注入风险警告：column_name 未经验证直接拼接到查询中。
            # 仅在 column_name 确定安全的情况下使用。
            allowed_columns = {
                "first_name", "last_name", "user_name", "create_at", "update_at",
                "input_tokens", "output_tokens", "account_tier", "remain_frequency", "balance"
            }

            if column_name not in allowed_columns:
                error_msg = f"错误: 查询了不允许的列名: {column_name}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "data": 0,
                    "error": error_msg
                }

            command = f"SELECT {column_name} FROM users WHERE uid = ?"
            result = query_db(command, (userid,))

            return {
                "success": True,
                "data": result[0][0] if result and result[0] else 0
            }
        except Exception as e:
            logger.error(f"获取用户列信息失败: {e}")
            return {
                "success": False,
                "data": 0,
                "error": str(e)
            }

    @staticmethod
    def user_info_create(userid: int, first_name: str, last_name: str, user_name: str) -> dict:
        """
        创建用户信息

        Args:
            userid: 用户ID
            first_name: 名字
            last_name: 姓氏
            user_name: 用户名

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            create_at = str(datetime.datetime.now())
            command = """
                INSERT INTO users(uid, first_name, last_name, user_name, create_at, update_at, input_tokens, output_tokens, account_tier, remain_frequency, balance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            result = revise_db(
                command,
                (
                    userid,
                    first_name,
                    last_name,
                    user_name,
                    create_at,
                    create_at,
                    0,
                    0,
                    0,
                    get_default_frequency(),
                    get_default_balance(),
                ),
            )

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"创建用户信息失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def user_info_update(userid: int, field: str, value: Any, increment: bool = False) -> dict:
        """
        更新用户信息

        Args:
            userid: 用户ID
            field: 需要更新的字段名
            value: 更新值或增量值
            increment: 是否为增量更新，默认为False

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            uid = int(userid)

            if increment:
                command = f"UPDATE users SET {field} = COALESCE({field}, 0) + ? WHERE uid = ?"
            else:
                command = f"UPDATE users SET {field} = ? WHERE uid = ?"

            result = revise_db(command, (value, uid))

            return {
                "success": result > 0
            }
        except ValueError:
            # 不是数字则按用户名处理，转换为小写并去除可能的前缀
            userid_str = str(userid).lower()[1:] if len(str(userid)) > 1 else ""

            if increment:
                command = f"UPDATE users SET {field} = COALESCE({field}, 0) + ? WHERE LOWER(user_name) = ?"
            else:
                command = f"UPDATE users SET {field} = ? WHERE LOWER(user_name) = ?"

            result = revise_db(command, (value, userid_str))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新用户信息失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def user_frequency_free(value: int) -> dict:
        """
        为所有用户的remain_frequency增加指定值

        Args:
            value: 要增加的值

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = f"UPDATE users SET remain_frequency = COALESCE(remain_frequency, 0) + ?"
            result = revise_db(command, (value,))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"为所有用户增加频率失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
