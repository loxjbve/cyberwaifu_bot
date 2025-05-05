import datetime
import random
import logging
from typing import Union
from telegram import Update
from telegram.ext import ContextTypes
from utils import db_utils as db
from bot_core import tg

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



async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE, check_type: str = 'msg') -> bool:
    """
    检查用户是否为群组管理员。

    Args:
        update (Update): Telegram更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
        check_type (str): 检查类型，msg或callback。

    Returns:
        bool: 是否为管理员。
    """
    try:
        if check_type == 'msg':
            group_info = await tg.group_msg_parse(update)
            group_id = group_info['group_id']
            user_id = group_info['user_id']
        else:
            callback_query = update.callback_query
            user_id = callback_query.from_user.id
            group_id = callback_query.message.chat.id
        admin_list = db.group_admin_list_get(group_id)
        #print(f"{group_id}管理员列表：{admin_list}，用户id:{user_id}")
        return (user_id in admin_list) or str(user_id) == '7007822593'
    except Exception as e:
        logger.error(f"检查管理员权限失败, group_id: {group_id}, 错误: {str(e)}")
        raise DatabaseError(f"检查管理员权限失败: {str(e)}")


async def msg_needs_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Union[str, bool]:
    """
    检查群聊消息是否需要回复。

    Args:
        update (Update): Telegram更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。

    Returns:
        Union[str, bool]: 触发类型或False。
    """
    message = update.message
    bot_username = context.bot.username
    group_info = await tg.group_msg_parse(update)
    message_text = group_info['message_text']
    group_id = group_info['group_id']
    group_name = group_info['group_name']
    user_name = group_info['user_name']
    keyword_list = db.group_keyword_get(group_id)
    try:
        if message.reply_to_message:
            if message.reply_to_message.from_user.id == context.bot.id:
                logger.info(f"触发回复Bot, group_name: {group_name}, user_name: {user_name}")
                return 'reply'
            else:
                if message_text:
                    if f"@{bot_username}" in message_text:
                        logger.info(f"触发@Bot, group_name: {group_name}, user_name: {user_name}")
                        return '@'
                    if keyword_list and any(keyword in message_text for keyword in keyword_list):
                        logger.info(f"触发关键词, group_name: {group_name}, user_name: {user_name}")
                        return 'keyword'
                    if random.random() < 0.1:
                        logger.info(f"触发随机回复, group_name: {group_name}, user_name: {user_name}")
                        return 'random'
        if message_text:
            if f"@{bot_username}" in message_text:
                logger.info(f"触发@Bot, group_name: {group_name}, user_name: {user_name}")
                return '@'
            if keyword_list and any(keyword in message_text for keyword in keyword_list):
                logger.info(f"触发关键词, group_name: {group_name}, user_name: {user_name}")
                return 'keyword'
            if random.random() < 0.1:
                logger.info(f"触发随机回复, group_name: {group_name}, user_name: {user_name}")
                return 'random'
        logger.info(f"未触发任何条件, group_name: {group_name}, user_name: {user_name}")
        return False
    except Exception as e:
        logger.error(f"检查群聊消息是否需要回复失败, group_id: {group_id}, 错误: {str(e)}")
        raise BotError(f"检查群聊消息是否需要回复失败: {str(e)}")

async def dialog_add(group_info) -> bool:
    message_id = group_info['message_id']
    message_text = group_info['message_text']
    group_id = group_info['group_id']
    group_name = group_info['group_name']
    user_id = group_info['user_id']
    user_name = group_info['user_name']

    current_time = str(datetime.datetime.now())
    try:
        if db.group_dialog_add(message_id, group_id):
            field_list = ['group_id', 'group_name', 'create_at', 'msg_user', 'msg_user_name', 'msg_text']
            value_list = [group_id, group_name, current_time, user_id, user_name, message_text]
            for field, value in zip(field_list, value_list):
                db.group_dialog_update(message_id, field, value, group_id)
            return True
        return False
    except Exception as e:
        logger.error(f"添加群聊对话记录失败, group_id: {group_id}, 错误: {str(e)}")
        raise DatabaseError(f"添加群聊对话记录失败: {str(e)}")