import datetime
import logging
from typing import Dict
from telegram import Update
from utils import db_utils as db,file_utils as file
ADMIN = file.load_config()['admin']
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
        if result:
            return {'user_name':f"{result[0]}{result[1]}",'first_name': result[0], 'last_name': result[1],'tier': result[2],'remain': result[3],'balance': result[4]}
        else:
            return{}
    except Exception as e:
        logger.error(f"获取用户信息失败, user_id: {user_id}, 错误: {str(e)}")
        raise DatabaseError(f"获取用户信息失败: {str(e)}")

def info_update(user_id, user_name, first_name, last_name) -> str:
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
            db.user_config_create(user_id)
            result = db.user_config_get(user_id)
            logger.info(f"为新用户{user_id}创建默认配置")
        return {'char':result[0],'api':result[1],'preset':result[2],'conv_id':result[3],'stream':result[4],'user_id':user_id}
    except Exception as e:
        logger.error(f"获取用户配置失败, user_id: {user_id}, 错误: {str(e)}")
        raise DatabaseError(f"获取用户配置失败: {str(e)}")

def stream_switch(user_id) -> bool:
    return db.user_stream_switch(user_id)

def is_admin(user_id) ->bool:
    return True if user_id in ADMIN else False
