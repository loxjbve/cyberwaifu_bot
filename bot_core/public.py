import logging, uuid, time
from typing import Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils import file_utils as file, db_utils as db, LLM_utils as llm, prompt_utils as prompt, text_utils as txt
import random
from datetime import timedelta
import datetime
from bot_core.exceptions import BotError, DatabaseError

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
DEFAULT_CHAR = 'cuicuishark_public'
DEFAULT_PRESET = 'Default_meeting'
DEFAULT_API = 'gemini-2'


class Conversation():
    """会话类，用于管理和处理用户与机器人的交互信息。"""

    def __init__(self, info: dict):
        """初始化会话对象。

        Args:
            info (dict): 包含会话所需信息的字典，例如用户信息、消息内容等。
        """
        self.info = info or None
        self.id = info['conv_id'] or None
        self.char = info['char'] or None
        self.preset = info['preset'] or None
        self.api = info['api'] or None
        self.type = 'private' if info['chat_type'] == 'private' else 'group'
        self.history = llm.build_openai_messages(self.id, self.type) or None
        self.prompt = prompt.build_prompts(self.char, info['message_text'], self.preset) or None
        self.response_text = None
        self.cleared_response_text = None
        self.send_msg_id = None
        self.turn = db.dialog_turn_get(self.id, self.type) or 0
        self.trigger = None
        self.received_text = info["message_text"] or None
        self.cleared_received_text = txt.extract_special_control(self.received_text)[0] or self.received_text
        logging.info(self.cleared_received_text)
        if type == 'group':
            self._build_group_prompt()

    def save_to_db(self, role: str):
        """将当前会话信息保存到数据库。
        Args:
            role (str): 当前消息的角色，'user' 或 'assistant'。
        """
        self.turn += 1
        token = llm.calculate_token_count(self.received_text if role == 'user' else self.response_text)
        if self.trigger != 'random' and self.trigger != 'keyword':
            db.dialog_content_add(self.id, role, self.turn,
                                  self.received_text if role == 'user' else self.response_text,
                                  self.cleared_response_text if role == 'assistant' else self.cleared_received_text,
                                  self.info['message_id'] if role == 'user' else self.send_msg_id, self.type)
        if self.type == 'private':
            self._save_private_dialog(token, role)
        else:
            self._save_group_dialog(token, role)

    def set_send_msg_id(self, msg_id: int):
        """设置机器人发送消息的ID。

        Args:
            msg_id (int): 消息ID。
        """
        self.send_msg_id = msg_id

    def set_trigger(self, trigger: str):
        """设置触发回复的类型。

        Args:
            trigger (str): 触发类型，例如 'reply', '@', 'keyword', 'random'。
        """
        self.trigger = trigger

    def set_response_text(self, text: str):
        """设置机器人的回复文本，并提取清理后的文本内容。

        Args:
            text (str): 机器人的原始回复文本。
        """
        self.response_text = text
        self.cleared_response_text = txt.extract_tag_content(text, 'content')
        logging.info(self.cleared_response_text)

    def check_id(self, chat_type: str):
        """检查会话ID是否存在，如果不存在则创建新的会话ID。
        Args:
            chat_type (str): 聊天类型，'private' 或 'group'。
        Raises:
            ValueError: 如果尝试多次后仍无法创建ID。
        """
        if not self.info.get('conv_id'):  # 使用 get() 避免 KeyError
            try:
                if chat_type == 'group':
                    new_conv_id = self.new('group')
                    logger.info(
                        f"新建群聊对话, group_name: {self.info['group_name']}, user_name: {self.info['user_name']}, conv_id: {new_conv_id}")
                else:  # 假设为 'private'
                    new_conv_id = self.new('private')
                    logger.info(f"{self.info['user_name']} 新建私聊对话, conv_id: {new_conv_id}")
                self.id = new_conv_id  # 设置属性
            except Exception as e:  # 捕获一般异常，便于调试
                logger.error(f"创建会话ID失败: {e}")
                raise

    def new(self, conv_type: str) -> int or str:
        """辅助方法：生成新的会话ID并创建数据库记录。
        Args:
            conv_type (str): 'group' 或 'private'。
        Returns:
            int or str: 生成的新的会话ID。
        Raises:
            ValueError: 如果多次尝试后失败。
        """
        max_attempts = 5  # 限制尝试次数，避免无限循环
        for _ in range(max_attempts):

            new_conv_id = random.randint(10000000, 99999999)  # 生成UUID的整数表示（如果需要整数）

            if conv_type == 'group':
                if db.conversation_group_check(new_conv_id):  # 假设这个函数检查ID是否可用
                    db.conversation_group_create(new_conv_id, self.info['user_id'], self.info['user_name'],
                                                 self.info['group_id'], self.info['group_name'])
                    return new_conv_id
            else:  # 'private'
                if db.conversation_private_create(new_conv_id, self.info['user_id'], self.info['char'],
                                                  self.info['preset']):
                    return new_conv_id

            # 如果检查失败，等待一小会儿再试（可选，避免快速重试）
            #time.sleep(0.1)  # 导入 time 模块

        raise ValueError(f"无法创建{conv_type}会话ID，经过{max_attempts}次尝试")

    def _save_private_dialog(self, token, role):
        db.user_info_update(self.info['user_id'], 'input_tokens' if role == 'user' else 'output_tokens', token,
                            True)
        db.user_info_update(self.info['user_id'], 'dialog_turns', 1, True)
        db.user_info_update(self.info['user_id'], 'remain_frequency', -1 if (role == 'assistant') and (
            not self.cleared_response_text.startswith('API调用失败:')) else 0, True)
        db.conversation_private_arg_update(self.id, 'turns', 1, True)

    def _save_group_dialog(self, token, role):
        print(f"trigger is {self.trigger},role is {role},saving")
        if role == 'assistant':

            db.group_dialog_update(self.info['message_id'], 'raw_response', self.response_text, self.info['group_id'])
            db.group_dialog_update(self.info['message_id'], 'processed_response', self.cleared_response_text,
                                   self.info['group_id'])
            db.group_dialog_update(self.info['message_id'], 'trigger_type', self.trigger, self.info['group_id'])
            if self.trigger == 'ramdom' or self.trigger == 'keyword':
                logger.info(
                    f"一次性群聊回复完成, group_name: {self.info['group_name']}, user_name: {self.info['user_name']}, output_token: {token}")
            else:
                #print('增加群聊对话turn')
                db.conversation_group_update(self.info['group_id'], self.info['user_id'], 'turns', 1)
                #print('增加群聊dialog')
                db.group_dialog_update(self.id, 'trigger_type', 'reply', self.info['group_id'])
                db.group_dialog_update(self.id, 'raw_response', self.response_text, self.info['group_id'])
                db.group_dialog_update(self.id, 'processed_response', self.cleared_response_text, self.info['group_id'])

    def _build_group_prompt(self):
        self.prompt = prompt.insert_text(self.prompt,
                                         f"你需要回复的用户的姓名或网名是‘{self.info['user_name']}，以下是用户的输入’\r\n",
                                         '以下是用户最新输入:\r\n', 'before')
        group_dialog = db.group_dialog_get(self.info['group_id'], 10)
        insert_txt = f"<现在是群聊模式，你需要先看看群友在聊什么，再输出内容：\r\n"
        for dialog in group_dialog:
            if dialog[1]:
                insert_txt += f"{dialog[1]}:\r\n{dialog[0]}\r\n"
        insert_txt += ">"
        self.prompt = prompt.insert_text(self.prompt, insert_txt, '以下是用户最新输入:\r\n', 'before')




