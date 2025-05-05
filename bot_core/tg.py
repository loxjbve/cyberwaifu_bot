import asyncio
import datetime
import random
import re
import logging
import functools
from functools import lru_cache, wraps
from typing import Tuple, List, Optional, Union, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from telegram import Update
from datetime import datetime
from datetime import timedelta
# 设置日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
# 获取全局 logger
logger = logging.getLogger(__name__)
# 单独设置 httpx 的日志级别为 WARNING，屏蔽 INFO 级别日志
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)
httpx_logger.propagate = True

class BotError(Exception):
    """自定义Bot异常基类"""
    pass


class DatabaseError(BotError):
    """数据库操作相关异常"""
    pass


class LLMError(BotError):
    """LLM服务调用相关异常"""
    pass

def is_private_chat(update: Update) -> bool:
    """
    检查消息是否来自私聊。

    Args:
        update (Update): Telegram更新对象。

    Returns:
        bool: 如果是私聊返回True，否则返回False。
    """
    return update.message.chat.type == 'private'

def user_info_get(update: Update) -> Dict:
    """
    获取Telegram用户信息。

    Args:
        update (Update): Telegram更新对象。

    Returns:
        Tuple[int, str, str, str]: 用户ID、用户名、名、姓。
    """
    user = update.message.from_user
    user_id = user.id
    username = user.username or ''
    first_name = user.first_name or ''
    last_name = user.last_name or ''
    text = update.message.text or ''
    msg_id = update.message.message_id or 0
    return {'user_id': user_id, 'username': username, 'first_name': first_name, 'last_name': last_name,'text': text,'msg_id': msg_id}

@lru_cache(maxsize=1000)
def is_message_expired(update: Update) -> bool:
    """
    检查消息是否过期（超过30秒）。

    Args:
        update (Update): Telegram 更新对象。

    Returns:
        bool: 如果消息过期返回 True，否则返回 False。
    """
    if update.message is None or update.message.date is None:
        return False  # 如果没有消息或时间信息，默认不过期
    current_time = datetime.now(update.message.date.tzinfo)  # 获取当前时间，匹配时区
    time_diff = current_time - update.message.date
    logger.debug(f"检查消息是否过期，时间差: {time_diff}")
    return time_diff > timedelta(seconds=30)

async def group_msg_parse(update: Update) -> Dict:
    """
    解析群聊消息内容。

    Args:
        update (Update): Telegram更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。

    Returns:
        Union[Tuple[int, str, int, str, str, int], bool]: 解析结果或False。
    """
    try:
        if not update.message:
            raise ValueError("Update 中不包含消息对象")
        group_id = update.message.chat.id
        group_name = update.message.chat.title if update.message.chat.title else "未知群聊"
        user = update.message.from_user
        user_id = user.id
        first_name = user.first_name if user.first_name else ""
        last_name = user.last_name if user.last_name else ""
        user_name = f"{first_name} {last_name}".strip() if first_name or last_name else "未知用户"
        message_text = update.message.text if update.message.text else ""
        if not message_text and update.message.caption:
            message_text = update.message.caption
        message_id = update.message.message_id
        return {'group_id': group_id, 'user_id': user_id, 'message_id': message_id, 'message_text': message_text,'group_name': group_name,'user_name': user_name}
    except Exception as e:
        logger.error(f"解析群聊消息失败, 错误: {str(e)}")
        return False