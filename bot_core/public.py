import logging
from typing import Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from utils import file_utils as file, db_utils as db

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

def print_char_list(update: Update, char_type: str = 'private') -> Union[str, InlineKeyboardMarkup]:
    """
    显示角色列表。

    Args:
        update (Update): Telegram更新对象。
        char_type (str): 类型，private或group。

    Returns:
        Union[str, InlineKeyboardMarkup]: 如果没有角色返回提示，否则返回键盘标记。
    """
    try:
        characters = file.list_characters()
        if not characters:
            return "没有可用的角色。"
        if char_type == 'private':
            keyboard = [
                [InlineKeyboardButton(char, callback_data=f"set_char_{char}")] for char in characters
            ]
        else:
            group_id = update.message.chat.id
            keyboard = [
                [InlineKeyboardButton(char, callback_data=f"group_char_{char}_{group_id}")] for char in characters
            ]
        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"获取角色列表失败, 错误: {str(e)}")
        raise BotError(f"获取角色列表失败: {str(e)}")

def print_api_list(tier) -> Union[str, InlineKeyboardMarkup]:
    """
    显示API列表，根据用户账户等级过滤API选项。
    Args:
        update: Telegram 更新对象，用于获取用户信息。
    Returns:
        Union[str, InlineKeyboardMarkup]: 如果没有符合条件的API返回提示，否则返回键盘标记。
    """
    try:
        _, api_list = file.load_config()
        if not api_list:
            return "没有可用的api。"

        # 过滤API列表，只保留group小于或等于用户tier的API
        filtered_api_list = [api for api in api_list if api.get('group', 0) <= tier]

        if not filtered_api_list:
            return "没有符合您账户等级的可用api。"

        keyboard = [
            [InlineKeyboardButton(api['name'], callback_data=f"set_api_{api['name']}")]
            for api in filtered_api_list
        ]
        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"获取API列表失败, 错误: {str(e)}")
        raise BotError(f"获取API列表失败: {str(e)}")

def print_preset_list() -> Union[str, InlineKeyboardMarkup]:
    """
    显示预设列表。

    Returns:
        Union[str, InlineKeyboardMarkup]: 如果没有预设返回提示，否则返回键盘标记。
    """
    try:
        preset_list = file.load_prompts()
        if not preset_list:
            return "没有可用的预设。"
        keyboard = [
            [InlineKeyboardButton(preset['display'], callback_data=f"set_preset_{preset['name']}")]
            for preset in preset_list
        ]
        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"获取预设列表失败, 错误: {str(e)}")
        raise BotError(f"获取预设列表失败: {str(e)}")

def print_conversations(user_id, conv_type: str = 'load') -> Union[str, InlineKeyboardMarkup]:
    """
    显示用户对话列表。

    Args:
        update (Update): Telegram更新对象。
        conv_type (str): 操作类型，load或delete。

    Returns:
        Union[str, InlineKeyboardMarkup]: 如果没有对话返回提示，否则返回键盘标记。
    """

    try:
        conv_list = db.user_conversations_get(user_id)
        logger.info(f"获取用户对话列表, user_id: {user_id}")
        if not conv_list:
            return "没有可用的对话。"
        keyboard = [
            [InlineKeyboardButton(f"{conv[1]}： {conv[2]}",
                                  callback_data=f"{'set' if conv_type == 'load' else 'del'}_conv_{conv[0]}")]
            for conv in conv_list
        ]
        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"获取用户对话列表失败, user_id: {user_id}, 错误: {str(e)}")
        raise DatabaseError(f"获取用户对话列表失败: {str(e)}")