def update_info_get(update: Update) -> dict:
    """从Telegram的Update对象中提取并整合有用的信息。

    Args:
        update (Update): Telegram的Update对象。

    Returns:
        dict: 包含用户、消息、群组等信息的字典。

    Raises:
        BotError: 解析Update信息时发生错误。
    """
    try:
        if update.message:
            user_info = _extract_user_info(update.message.from_user)
            msg_info = _extract_message_info(update.message)
            group_info = _extract_group_info(update.message.chat)
            info = {**user_info, **msg_info, **group_info}
            if update.message.chat.type == 'private':
                config = user_config_get(user_info['user_id']) or {}
                user_detail = user_info_get(user_info['user_id']) or {}
                return {**config, **user_detail, **info}
            else:
                config = db.group_config_get(group_info['group_id'])
                user_info = _extract_user_info(update.message.from_user)
                if config:
                    config_dict = {'api': config[0], 'char': config[1], 'preset': config[2]}
                    conv_id = {'conv_id': db.conversation_group_get(group_info['group_id'], user_info['user_id'])}
                    if db.group_check_update(group_info['group_id']):
                        return {'need_update': True, **user_info, **conv_id, **config_dict, **info}
                    else:
                        return {'need_update': False, **user_info, **conv_id, **config_dict, **info}
                else:
                    return {'need_update': True, **info}
        elif update.callback_query:
            user_info = _extract_user_info(update.callback_query.from_user)
            message = update.callback_query.message if update.callback_query.message else None
            chat = message.chat if message else None
            msg_info = _extract_message_info(message) if message else {}
            if chat and chat.type == 'private':
                info = {**user_info, **msg_info, 'user_name': f"{user_info['first_name']}{user_info['last_name']}"}
                config = user_config_get(user_info['user_id']) or {}
                user_detail = user_info_get(user_info['user_id']) or {}
                return {**config, **user_detail, **info}
            elif chat and chat.type in ['group', 'supergroup']:
                group_info = _extract_group_info(chat)
                info = {**user_info, **msg_info, **group_info}
                config = db.group_config_get(group_info['group_id'])
                if config:
                    config_dict = {'api': config[0], 'char': config[1], 'preset': config[2]}
                    conv_id = {'conv_id': db.conversation_group_get(group_info['group_id'], user_info['user_id'])}
                    return {**conv_id, **config_dict, **info}
                else:
                    return {'need_update': True, **info}
            else:
                config = user_config_get(user_info['user_id']) or {}
                user_detail = user_info_get(user_info['user_id']) or {}
                return {**user_detail, **config}
    except Exception as e:
        logger.error(f"解析update信息错误: {str(e)}")
        raise BotError(f"解析update信息错误: {str(e)}")


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


