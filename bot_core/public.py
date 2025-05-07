import logging
from typing import Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from utils import file_utils as file, db_utils as db
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


def print_api_list(tier: int) -> Union[str, InlineKeyboardMarkup]:
    """
    显示API列表，根据用户账户等级过滤API选项。
    Args:
        tier: 用户账户等级。
    Returns:
        Union[str, InlineKeyboardMarkup]: 如果没有符合条件的API返回提示，否则返回键盘标记。
    """
    try:
        api_list = file.load_config()['api']
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


def print_conversations(user_id:int, conv_type: str = 'load') -> Union[str, InlineKeyboardMarkup]:
    """
    显示用户对话列表。

    Args:
        user_id (Update): Telegram用户id。
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


def print_char_list(operate_type: str, chat_type: str, id: int) -> list or str:
    """
        筛选角色列表。

        Args:
            operate_type (str): 操作类型，load或delete。
            chat_type (str): 消息类型，私聊或群聊。
            id(int): 私聊或群聊id。

        Returns:
            keyboard: 筛选后的inline按钮或str
        """
    try:
        char_list = file.list_all_characters()
        keyboard = []
        for char in char_list:
            if operate_type == 'load' and chat_type == 'private':
                if char.endswith("_public") or char.endswith(f"_{id}"):
                    keyboard.append([InlineKeyboardButton(char.split('_')[0], callback_data=f"set_char_{char}")])
            elif operate_type == 'del' and chat_type == 'private':
                if char.endswith(f"_{id}"):
                    keyboard.append([InlineKeyboardButton(char.split('_')[0], callback_data=f"del_char_{char}")])
            elif operate_type == 'load' and chat_type == 'group':
                if char.endswith("_public") or char.endswith(f"_{id}"):
                    keyboard.append([InlineKeyboardButton(char.split('_')[0], callback_data=f"group_char_{char}_{id}")])
            elif operate_type == 'del' and chat_type == 'group':
                if char.endswith(f"_{id}"):
                    keyboard.append(
                        [InlineKeyboardButton(char.split('_')[0], callback_data=f"group_delchar_{char}_{id}")])
        if keyboard == []:
            return "没有可操作的角色。"
        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"获取角色菜单失败, 错误: {str(e)}")
        raise DatabaseError(f"获取用户对话列表失败: {str(e)}")
