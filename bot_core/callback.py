import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils import db_utils as db
from bot_core import group
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


# 自定义异常类
class BotError(Exception):
    """自定义Bot异常基类"""
    pass


class DatabaseError(BotError):
    """数据库操作相关异常"""
    pass


class CallbackHandler:
    """回调处理类"""

    handlers = {
        'set_char_': '_handle_set_character',
        'set_api_': '_handle_set_api',
        'set_preset_': '_handle_set_preset',
        'set_conv_': '_handle_set_conversation',
        'del_conv_': '_handle_delete_conversation',
        'group_char_': '_handle_group_character_callback'
    }

    @staticmethod
    async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理回调查询"""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id
        try:
            if data.startswith("set_char_"):
                await _handle_set_character(update, data[9:], user_id)
            elif data.startswith("del_char"):
                await _handle_del_character(update,data[9:],user_id)
            elif data.startswith("set_api_"):
                await _handle_set_api(update, data[8:], user_id)
            elif data.startswith("set_preset_"):
                await _handle_set_preset(update, data[11:], user_id)
            elif data.startswith("set_conv_"):
                await _handle_set_conversation(update, data[9:], user_id)
            elif data.startswith("del_conv_"):
                await _handle_delete_conversation(update, data[9:])
            elif data.startswith("group_char_"):
                parts = data.split('_')
                print(f"parts{parts}")
                if len(parts) != 5 or parts[0] != 'group' or parts[1] != 'char':
                    raise ValueError("Invalid string format")
                await _handle_group_character(update, context, f"{parts[2]}_{parts[3]}", int(parts[4]))
        except Exception as e:
            logger.error(f"处理回调查询失败, user_id: {user_id}, data: {data}, 错误: {str(e)}")
            raise BotError(f"处理回调{data} 失败: {str(e)}")


async def _handle_set_character(update: Update, character: str, user_id: int) -> None:
    """
    处理角色设置回调。

    Args:
        update (Update): Telegram更新对象。
        character (str): 角色名。
        user_id (int): 用户ID。
    """
    _, api, preset, conv_id,_ = db.user_config_get(user_id)
    db.user_config_update(user_id, character, api, preset, conv_id)
    db.conversation_private_update(conv_id, character, preset)
    await update.callback_query.message.edit_text(f"角色切换成功！当前角色: {character.split('_')[0]}。")

async def _handle_del_character(update: Update, character: str, user_id: int) -> None:
    """
    处理角色设置回调。

    Args:
        update (Update): Telegram更新对象。
        character (str): 角色名。
        user_id (int): 用户ID。
    """
    import os
    _, api, preset, conv_id,_ = db.user_config_get(user_id)
    db.user_config_update(user_id, 'cuicuishark_public', api, preset, conv_id)
    db.conversation_private_update(conv_id, character, preset)
    # 处理角色文件重命名逻辑
    char_dir = './characters/'
    json_path = os.path.join(char_dir, f'{character}.json')
    txt_path = os.path.join(char_dir, f'{character}.txt')
    if os.path.exists(json_path):
        del_path = os.path.join(char_dir, f'{character}_del.json')
        os.rename(json_path, del_path)
    elif os.path.exists(txt_path):
        del_path = os.path.join(char_dir, f'{character}_del.txt')
        os.rename(txt_path, del_path)
    await update.callback_query.message.edit_text(f"角色`{character.split('_')[0]}`删除成功！已为您切换默认角色`cuicuishark` 。")

async def _handle_set_api(update: Update, api: str, user_id: int) -> None:
    """
    处理API设置回调。

    Args:
        update (Update): Telegram更新对象。
        api (str): API名。
        user_id (int): 用户ID。
    """
    char, _, preset, conv_id,_ = db.user_config_get(user_id)
    db.user_config_update(user_id, char, api, preset, conv_id)
    await update.callback_query.message.edit_text(f"角色切换成功！当前api: {api}。")


async def _handle_set_preset(update: Update, preset: str, user_id: int) -> None:
    """
    处理预设设置回调。

    Args:
        update (Update): Telegram更新对象。
        preset (str): 预设名。
        user_id (int): 用户ID。
    """
    char, api, _, conv_id,_ = db.user_config_get(user_id)
    db.user_config_update(user_id, char, api, preset, conv_id)
    db.conversation_private_update(conv_id, char, preset)
    await update.callback_query.message.edit_text(f"预设切换成功！当前预设: {preset}。")


async def _handle_set_conversation(update: Update, conv_id: int, user_id: int) -> None:
    """
    处理对话加载回调。

    Args:
        update (Update): Telegram更新对象。
        conv_id (str): 对话ID。
        user_id (int): 用户ID。
    """
    _, api, _, _,_ = db.user_config_get(user_id)
    char, preset = db.conversation_private_get(conv_id)
    db.user_config_update(user_id, char, api, preset, conv_id)
    db.conversation_private_update(conv_id, char, preset)
    await update.callback_query.message.edit_text(f"加载对话成功！当前对话: {conv_id}。")


async def _handle_delete_conversation(update: Update, conv_id: int) -> None:
    """
    处理对话删除回调。

    Args:
        update (Update): Telegram更新对象。
        conv_id (str): 对话ID。
    """
    db.conversation_private_delete(conv_id)
    await update.callback_query.message.edit_text(f"删除对话成功！删除了对话: {conv_id}。")


async def _handle_group_character(update: Update, context: ContextTypes.DEFAULT_TYPE, char: str, group_id: int) -> None:
    """
    处理群聊角色设置回调。

    Args:
        update (Update): Telegram更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
        char (str): 角色名。
        group_id (int): 群聊ID。
    """
    if not await group.admin_check(update, context, 'callback'):
        await update.callback_query.answer("仅管理员可操作", show_alert=True)
        return
    db.group_info_update(group_id, 'char', char)
    await update.callback_query.message.edit_text(f"切换角色成功！当前角色: {char.split('_')[0]}。")