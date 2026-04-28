"""
user_config_repository.py - 用户配置表(user_config)相关的CRUD操作
"""

import logging
from typing import Any, Optional

from utils.config_utils import (
    get_default_api,
    get_default_char,
    get_default_preset,
    get_default_stream,
)
from utils.db_utils import query_db, revise_db
from utils.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class UserConfigRepository:
    """用户配置表相关的数据库操作"""

    @staticmethod
    def user_config_get(userid: int) -> dict:
        """
        获取用户的完整配置信息

        Args:
            userid: 用户ID

        Returns:
            dict: {
                "success": bool,
                "data": dict (char, api, preset, conv_id, stream, nick),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT char, api, preset, conv_id, stream, nick FROM user_config WHERE uid = ?"
            result = query_db(command, (userid,))

            if result:
                return {
                    "success": True,
                    "data": {
                        "char": result[0][0],
                        "api": result[0][1],
                        "preset": result[0][2],
                        "conv_id": result[0][3],
                        "stream": result[0][4],
                        "nick": result[0][5],
                    }
                }
            else:
                return {
                    "success": True,
                    "data": {}
                }
        except Exception as e:
            logger.error(f"获取用户配置失败: {e}")
            return {
                "success": False,
                "data": {},
                "error": str(e)
            }

    @staticmethod
    def user_conv_id_get(user_id: int) -> dict:
        """
        获取用户当前激活的对话ID

        Args:
            user_id: 用户ID

        Returns:
            dict: {
                "success": bool,
                "data": int (对话ID，如果未找到或未设置则返回0),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT conv_id FROM user_config WHERE uid = ?"
            result = query_db(command, (user_id,))

            conv_id = result[0][0] if result and result[0] and result[0][0] is not None else 0

            return {
                "success": True,
                "data": conv_id
            }
        except Exception as e:
            logger.error(f"获取用户对话ID失败: {e}")
            return {
                "success": False,
                "data": 0,
                "error": str(e)
            }

    @staticmethod
    def user_api_get(userid: int) -> dict:
        """
        获取用户配置的API

        Args:
            userid: 用户ID

        Returns:
            dict: {
                "success": bool,
                "data": str (用户配置的API，如果未找到或未设置则返回空字符串),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT api FROM user_config WHERE uid = ?"
            result = query_db(command, (userid,))

            api = result[0][0] if result else ""

            return {
                "success": True,
                "data": api
            }
        except Exception as e:
            logger.error(f"获取用户API配置失败: {e}")
            return {
                "success": False,
                "data": "",
                "error": str(e)
            }

    @staticmethod
    def user_stream_get(userid: int) -> dict:
        """
        获取用户是否开启流式传输

        Args:
            userid: 用户ID

        Returns:
            dict: {
                "success": bool,
                "data": Optional[bool] (是否开启流式传输，如果未找到配置则返回None),
                "error": str (如果有错误)
            }
        """
        try:
            command = "SELECT stream FROM user_config WHERE uid = ?"
            result = query_db(command, (userid,))

            stream = True if result and result[0][0] == "yes" else False

            return {
                "success": True,
                "data": stream
            }
        except Exception as e:
            logger.error(f"获取用户流式传输配置失败: {e}")
            return {
                "success": False,
                "data": False,
                "error": str(e)
            }

    @staticmethod
    def user_stream_switch(userid: int) -> dict:
        """
        切换用户的流式传输设置

        Args:
            userid: 用户ID

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            # 首先获取当前的流式传输设置
            current_stream_result = UserConfigRepository.user_stream_get(userid)
            if not current_stream_result["success"]:
                return current_stream_result

            current_stream = current_stream_result["data"]

            # 切换设置
            if current_stream:
                command = "UPDATE user_config SET stream = 'no' WHERE uid = ?"
            else:
                command = "UPDATE user_config SET stream = 'yes' WHERE uid = ?"

            result = revise_db(command, (userid,))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"切换用户流式传输设置失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def user_config_arg_update(user_id: int, field: str, value: Any) -> dict:
        """
        更新用户配置表中的指定字段

        Args:
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
            command = f"UPDATE user_config SET {field} = ? WHERE uid = ?"
            result = revise_db(command, (value, user_id))

            return {
                "success": result > 0
            }
        except Exception as e:
            logger.error(f"更新用户配置字段失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def user_config_create(userid: int, nick: Optional[str] = None) -> dict:
        """
        为新用户创建默认配置。如果用户已存在，则不执行任何操作

        Args:
            userid: 用户ID
            nick: 用户的昵称 (可选)

        Returns:
            dict: {
                "success": bool,
                "error": str (如果有错误)
            }
        """
        try:
            command = (
                "INSERT OR IGNORE INTO user_config (char, api, preset, uid, stream, nick) VALUES (?, ?, ?, ?, ?, ?)"
            )
            params = (
                get_default_char(),
                get_default_api(),
                get_default_preset(),
                userid,
                get_default_stream(),
                nick,
            )
            result = revise_db(command, params)

            # INSERT OR IGNORE 成功时返回0，所以用 >= 0 判断
            return {
                "success": result >= 0
            }
        except Exception as e:
            logger.error(f"为新用户创建配置失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
