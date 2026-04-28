import logging
from typing import Dict, Any, Optional

from telegram import Update, User, Message, Chat
from bot_core.services.utils.error import BotError, DatabaseError
from bot_core.data_repository.gateways import UserGateway
from utils import db_utils as db
from utils.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class UpdateParser:
    """
    一个用于解析Telegram Update对象的类，封装了信息提取和数据加载的逻辑。
    """

    def __init__(self, update: Update):
        self.update = update
        self.user: Optional[User] = None
        self.message: Optional[Message] = None
        self.chat: Optional[Chat] = None
        self.info: Dict[str, Any] = {}

        self._extract_base_objects()

    def _extract_base_objects(self):
        """从Update对象中提取核心对象（user, message, chat）。"""
        if self.update.message:
            self.message = self.update.message
            self.user = self.message.from_user
            self.chat = self.message.chat
        elif self.update.callback_query:
            callback = self.update.callback_query
            if callback.message and isinstance(callback.message, Message):
                self.message = callback.message
                self.chat = self.message.chat
            self.user = callback.from_user
        # 可以根据需要扩展以支持其他类型的更新，如 inline_query

    def parse(self) -> Optional[Dict[str, Any]]:
        """
        解析Update对象，提取所有信息并从数据库加载相关数据。
        """
        if not self.user or not self.chat:
            logger.debug("Update对象不包含足够的信息进行解析。")
            return None

        try:
            self._extract_initial_info()

            if self.chat.type == 'private':
                self._load_private_chat_data()
            elif self.chat.type in ['group', 'supergroup']:
                self._load_group_chat_data()
            
            return self.info

        except Exception as e:
            logger.error(f"解析update信息时出错: {e}", exc_info=True)
            raise BotError(f"解析update信息错误: {e}")

    def _extract_initial_info(self):
        """提取用户、消息和聊天的基本信息。"""
        self.info.update(self._extract_user_info())
        if self.message:
            self.info.update(self._extract_message_info())
        self.info.update(self._extract_chat_info())

    def _load_private_chat_data(self):
        """加载私聊相关的数据（用户配置和详情）。"""
        if not self.user:
            logger.warning("无法加载私聊数据，因为 self.user 未定义。")
            return
        user_id = self.user.id
        config = self._get_or_create_user_config(user_id)
        self.info.update(config)

        # --- 重构：使用 UserRepository 获取标准化的用户信息 ---
        user_gateway = UserGateway()
        user_model = user_gateway.get_by_id(user_id)
        if user_model:
            # 直接使用 UserModel 的属性更新 info 字典，不改变键名
            self.info.update(user_model.model_dump(by_alias=True))
            logger.debug(f"成功从 UserRepository 加载用户详情并更新到 info 字典。")
        else:
            # 作为后备，或者记录一个警告
            logger.warning(f"无法通过 UserRepository 加载用户 {user_id} 的详细信息。")
            # 仍然尝试旧方法以保证兼容性，但这不是长久之计
            legacy_user_detail = db.user_info_get(user_id) or {}
            self.info.update(legacy_user_detail)

    def _load_group_chat_data(self):
        """加载群聊相关的数据（群组配置和会话ID）。"""
        if not self.chat or not self.user:
            logger.warning("无法加载群聊数据，因为 self.chat 或 self.user 未定义。")
            return
        group_id = self.chat.id
        user_id = self.user.id
        
        config = db.group_config_get(group_id)
        if config:
            self.info['api'] = config[0]
            self.info['char'] = config[1]
            self.info['preset'] = config[2]
            self.info['conv_id'] = db.conversation_group_get(group_id, user_id)
            self.info['need_update'] = db.group_check_update(group_id)
        else:
            self.info['need_update'] = True

    def _get_or_create_user_config(self, user_id: int) -> dict:
        """获取用户配置，如果不存在则创建。"""
        try:
            # 首先尝试获取现有配置
            result = db.user_config_get(user_id)
            if not result:
                # 如果不存在，则创建新配置，并直接传入 nick
                logger.info(f"为新用户 {user_id} 创建默认配置。")
                nick = self.info.get('user_name')
                db.user_config_create(user_id, nick=nick)
                # 重新获取以确保数据一致
                result = db.user_config_get(user_id)
            return result or {}
        except Exception as e:
            logger.error(f"获取或创建用户配置失败, user_id: {user_id}, 错误: {e}")
            raise DatabaseError(f"获取用户配置失败: {e}")

    def _extract_user_info(self) -> Dict[str, Any]:
        """从User对象提取信息。"""
        if not self.user: return {}
        return {
            'user_id': self.user.id,
            'first_name': self.user.first_name or '',
            'last_name': self.user.last_name or '',
            'username': self.user.username or '',
            'user_name': (f"{self.user.first_name or ''} {self.user.last_name or ''}").strip()
        }

    def _extract_message_info(self) -> Dict[str, Any]:
        """从Message对象提取信息。"""
        if not self.message: return {}

        # 检查消息类型并设置相应的文本表示
        message_text = ""
        if self.message.text:
            message_text = self.message.text
        elif self.message.photo:
            message_text = "[img]"
        elif self.message.document:
            message_text = "[file]"
        elif self.message.sticker:
            message_text = "[sticker]"
        elif self.message.animation:
            message_text = "[gif]"
        else:
            message_text = ""  # 其他类型保持为空

        return {
            'message_id': self.message.message_id,
            'message_text': message_text
        }

    def _extract_chat_info(self) -> Dict[str, Any]:
        """从Chat对象提取信息。"""
        if not self.chat: return {}
        info = {
            'chat_id': self.chat.id,
            'chat_type': self.chat.type
        }
        if self.chat.type in ['group', 'supergroup']:
            info['group_id'] = self.chat.id
            info['group_name'] = self.chat.title or ''
        return info


def update_info_get(update: Update) -> Optional[Dict[str, Any]]:
    """
    从Telegram的Update对象中提取并整合有用的信息。
    这是对 UpdateParser 的一个向后兼容的封装。

    Args:
        update (Update): Telegram的Update对象。

    Returns:
        dict: 包含用户、消息、群组等信息的字典。

    Raises:
        BotError: 解析Update信息时发生错误。
    """
    parser = UpdateParser(update)
    return parser.parse() or {}


def parse_commands_with_and(message_text: str) -> list[tuple[str, list[str]]]:
    """
    Parse command string containing && separators and return list of commands.
    Each command is a tuple: (command_name, args_list)

    Args:
        message_text (str): The message text containing commands

    Returns:
        list[tuple[str, list[str]]]: List of commands, each element is (command, args)
    """
    if not message_text.startswith('/'):
        return []

    # Split commands by &&
    command_strings = message_text.split('&&')

    parsed_commands = []
    for cmd_str in command_strings:
        cmd_str = cmd_str.strip()
        if not cmd_str:
            continue

        # Ensure command starts with /
        if not cmd_str.startswith('/'):
            cmd_str = '/' + cmd_str

        # Parse individual command
        parts = cmd_str[1:].split()  # Remove leading /
        if not parts:
            continue

        command_full = parts[0]
        # Keep @botname in command for handler to check
        command = command_full
        args = parts[1:]

        parsed_commands.append((command, args))

    return parsed_commands