def print_conversations(user_id: int, conv_type: str = 'load') -> Union[str, InlineKeyboardMarkup]:
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


def print_char_list(operate_type: str, chat_type: str, _id: int) -> list or str:
    """
        筛选角色列表。

        Args:
            operate_type (str): 操作类型，load或delete。
            chat_type (str): 消息类型，私聊或群聊。
            _id(int): 私聊或群聊id。

        Returns:
            keyboard: 筛选后的inline按钮或str
        """
    try:
        char_list = file.list_all_characters()
        keyboard = []
        for char in char_list:
            if operate_type == 'load' and chat_type == 'private':
                if char.endswith("_public") or char.endswith(f"_{_id}"):
                    keyboard.append([InlineKeyboardButton(char.split('_')[0], callback_data=f"set_char_{char}")])
            elif operate_type == 'del' and chat_type == 'private':
                if char.endswith(f"_{_id}"):
                    keyboard.append([InlineKeyboardButton(char.split('_')[0], callback_data=f"del_char_{char}")])
            elif operate_type == 'load' and chat_type == 'group':
                if char.endswith("_public") or char.endswith(f"_{_id}"):
                    keyboard.append(
                        [InlineKeyboardButton(char.split('_')[0], callback_data=f"group_char_{char}_{_id}")])
            elif operate_type == 'del' and chat_type == 'group':
                if char.endswith(f"_{_id}"):
                    keyboard.append(
                        [InlineKeyboardButton(char.split('_')[0], callback_data=f"group_delchar_{char}_{_id}")])
        if keyboard == []:
            return "没有可操作的角色。"
        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"获取角色菜单失败, 错误: {str(e)}")
        raise DatabaseError(f"获取用户对话列表失败: {str(e)}")


