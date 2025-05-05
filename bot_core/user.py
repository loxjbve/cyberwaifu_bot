import datetime
import logging
from typing import Dict
from telegram import Update
from utils import db_utils as db

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


def info_get(user_id) -> Dict:
    try:
        result = db.user_info_get(user_id)
        return {'first_name': result[0], 'last_name': result[1],'tier': result[2],'remain': result[3],'balance': result[4]}
    except Exception as e:
        logger.error(f"获取用户信息失败, user_id: {user_id}, 错误: {str(e)}")
        raise DatabaseError(f"获取用户信息失败: {str(e)}")

def info_update_or_create(user_id, user_name, first_name, last_name) -> str:
    try:
        if db.user_config_check(user_id):
            db.user_info_update(user_id, 'first_name', first_name)
            db.user_info_update(user_id, 'last_name', last_name)
            db.user_info_update(user_id, 'user_name', user_name)
            current_time = str(datetime.datetime.now())
            db.user_info_update(user_id, 'update_at', current_time)
            return "已成功更新您的信息"
        else:
            db.user_info_create(user_id, first_name, last_name, user_name)
            return "已为您创建信息"
    except Exception as e:
        logger.error(f"更新或创建用户信息失败, user_id: {user_id}, 错误: {str(e)}")
        raise DatabaseError(f"更新或创建用户信息失败: {str(e)}")


def config_get(user_id) -> Dict:
    try:
        result = db.user_config_get(user_id)
        if not result:
            db.user_config_new(user_id)
            result = db.user_config_get(user_id)
        return {'char':result[0],'api':result[1],'preset':result[2],'conv_id':result[3],'stream':result[4]}
    except Exception as e:
        logger.error(f"获取用户配置失败, user_id: {user_id}, 错误: {str(e)}")
        raise DatabaseError(f"获取用户配置失败: {str(e)}")

def stream_switch(user_id) -> bool:
    return db.user_stream_switch(user_id)

async def group_info_update_or_create(update,context) -> bool:
    """
    更新或创建群组信息。

    Args:
        update (Update): Telegram更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。

    Returns:
        bool: 操作是否成功。
    """
    group_id = update.message.chat.id
    group_name = update.message.chat.title
    current_time = str(datetime.datetime.now())
    try:
        if db.group_check_update(group_id):
            logger.info(f"更新群组信息, group_name: {group_name}, time: {current_time}")
            admins = await context.bot.get_chat_administrators(group_id)
            admin_list = [admin.user.id for admin in admins]
            config = db.group_config_get(group_id)
            if config:
                api, char, preset = config[0], config[1], config[2]
            else:
                db.group_info_create(group_id)
                api, char, preset = 'gemini-2', 'cuicuishark', 'Default_meeting'
            field_list = ['group_name', 'update_time', 'members_list', 'api', 'char', 'preset']
            value_list = [group_name, current_time, str(admin_list), api, char, preset]
            for field, value in zip(field_list, value_list):
                db.group_info_update(group_id, field, value)
            return True
        return False
    except Exception as e:
        logger.error(f"更新或创建群组信息失败, group_id: {group_id}, 错误: {str(e)}")
        raise DatabaseError(f"更新或创建群组信息失败: {str(e)}")
