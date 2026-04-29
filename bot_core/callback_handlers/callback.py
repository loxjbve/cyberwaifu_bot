# callback.py
import logging
import random
import os
from typing import Dict, Union

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, MaybeInaccessibleMessage
from telegram.ext import ContextTypes

import bot_core.services.messages
import bot_core.services.utils.tg_parse as public
from bot_core.callback_handlers.base import BaseCallback, CallbackMeta
from bot_core.services.utils.error import BotError
from bot_core.data_repository import (
    conversations, user_config, users, groups
)
from utils.logging_utils import setup_logging
from .inline import Inline

setup_logging()
logger = logging.getLogger(__name__)

# 设置日志配置


async def safe_edit_message(message: Union[Message, MaybeInaccessibleMessage, None], text: str, **kwargs) -> bool:
    """
    安全地编辑消息，直接处理消息对象，忽略类型检查以防止lint报错。

    Args:
        message: 消息对象，直接使用而不检查类型
        text: 要编辑的文本内容
        **kwargs: 其他传递给 edit_text 的参数

    Returns:
        bool: 编辑是否成功
    """
    if message is None:
        logger.debug("消息对象为None，跳过编辑")
        return False

    try:
        # 直接使用消息对象，忽略类型检查
        await message.edit_text(text, **kwargs)  # type: ignore
        logger.debug(f"消息编辑成功: {text[:50]}...")
        return True
    except Exception as e:
        logger.warning(f"编辑消息失败: {e}")
        return False


def ensure_user_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """
    确保context.user_data不为None，如果为None则初始化为空字典。

    Args:
        context: Telegram context对象

    Returns:
        dict: 有效的user_data字典
    """
    if context.user_data is None:
        logger.debug("context.user_data 为 None，正在初始化为空字典")
        context.user_data = {}
    return context.user_data


async def safe_reply_message(message: Union[Message, MaybeInaccessibleMessage, None], text: str, **kwargs) -> bool:
    """
    安全地回复消息，直接处理消息对象，忽略类型检查以防止lint报错。

    Args:
        message: 消息对象，直接使用而不检查类型
        text: 要回复的文本内容
        **kwargs: 其他传递给 reply_text 的参数

    Returns:
        bool: 回复是否成功
    """
    if message is None:
        logger.debug("消息对象为None，跳过回复")
        return False

    try:
        # 直接使用消息对象，忽略类型检查
        await message.reply_text(text, **kwargs)  # type: ignore
        logger.debug(f"消息回复成功: {text[:50]}...")
        return True
    except Exception as e:
        logger.warning(f"回复消息失败: {e}")
        return False