async def group_info_update_or_create(update, context) -> bool:
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
                api, char, preset = DEFAULT_API, DEFAULT_CHAR, DEFAULT_PRESET
            field_list = ['group_name', 'update_time', 'members_list', 'api', 'char', 'preset', 'rate']
            value_list = [group_name, current_time, str(admin_list), api, char, preset, 0.05]
            for field, value in zip(field_list, value_list):
                db.group_info_update(group_id, field, value)
            return True
        return False
    except Exception as e:
        logger.error(f"更新或创建群组信息失败, group_id: {group_id}, 错误: {str(e)}")
        raise DatabaseError(f"更新或创建群组信息失败: {str(e)}")


def group_dialog_add(info) -> bool:
    message_id = info['message_id']
    message_text = info['message_text']
    group_name = info['group_name']
    user_id = info['user_id']
    user_name = info['user_name']

    current_time = str(datetime.datetime.now())
    try:
        if db.group_dialog_add(message_id, info['group_id']):
            field_list = ['group_id', 'group_name', 'create_at', 'msg_user', 'msg_user_name', 'msg_text']
            value_list = [info['group_id'], group_name, current_time, user_id, user_name, message_text]
            for field, value in zip(field_list, value_list):
                db.group_dialog_update(message_id, field, value, info['group_id'])
            return True
        return False
    except Exception as e:
        logger.error(f"添加群聊对话记录失败, group_id: {info['group_id']}, 错误: {str(e)}")
        raise DatabaseError(f"添加群聊对话记录失败: {str(e)}")


def group_msg_needs_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Union[str, bool]:
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
    info = update_info_get(update)
    message_text = info['message_text']
    group_id = info['group_id']
    group_name = info['group_name']
    user_name = info['user_name']
    keyword_list = db.group_keyword_get(group_id)
    rate = db.group_rate_get(group_id)
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
                    if random.random() < rate:
                        logger.info(f"触发随机回复, group_name: {group_name}, user_name: {user_name}")
                        return 'random'
        if message_text:
            if f"@{bot_username}" in message_text:
                logger.info(f"触发@Bot, group_name: {group_name}, user_name: {user_name}")
                return '@'
            if keyword_list and any(keyword in message_text for keyword in keyword_list):
                logger.info(f"触发关键词, group_name: {group_name}, user_name: {user_name}")
                return 'keyword'
            if random.random() < rate:
                logger.info(f"触发随机回复, group_name: {group_name}, user_name: {user_name}")
                return 'random'
        logger.info(f"未触发任何条件, group_name: {group_name}, user_name: {user_name}")
        return False
    except Exception as e:
        logger.error(f"检查群聊消息是否需要回复失败, group_id: {group_id}, 错误: {str(e)}")
        raise BotError(f"检查群聊消息是否需要回复失败: {str(e)}")


def group_admin_check(update: Update) -> bool:
    """
    检查用户是否为群组管理员。

    Args:
        update (Update): Telegram更新对象。

    Returns:
        bool: 如果是管理员或机器人管理员则返回 True，否则返回 False。

    Raises:
        DatabaseError: 检查管理员权限失败时抛出。
    """
    try:
        info = update_info_get(update)
        admin_list = db.group_admin_list_get(info['group_id'])
        return (info['user_id'] in admin_list) or (info['user_id'] in ADMIN)
    except Exception as e:
        logger.error(f"检查管理员权限失败, group: {info['group_name']}, 错误: {str(e)}")
        raise DatabaseError(f"检查管理员权限失败: {str(e)}")


def user_admin_check(user_id: int) -> bool:
    """检查用户是否为机器人管理员。

    Args:
        user_id (int): 用户ID。

    Returns:
        bool: 如果是机器人管理员则返回 True，否则返回 False。
    """
    return True if user_id in ADMIN else False


def user_info_get(user_id: int) -> dict:
    """获取指定用户的详细信息。

    Args:
        user_id (int): 用户ID。

    Returns:
        dict: 包含用户信息的字典，如果用户不存在则返回空字典。

    Raises:
        DatabaseError: 获取用户信息失败时抛出。
    """
    try:
        result = db.user_info_get(user_id)
        if result:
            return {'user_name': f"{result[0]}{result[1]}", 'first_name': result[0], 'last_name': result[1],
                    'tier': result[2], 'remain': result[3], 'balance': result[4]}
        else:
            return {}
    except Exception as e:
        logger.error(f"获取用户信息失败, user_id: {user_id}, 错误: {str(e)}")
        raise DatabaseError(f"获取用户信息失败: {str(e)}")


def user_info_update(user_id: int, user_name: str, first_name: str, last_name: str) -> str:
    """更新或创建用户信息。

    Args:
        user_id (int): 用户ID。
        user_name (str): 用户名。
        first_name (str): 用户名字。
        last_name (str): 用户姓氏。

    Returns:
        str: 操作结果的提示信息。

    Raises:
        DatabaseError: 更新或创建用户信息失败时抛出。
    """
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


def user_config_get(user_id: int) -> dict:
    """获取用户配置信息，如果不存在则创建默认配置。

    Args:
        user_id (int): 用户ID。

    Returns:
        dict: 包含用户配置信息的字典。

    Raises:
        DatabaseError: 获取用户配置失败时抛出。
    """
    try:
        result = db.user_config_get(user_id)
        if not result:
            db.user_config_create(user_id)
            result = db.user_config_get(user_id)
            logger.info(f"为新用户{user_id}创建默认配置")
        return {'char': result[0], 'api': result[1], 'preset': result[2], 'conv_id': result[3], 'stream': result[4],
                'user_id': user_id}
    except Exception as e:
        logger.error(f"获取用户配置失败, user_id: {user_id}, 错误: {str(e)}")
        raise DatabaseError(f"获取用户配置失败: {str(e)}")


def is_message_expired(update: Update) -> bool:
    """
    检查消息是否过期（默认超过30秒）。

    Args:
        update (Update): Telegram 更新对象。

    Returns:
        bool: 如果消息过期返回 True，否则返回 False。
    """
    if update.message is None or update.message.date is None:
        return False  # 如果没有消息或时间信息，默认不过期
    current_time = datetime.datetime.now(update.message.date.tzinfo)  # 获取当前时间，匹配时区
    time_diff = current_time - update.message.date
    logger.debug(f"检查消息是否过期，时间差: {time_diff}")
    return time_diff > timedelta(seconds=30)


def _extract_user_info(user) -> dict:
    """从Telegram User对象中提取用户信息。

    Args:
        user: Telegram User对象。

    Returns:
        dict: 包含用户ID、名字、姓氏、用户名和完整用户名的字典。
    """
    return {
        'user_id': user.id,
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'username': user.username or '',
        'user_name': (str(user.first_name or '') + str(user.last_name or '')).strip()
    }


def _extract_message_info(message) -> dict:
    """从Telegram Message对象中提取消息信息。

    Args:
        message: Telegram Message对象。

    Returns:
        dict: 包含消息ID和消息文本的字典。
    """
    return {
        'message_id': message.message_id or '',
        'message_text': message.text or ''
    }


def _extract_group_info(chat) -> dict:
    """从Telegram Chat对象中提取群组或私聊信息。

    Args:
        chat: Telegram Chat对象。

    Returns:
        dict: 包含聊天ID（群组ID或用户ID）、群组名称和聊天类型的字典。
    """
    return {
        'user_id' if chat.type == 'private' else 'group_id': chat.id or '',
        'group_name': chat.title or '',
        'chat_type': chat.type or ''
    }