class SetCharCallback(BaseCallback):
    meta = CallbackMeta(
        name='set_char',
        callback_type='private',
        trigger='set_char_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理角色设置回调。
        """
        try:
            character = data
            info = public.update_info_get(update)
            if not info:
                return
            query = update.callback_query
            if not query or not query.message:
                return

            if user_config.user_config_arg_update(info['user_id'], 'char', character)["success"]:
                import random
                while True:
                    new_conv_id = random.randint(10000000, 99999999)
                    if conversations.conversation_private_check(new_conv_id)["data"]:
                        break

                preset = info.get('preset')
                user_id = info.get('user_id')

                if not preset or not user_id:
                    await safe_edit_message(query.message, "无法获取用户配置，创建新对话失败。")
                    return
    
                if conversations.conversation_private_create(new_conv_id, user_id, character, preset)["success"]:
                    user_config.user_config_arg_update(user_id, "conv_id", new_conv_id)
                    await safe_edit_message(query.message,
                        f"角色切换成功！会话已重开！当前角色: {character.split('_')[0]}。")
                else:
                    await safe_edit_message(query.message, "创建新对话失败，请联系管理员。")
                    return
                
                from utils import file_utils
                char_file_name_parts = character.split('_')
                actual_char_name = char_file_name_parts[0]
                possible_filenames = [
                    f"{character}.json",
                    f"{actual_char_name}.json"
                ]
                char_data = None
                for fname in possible_filenames:
                    char_data = file_utils.load_char(fname)
                    if char_data:
                        break

                if char_data and 'meeting' in char_data:
                    meeting_message = char_data['meeting']
                    await safe_reply_message(query.message, meeting_message)
                    # 重新获取info以确保conv_id是新的
                    updated_info = public.update_info_get(update)
                    if updated_info and updated_info.get('conv_id'):
                        conversations.dialog_content_add(updated_info['conv_id'], 'assistant', 1, meeting_message,
                                                         meeting_message, query.message.message_id, 'private')
                elif char_data is None:
                    logger.warning(f"未能加载角色 {character} 的数据文件。")
        except Exception as e:
            logger.error(f"设置角色失败, 错误: {str(e)}")


class DelCharCallback(BaseCallback):
    meta = CallbackMeta(
        name='del_char',
        callback_type='private',
        trigger='del_char_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理角色删除回调。
        """

        character = data
        info = public.update_info_get(update)
        if not info:
            return
        query = update.callback_query
        if not query or not query.message:
            return
        char_dir = './characters/'
        json_path = os.path.join(char_dir, f'{character}.json')
        txt_path = os.path.join(char_dir, f'{character}.txt')
        delmark = str(random.randint(100000, 999999))
        if os.path.exists(json_path):
            del_path = os.path.join(char_dir, f'{character}_{delmark}_del.json')
            os.rename(json_path, del_path)
        elif os.path.exists(txt_path):
            del_path = os.path.join(char_dir, f'{character}_{delmark}_del.txt')
            os.rename(txt_path, del_path)
        if info['char'] == data:
            user_config.user_config_arg_update(info['user_id'], 'char', 'cuicuishark_public')
            conversations.conversation_private_arg_update(info['conv_id'], 'character', 'cuicuishark_public')
            await safe_edit_message(query.message, 
                f"角色`{character.split('_')[0]}`删除成功！已为您切换默认角色`cuicuishark` 。")
        else:
            await safe_edit_message(query.message, 
                f"角色`{character.split('_')[0]}`删除成功！")





class SetApiCallback(BaseCallback):
    meta = CallbackMeta(
        name='set_api',
        callback_type='private',
        trigger='set_api_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理API设置回调。
        """
        try:
            query = update.callback_query
            if not query or not query.message:
                return
            info = public.update_info_get(update)
            if not info or not info.get('user_id'):
                await safe_edit_message(query.message, "无法获取用户信息。")
                return

            if user_config.user_config_arg_update(info['user_id'], 'api', data)["success"]:
                await safe_edit_message(query.message, f"api切换成功！当前api: {data}。")
            else:
                await safe_edit_message(query.message, "API切换失败。")
        except Exception as e:
            logger.error(f"设置api失败, 错误: {str(e)}")
            if update.callback_query and update.callback_query.message:
                await safe_edit_message(update.callback_query.message, "设置API时发生错误。")


class SetGroupApiCallback(BaseCallback):
    meta = CallbackMeta(
        name='set_group_api',
        callback_type='group',
        trigger='set_group_api_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理群组API设置回调。
        """
        try:
            query = update.callback_query
            if not query or not query.message:
                return

            # 解析回调数据：set_group_api_{api_name}_{group_id}
            parts = data.split('_')
            if len(parts) < 2:
                await safe_edit_message(query.message, "回调数据格式错误。")
                return
            
            api_name = parts[0]
            group_id = parts[1] if len(parts) > 1 else None
            
            if not group_id:
                await safe_edit_message(query.message, "群组ID缺失。")
                return
            
            # 更新群组配置
            if groups.group_config_arg_update(int(group_id), 'api', api_name)["success"]:
                await safe_edit_message(query.message, f"群组API切换成功！当前API: {api_name}。")
            else:
                await safe_edit_message(query.message, "API切换失败，请稍后重试。")
        except Exception as e:
            logger.error(f"设置群组API失败, 错误: {str(e)}")
            if update.callback_query and update.callback_query.message:
                await safe_edit_message(update.callback_query.message, "设置失败，请稍后重试。")


class SetPresetCallback(BaseCallback):
    meta = CallbackMeta(
        name='set_preset',
        callback_type='private',
        trigger='set_preset_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理预设设置回调。
        """
        try:
            query = update.callback_query
            if not query or not query.message:
                return
            info = public.update_info_get(update)
            if not info or not info.get('user_id'):
                await safe_edit_message(query.message, "无法获取用户信息。")
                return
            
            conv_id = info.get('conv_id')
            if not conv_id:
                await safe_edit_message(query.message, "无法找到当前会话。")
                return

            if (user_config.user_config_arg_update(info['user_id'], 'preset', data)["success"] and
                conversations.conversation_private_arg_update(conv_id, 'preset', data)["success"]):
                await safe_edit_message(query.message, f"预设切换成功！当前预设: {data}。")
            else:
                await safe_edit_message(query.message, "预设切换失败。")
        except Exception as e:
            logger.error(f"设置预设失败, 错误: {str(e)}")
            if update.callback_query and update.callback_query.message:
                await safe_edit_message(update.callback_query.message, "设置预设时发生错误。")


class SetConversationCallback(BaseCallback):
    meta = CallbackMeta(
        name='set_conversation',
        callback_type='private',
        trigger='set_conv_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理对话加载回调。
        """
        try:
            query = update.callback_query
            if not query or not query.message:
                return
            info = public.update_info_get(update)
            if not info or not info.get('user_id'):
                await safe_edit_message(query.message, "无法获取用户信息。")
                return
            
            user_id = info['user_id']
            conv_id = int(data)

            if user_config.user_config_arg_update(user_id, 'conv_id', conv_id)["success"]:
                conv_result = conversations.conversation_private_get(conv_id)
                if conv_result["success"] and conv_result["data"]:
                    char, preset = conv_result["data"]
                    if (user_config.user_config_arg_update(user_id, 'preset', preset)["success"] and
                        user_config.user_config_arg_update(user_id, 'char', char)["success"]):
                        await safe_edit_message(query.message, f"加载对话成功！当前对话ID: {conv_id}。")
                    else:
                        await safe_edit_message(query.message, "更新用户配置失败。")
                else:
                    await safe_edit_message(query.message, "找不到对应的对话记录。")
            else:
                await safe_edit_message(query.message, "设置当前对话失败。")
        except Exception as e:
            logger.error(f"设置对话失败, 错误: {str(e)}")
            if update.callback_query and update.callback_query.message:
                await safe_edit_message(update.callback_query.message, "加载对话时发生错误。")


class DelConversationCallback(BaseCallback):
    meta = CallbackMeta(
        name='del_conversation',
        callback_type='private',
        trigger='del_conv_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理对话删除回调。
        """
        query = update.callback_query
        if not query or not query.message:
            return

        try:
            conv_id = int(data)
            if conversations.conversation_private_delete(conv_id)["success"]:
                await safe_edit_message(query.message, f"删除对话成功！已删除对话: {conv_id}。")
            else:
                await safe_edit_message(query.message, "删除对话失败，可能对话不存在。")
        except (ValueError, TypeError) as e:
            logger.error(f"删除对话失败，无效数据: {data}, 错误: {str(e)}")
            await safe_edit_message(query.message, "删除对话失败，数据格式错误。")
        except Exception as e:
            logger.error(f"删除对话时发生未知错误, 错误: {str(e)}")
            await safe_edit_message(query.message, "删除对话时发生未知错误。")


class DialogShowCallback(BaseCallback):
    meta = CallbackMeta(
        name='dialog_show',
        callback_type='private',
        trigger='dialog_show_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理对话详情显示回调，显示summary并提供加载和删除按钮。
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None
        assert query.from_user is not None

        try:
            conv_id = int(data)
            conv_result = conversations.conversation_private_get(conv_id)
            if not conv_result["success"] or not conv_result["data"]:
                await safe_edit_message(query.message, "对话不存在或已被删除。")
                return

            conv_list_result = users.user_conversations_get_for_dialog(query.from_user.id)
            conv_list = conv_list_result["data"] if conv_list_result["success"] else []
            summary = "暂无摘要"
            for conv in conv_list or []:
                if conv[0] == conv_id:
                    summary = conv[4] if conv[4] else "暂无摘要"
                    break
            
            keyboard = [
                [InlineKeyboardButton("加载对话", callback_data=f"dialog_load_{conv_id}")],
                [InlineKeyboardButton("删除对话", callback_data=f"dialog_delete_{conv_id}")],
                [InlineKeyboardButton("返回列表", callback_data="dialog_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await safe_edit_message(query.message, 
                f"对话摘要：\n{summary}",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"显示对话详情失败, 错误: {str(e)}")
            await safe_edit_message(query.message, "获取对话详情失败，请稍后重试。")


class DialogLoadCallback(BaseCallback):
    meta = CallbackMeta(
        name='dialog_load',
        callback_type='private',
        trigger='dialog_load_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理对话加载回调。
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None
        
        try:
            conv_id = int(data)
            info = public.update_info_get(update)
            assert info is not None

            conv_result = conversations.conversation_private_get(conv_id)
            if not conv_result["success"] or not conv_result["data"]:
                await safe_edit_message(query.message, "对话不存在或已被删除。")
                return

            character, preset = conv_result["data"]
            user_id = info['user_id']

            user_config.user_config_arg_update(user_id, 'conv_id', conv_id)
            user_config.user_config_arg_update(user_id, 'char', character)
            user_config.user_config_arg_update(user_id, 'preset', preset)
            
            await safe_edit_message(query.message, 
                f"对话加载成功！\n角色: {character.split('_')[0]}\n预设: {preset}"
            )
        except Exception as e:
            logger.error(f"加载对话失败, 错误: {str(e)}")
            await safe_edit_message(query.message, "加载对话失败，请稍后重试。")


class DialogDeleteCallback(BaseCallback):
    meta = CallbackMeta(
        name='dialog_delete',
        callback_type='private',
        trigger='dialog_delete_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理对话删除回调。
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None

        try:
            conv_id = int(data)
            if conversations.conversation_private_delete(conv_id)["success"]:
                await safe_edit_message(query.message, "对话删除成功！")
            else:
                await safe_edit_message(query.message, "对话删除失败，请稍后重试。")
        except Exception as e:
            logger.error(f"删除对话失败, 错误: {str(e)}")
            await safe_edit_message(query.message, "删除对话失败，请稍后重试。")


class DialogBackCallback(BaseCallback):
    meta = CallbackMeta(
        name='dialog_back',
        callback_type='private',
        trigger='dialog_back',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str = "") -> None:
        """
        处理返回对话列表回调。
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None

        try:
            from .inline import Inline
            info = public.update_info_get(update)
            assert info is not None
            markup = Inline.print_dialog_conversations(info['user_id'])
            
            if markup == "没有可用的对话。":
                await safe_edit_message(query.message, str(markup))
            else:
                await safe_edit_message(query.message,
                    "请选择一个对话：",
                    reply_markup=markup  # type: ignore
                )
        except Exception as e:
            logger.error(f"返回对话列表失败, 错误: {str(e)}")
            await safe_edit_message(query.message, "返回列表失败，请稍后重试。")


class GroupCharCallback(BaseCallback):
    meta = CallbackMeta(
        name='group_char',
        callback_type='group',
        trigger='group_char_',
        enabled=True,
        group_admin_required=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理群组角色设置回调。
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None

        try:
            parts = data.split('_')
            char = f"{parts[0]}_{parts[1]}"
            group_id = int(parts[2])
            groups.group_info_update(group_id, 'char', char)
            await safe_edit_message(query.message, f"切换角色成功！当前角色: {char.split('_')[0]}。")
        except Exception as e:
            logger.error(f"设置群组角色失败, 错误: {str(e)}")
            await safe_edit_message(query.message, "设置群组角色失败。")


class GroupKeywordCancelCallback(BaseCallback):
    meta = CallbackMeta(
        name='group_keyword_cancel',
        callback_type='group',
        trigger='group_kw_cancel_',
        enabled=True,
        group_admin_required=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str = "") -> None:
        """
        处理关键词取消回调
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None
        
        await query.answer()
        user_data = ensure_user_data(context)
        original_message_id = user_data.get('original_message_id')
        if original_message_id:
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=query.message.chat.id,
                    message_id=original_message_id,
                    reply_markup=None
                )
            except Exception as e:
                logger.warning(f"清除按钮失败: {e}")
        user_data.clear()
        await safe_edit_message(query.message, "操作已取消，关键词列表未修改。")


class GroupKeywordAddCallback(BaseCallback):
    meta = CallbackMeta(
        name='group_keyword_add',
        callback_type='group',
        trigger='group_kw_add_',
        enabled=True,
        group_admin_required=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理关键词添加回调
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None

        await query.answer()
        group_id = int(data)
        keyboard = [[InlineKeyboardButton("取消", callback_data=f"group_kw_cancel_{group_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        user_data = ensure_user_data(context)
        user_data['original_message_id'] = query.message.message_id
        await safe_edit_message(query.message, "请回复此消息，输入要添加的关键词（用空格分隔）。", reply_markup=reply_markup)
        user_data['keyword_action'] = 'add'
        user_data['group_id'] = group_id


class GroupKeywordDeleteCallback(BaseCallback):
    meta = CallbackMeta(
        name='group_keyword_delete',
        callback_type='group',
        trigger='group_kw_del_',
        enabled=True,
        group_admin_required=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理关键词删除回调
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None

        await query.answer()
        group_id = int(data)
        keywords_result = groups.group_keyword_get(group_id)
        keywords = keywords_result["data"] if keywords_result["success"] else []
        if not keywords:
            await safe_edit_message(query.message, "当前群组没有关键词可删除。")
            return
        # 确保context.user_data不为None
        if context.user_data is None:
            context.user_data = {}
        context.user_data['keyword_action'] = 'delete'
        context.user_data['group_id'] = group_id
        context.user_data['to_delete'] = []
        keyboard = []
        row = []
        for kw in keywords:
            row.append(InlineKeyboardButton(kw, callback_data=f"group_kw_select_{kw}_{group_id}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([
            InlineKeyboardButton("提交", callback_data=f"group_kw_submit_del_{group_id}"),
            InlineKeyboardButton("取消", callback_data=f"group_kw_cancel_{group_id}")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query.message, "请选择要删除的关键词：", reply_markup=reply_markup)


class GroupKeywordSelectCallback(BaseCallback):
    meta = CallbackMeta(
        name='group_keyword_select',
        callback_type='group',
        trigger='group_kw_select_',
        enabled=True,
        group_admin_required=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理关键词选择回调
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None

        await query.answer()
        parts = data.rsplit('_', 1)
        keyword = parts[0]
        group_id = int(parts[1])
        user_data = ensure_user_data(context)
        if 'to_delete' not in user_data:
            user_data['to_delete'] = []
        if keyword not in user_data['to_delete']:
            user_data['to_delete'].append(keyword)
        keywords_result = groups.group_keyword_get(group_id)
        keywords = keywords_result["data"] if keywords_result["success"] else []
        remaining_keywords = [kw for kw in keywords if kw not in user_data['to_delete']]
        if not remaining_keywords:
            await safe_edit_message(query.message, "已选择所有关键词进行删除。")
            keyboard = [
                [InlineKeyboardButton("提交", callback_data=f"group_kw_submit_del_{group_id}"),
                 InlineKeyboardButton("取消", callback_data=f"group_kw_cancel_{group_id}")]
            ]
        else:
            keyboard = []
            row = []
            for kw in remaining_keywords:
                row.append(InlineKeyboardButton(kw, callback_data=f"group_kw_select_{kw}_{group_id}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            keyboard.append([
                InlineKeyboardButton("提交", callback_data=f"group_kw_submit_del_{group_id}"),
                InlineKeyboardButton("取消", callback_data=f"group_kw_cancel_{group_id}")
            ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        selected_text = ", ".join([f"`{kw}`" for kw in user_data['to_delete']]) if user_data.get('to_delete') else "无"
        await safe_edit_message(query.message, f"已选择删除的关键词：{selected_text}\r\n请选择更多要删除的关键词：",
                                      reply_markup=reply_markup, parse_mode='Markdown')


class GroupKeywordSubmitDeleteCallback(BaseCallback):
    meta = CallbackMeta(
        name='group_keyword_submit_delete',
        callback_type='group',
        trigger='group_kw_submit_del_',
        enabled=True,
        group_admin_required=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理关键词提交删除回调
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None

        await query.answer()
        group_id = int(data)
        user_data = ensure_user_data(context)
        to_delete_list = user_data.get('to_delete', [])
        if to_delete_list and user_data.get('keyword_action') == 'delete':
            keywords_result = groups.group_keyword_get(group_id)
            keywords = keywords_result["data"] if keywords_result["success"] else []
            new_keywords = [kw for kw in keywords if kw not in to_delete_list]
            groups.group_keyword_set(group_id, new_keywords)
            await safe_edit_message(query.message, f"已成功删除关键词：{', '.join(to_delete_list)}")
        else:
            await safe_edit_message(query.message, "删除操作未完成或已取消。")
        user_data.clear()


class CharPageCallback(BaseCallback):
    meta = CallbackMeta(
        name='char_page',
        callback_type='both',
        trigger='char_page_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
        """
        处理角色列表分页回调。
        data格式: operate_type_chat_type_id_page
        """
        try:
            query = update.callback_query
            if not query or not query.message:
                return

            # 解析回调数据
            parts = data.split('_')
            if len(parts) < 4:
                await safe_edit_message(query.message, "分页数据格式错误。")
                return

            operate_type = parts[0]  # load 或 del
            chat_type = parts[1]     # private 或 group
            _id = int(parts[2])      # 用户或群组ID
            page = int(parts[3])     # 页码

            # 生成新的角色列表
            markup = Inline.print_char_list(operate_type, chat_type, _id, page)
            
            if isinstance(markup, str):
                await safe_edit_message(query.message, markup)
            else:
                await safe_edit_message(query.message, "请选择一个角色：", reply_markup=markup)

        except (ValueError, IndexError) as e:
            logger.error(f"解析分页回调数据失败: {str(e)}")
            await safe_edit_message(query.message, "分页操作失败，请重试。")
        except Exception as e:
            logger.error(f"处理角色分页回调失败: {str(e)}")
            await safe_edit_message(query.message, "操作失败，请重试。")


class SettingsCallback(BaseCallback):
    meta = CallbackMeta(
        name='settings',
        callback_type='private',
        trigger='settings_',
        enabled=True
    )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str = "") -> None:
        """
        处理设置菜单回调。
        """
        query = update.callback_query
        assert query is not None
        assert query.message is not None

        await query.answer()
        
        # 确保data不为None
        data = data or 'main'

        info = public.update_info_get(update)
        # 某些操作不需要info，所以只在使用前检查
        
        try:
            if data == 'main':
                keyboard = [
                    [InlineKeyboardButton("对话管理", callback_data="settings_dialogue_main")],
                    [InlineKeyboardButton("角色管理", callback_data="settings_character_main")],
                    [InlineKeyboardButton("预设设置", callback_data="settings_preset_main")],
                    [InlineKeyboardButton("状态查询", callback_data="settings_status_main")],
                    [InlineKeyboardButton("我的信息", callback_data="settings_myinfo_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("请选择要管理的选项：", reply_markup=reply_markup)
            
            elif data == 'dialogue_main':
                keyboard = [
                    [InlineKeyboardButton("创建新对话", callback_data="settings_dialogue_new")],
                    [InlineKeyboardButton("加载对话", callback_data="settings_dialogue_load")],
                    [InlineKeyboardButton("删除对话", callback_data="settings_dialogue_delete")],
                    [InlineKeyboardButton("返回主菜单", callback_data="settings_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("请选择对话管理操作：", reply_markup=reply_markup)

            elif data == 'character_main':
                keyboard = [
                    [InlineKeyboardButton("选择角色", callback_data="settings_character_select")],
                    [InlineKeyboardButton("创建角色", callback_data="settings_character_new")],
                    [InlineKeyboardButton("删除角色", callback_data="settings_character_delete")],
                    [InlineKeyboardButton("返回主菜单", callback_data="settings_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("请选择角色管理操作：", reply_markup=reply_markup)

            elif data == 'preset_main':
                keyboard = [
                    [InlineKeyboardButton("选择预设", callback_data="settings_preset_select")],
                    [InlineKeyboardButton("返回主菜单", callback_data="settings_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("请选择预设设置操作：", reply_markup=reply_markup)

            elif data in ['status_main', 'myinfo_main', 'dialogue_new', 'dialogue_load', 'dialogue_delete', 'character_select', 'character_new', 'character_delete']:
                assert info is not None, "此操作需要用户信息。"
                user_id = info['user_id']

                if data == 'status_main':
                    result = f"当前角色：`{info.get('char', 'N/A')}`\r\n当前接口：`{info.get('api', 'N/A')}`\r\n当前预设：`{info.get('preset', 'N/A')}`\r\n流式传输：`{info.get('stream', 'N/A')}`\r\n"
                    keyboard = [[InlineKeyboardButton("返回主菜单", callback_data="settings_main")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(f"当前状态：\n{result}", reply_markup=reply_markup, parse_mode='Markdown')
                
                elif data == 'myinfo_main':
                    result = (
                        f"您好，{info.get('first_name', '')} {info.get('last_name', '')}！\r\n"
                        f"您的帐户等级是：`{info.get('tier', 'N/A')}`；\r\n"
                        f"您剩余额度还有`{info.get('remain', 'N/A')}`条；\r\n"
                        f"您的余额是`{info.get('balance', 'N/A')}`。\r\n"
                        f"您的聊天昵称是`{info.get('user_nick', 'N/A')}`。"
                    )
                    keyboard = [[InlineKeyboardButton("返回主菜单", callback_data="settings_main")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(f"您的信息：\n{result}", reply_markup=reply_markup, parse_mode='Markdown')

                elif data == 'dialogue_new':
                    import random
                    while True:
                        new_conv_id = random.randint(10000000, 99999999)
                        if conversations.conversation_private_check(new_conv_id)["data"]:
                            break
                    
                    character = info.get('char')
                    preset = info.get('preset')

                    if not character or not preset:
                        await query.edit_message_text("无法获取角色或预设，创建新对话失败。")
                        return

                    if conversations.conversation_private_create(new_conv_id, user_id, character, preset)["success"]:
                        user_config.user_config_arg_update(user_id, "conv_id", new_conv_id)
                        await query.edit_message_text("创建成功！")
                    else:
                        await query.edit_message_text("创建新对话失败，请联系管理员。")
                
                elif data == 'dialogue_load':
                    markup = Inline.print_conversations(user_id)
                    await query.edit_message_text("请选择一个对话：", reply_markup=markup) if not isinstance(markup, str) else await query.edit_message_text(markup)

                elif data == 'dialogue_delete':
                    markup = Inline.print_conversations(user_id, 'delete')
                    await query.edit_message_text("请选择一个要删除的对话：", reply_markup=markup) if not isinstance(markup, str) else await query.edit_message_text(markup)

                elif data == 'character_select':
                    markup = Inline.print_char_list('load', 'private', user_id)
                    await query.edit_message_text("请选择一个角色：", reply_markup=markup) if not isinstance(markup, str) else await query.edit_message_text(markup)

                elif data == 'character_new':
                    await bot_core.services.messages.send_message(context, user_id, "请使用 /newchar char_name 的格式创建角色")

                elif data == 'character_delete':
                    markup = Inline.print_char_list('del', 'private', user_id)
                    await query.edit_message_text("请选择一个要删除的角色：", reply_markup=markup) if not isinstance(markup, str) else await query.edit_message_text(markup)

            elif data == 'preset_select':
                markup = Inline.print_preset_list()
                await query.edit_message_text("请选择一个预设：", reply_markup=markup) if not isinstance(markup, str) else await query.edit_message_text(markup)

            else:
                logger.warning(f"未知的设置回调数据: {data}")
                await query.edit_message_text("未知的设置操作。")
        except Exception as e:
            logger.error(f"处理设置回调失败, data: {data}, 错误: {str(e)}")
            await safe_edit_message(query.message, "处理设置时发生错误。")

class CallbackHandler:
    """
    回调处理类，负责根据回调数据分发给相应的处理器。
    """

    def __init__(self, callback_mapping: Dict[str, BaseCallback]):
        """
        初始化回调处理器。

        Args:
            callback_mapping (Dict[str, BaseCallback]): 回调前缀到处理函数的映射。
        """
        self.callback_mapping = callback_mapping

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理回调查询"""
        query = update.callback_query
        if not query:
            return

        await query.answer()
        data = query.data
        user_id = query.from_user.id if query.from_user else 0

        try:
            for prefix, callback in self.callback_mapping.items():
                if data and data.startswith(prefix):
                    logger.debug(f"匹配到回调处理器: {prefix}, data: {data}")  # 添加日志
                    await callback.handle_callback(update, context, data[len(prefix):])
                    return

            logger.warning(f"未知的回调数据: {data}, user_id: {user_id}")
            if query.message:
                await safe_reply_message(query.message, "未知的回调操作。")

        except Exception as e:
            logger.error(f"处理回调查询失败, user_id: {user_id}, data: {data}, 错误: {str(e)}")
            raise BotError(f"处理回调{data} 失败: {str(e)}")


def create_callback_handler(module_names: list[str] | None = None):
    from bot_core.plugin_system import (
        create_callback_handler as create_plugin_callback_handler,
        get_default_plugin_manager,
    )

    return create_plugin_callback_handler(get_default_plugin_manager())
