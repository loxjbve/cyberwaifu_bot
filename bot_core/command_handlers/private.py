import asyncio
import json
import logging
import os
import re
from pathlib import Path
from agent.llm_functions import generate_summary
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from telegram.ext import ContextTypes
import bot_core.services.utils.tg_parse as public
from bot_core.callback_handlers.inline import Inline
from agent.llm_functions import generate_char
from bot_core.services.conversation import PrivateConv
from bot_core.data_repository import ConversationsRepository, UserConfigRepository, UsersRepository
from utils.logging_utils import setup_logging
from bot_core.command_handlers.base import BaseCommand, CommandMeta

setup_logging()
logger = logging.getLogger(__name__)


class StartCommand(BaseCommand):
    meta = CommandMeta(
        name="start",
        command_type="private",
        trigger="start",
        menu_text="开始使用 CyberWaifu",
        show_in_menu=False,
        menu_weight=99,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        await update.message.reply_text(
            f"您好，{info.get('first_name', '')} {info.get('last_name', '')}！这是由 @Xi_cuicui 开发的`CyberWaifu`项目。\r\n使用`/char`可以切换角色\r\n"
            f"使用`/setting`可以管理您的对话与角色设置\r\n"
            f"使用`/c` 可获取加密货币行情分析\r\n"
            f"使用`/sign` 可签到\r\n"
            f"直接发送图片可以获取`fuck or not`的评价\r\n"
            f"默认预设为正常模式，NSFW内容的生成质量有限\r\n"
            f"使用`/preset`可以切换预设，如果需要NSFW内容，建议替换默认预设为其它模式\r\n"
            f"使用`/newchar [角色名]`可以创建私人角色"
        )


class HelpCommand(BaseCommand):
    meta = CommandMeta(
        name="help",
        command_type="private",
        trigger="help",
        menu_text="获取帮助",
        show_in_menu=True,
        menu_weight=0,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        help_text = (
            "🤖 **CyberWaifu Bot 使用指南**\n\n"
            "📝 **角色管理**\n"
            "/char - 查看当前角色信息和角色列表\n"
            "/newchar - 创建新的AI角色\n"
            "/delchar - 删除已有角色\n"
            "/nick - 修改当前角色的昵称\n\n"
            "⚙️ **设置与配置**\n"
            "/setting - 个人设置（流式输出、模型选择等）\n"
            "/api - 查看和切换可用的API模型\n"
            "/preset - 管理对话预设模板\n\n"
            "💬 **对话管理**\n"
            "/new - 开始新的对话会话\n"
            "/save - 保存当前对话到历史记录\n"
            "/load - 加载之前保存的对话\n"
            "/delete - 删除指定的对话记录\n"
            "/undo - 撤销上一条消息\n"
            "/regen - 重新生成AI的最后一条回复\n"
            "/stream - 切换流式输出模式\n\n"
            "📊 **信息查看**\n"
            "/me - 查看个人信息和使用统计\n"
            "/sign - 每日签到获取额度奖励\n\n"
            "🔧 **高级功能**\n"
            "/c 或 /crypto - AI加密货币分析助手\n"
            "/director - 导演模式（多角色对话）\n"
            "/done - 标记当前任务为完成状态\n\n"
            "🏠 **群聊专用指令**\n"
            "在群聊中还可以使用以下指令：\n"
            "/remake - 重置群聊上下文(担任)\n"
            "/switch - 切换群聊角色\n"
            "/rate - 设置群聊回复概率\n"
            "/kw - 管理群聊关键词触发\n"
            "/e - 启用群聊话题讨论\n"
            "/d - 禁用群聊话题讨论\n"
            "/cc - 群聊加密货币分析\n\n"
            "💡 **使用提示**\n"
            "• 直接发送消息即可与AI对话\n"
            "• 如果喜欢NSFW内容，强烈建议使用 /newchar 创建属于您的角色，并通过 /preset 修改nsfw预设以获得更好的文本质量\n"
            "• 大部分指令支持简写形式\n"
            "• 在群聊中需要@机器人或回复机器人消息\n"
            "• 管理员拥有额外的管理指令权限"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")


class UndoCommand(BaseCommand):
    meta = CommandMeta(
        name="undo",
        command_type="private",
        trigger="undo",
        menu_text="撤回上一条消息",
        show_in_menu=True,
        menu_weight=1,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        conversation = PrivateConv(update, context)
        await conversation.undo()
        if conversation.input and conversation.input.id:
            await context.bot.delete_message(conversation.user.id, conversation.input.id)


class StreamCommand(BaseCommand):
    meta = CommandMeta(
        name="stream",
        command_type="private",
        trigger="stream",
        menu_text="切换流式传输模式",
        show_in_menu=True,
        menu_weight=5,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        result = UserConfigRepository.user_stream_switch(info["user_id"])
        if result["success"]:
            await update.message.reply_text("切换成功！")


class MeCommand(BaseCommand):
    meta = CommandMeta(
        name="me",
        command_type="private",
        trigger="me",
        menu_text="查看个人信息",
        show_in_menu=True,
        menu_weight=99,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        user_name = escape_markdown(info.get('user_name', '未知'), version=1)
        # --- 修复：使用正确的键名 ---
        tier = escape_markdown(str(info.get('account_tier', '未知')), version=1)
        remain = escape_markdown(str(info.get('remain_frequency', 0)), version=1)
        frequency = escape_markdown(str(info.get('frequency', 0)), version=1)
        balance = escape_markdown(str(info.get('balance', 0)), version=1)
        
        user_nick = escape_markdown(info.get('nick', '未设置'), version=1)
        char = escape_markdown(info.get('char', '未设置'), version=1)
        api = escape_markdown(info.get('api', '未设置'), version=1)
        preset = escape_markdown(info.get('preset', '未设置'), version=1)
        stream = escape_markdown(str(info.get('stream', '未知')), version=1)

        result = (
            f"您好，{user_name}！\r\n"
            f"您的帐户等级是`{tier}`；\r\n"
            f"您的额度还有`{remain}`条；\r\n"
            f"您的临时额度还有`{frequency}`条(上限100)；\r\n"
            f"您的余额是`{balance}`；\r\n"
            f"您的对话昵称是`{user_nick}`。\r\n"
            f"当前角色：`{char}`\r\n当前接口：`{api}`\r\n当前预设：`{preset}`\r\n流式传输：`{stream}`\r\n"
        )
        await update.message.reply_text(f"{result}", parse_mode="MarkDown")


class NewCommand(BaseCommand):
    meta = CommandMeta(
        name="new",
        command_type="private",
        trigger="new",
        menu_text="创建新对话",
        show_in_menu=True,
        menu_weight=5,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return

        import random
        # 1. 生成新的会话ID
        while True:
            new_conv_id = random.randint(10000000, 99999999)
            check_result = ConversationsRepository.conversation_private_check(new_conv_id)
            if check_result["success"] and check_result["data"]:
                break

        # 2. 从info中获取角色和预设
        character = info.get('char')
        preset = info.get('preset')
        user_id = info.get('user_id')

        if not character or not preset or not user_id:
            await update.message.reply_text("无法获取用户配置，创建新对话失败。")
            return

        # 3. 创建新对话
        create_result = ConversationsRepository.conversation_private_create(new_conv_id, user_id, character, preset)
        if create_result["success"]:
            # 4. 更新用户当前会话ID
            UserConfigRepository.user_config_arg_update(user_id, "conv_id", new_conv_id)
            UsersRepository.user_conversations_count_update(user_id)  # 更新用户对话计数
            await update.message.reply_text("创建成功！", parse_mode="MarkDown")
        else:
            await update.message.reply_text("创建新对话失败，请联系管理员。")
            return
        
        # 5. 显示预设和角色选择
        preset_markup = Inline.print_preset_list()
        if isinstance(preset_markup, str):
            await update.message.reply_text(preset_markup)
        else:
            await update.message.reply_text(
                "请为新对话选择一个预设：", reply_markup=preset_markup
            )
        
        char_markup = Inline.print_char_list("load", "private", user_id)
        if isinstance(char_markup, str):
            await update.message.reply_text(char_markup)
        else:
            await update.message.reply_text(
                "请为新对话选择一个角色：", reply_markup=char_markup
            )


class SaveCommand(BaseCommand):
    meta = CommandMeta(
        name="save",
        command_type="private",
        trigger="save",
        menu_text="保存当前对话 (可选: nosummary)",
        show_in_menu=True,
        menu_weight=5,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        config = public.update_info_get(update)
        if not config:
            return
        
        # 检查是否包含nosummary参数
        message_text = update.message.text or ""
        no_summary = "nosummary" in message_text.lower()
        
        conv_id = config.get("conv_id")
        char = config.get("char")
        preset = config.get("preset")

        update_result = ConversationsRepository.conversation_private_update(conv_id, char, preset)
        save_result = ConversationsRepository.conversation_private_save(conv_id)
        if conv_id and char and preset and update_result["success"] and save_result["success"]:
            if no_summary:
                # 简单保存，不生成总结
                await update.message.reply_text("保存成功")
                logger.info(f"简单保存对话, conv_id: {conv_id}")
                return
            
            placeholder_message = await update.message.reply_text("保存中...")

            async def create_summary(current_conv_id, placeholder):
                summary = await generate_summary(current_conv_id)
                if summary:
                    summary_result = ConversationsRepository.conversation_private_summary_add(current_conv_id, summary)
                    if summary_result["success"]:
                        logger.info(
                            f"保存对话并生成总结, conv_id: {current_conv_id}, summary: {summary}"
                        )
                        escaped_summary = escape_markdown(summary, version=1)
                        try:
                            await placeholder.edit_text(
                                f"保存成功，对话总结:`{escaped_summary}`", parse_mode="MarkDown"
                            )
                        except Exception as e:
                            logger.warning(e)
                            await placeholder.edit_text(f"保存成功，对话总结:`{escaped_summary}`")
                    else:
                        await placeholder.edit_text("保存失败")
                else:
                    await placeholder.edit_text("保存失败")

            _task = asyncio.create_task(
                create_summary(conv_id, placeholder_message)
            )
            return


class RegenCommand(BaseCommand):
    meta = CommandMeta(
        name="regen",
        command_type="private",
        trigger="regen",
        menu_text="重新生成回复",
        show_in_menu=True,
        menu_weight=1,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        conversation = PrivateConv(update, context)
        await conversation.regen()
        await update.message.delete()


class CharCommand(BaseCommand):
    meta = CommandMeta(
        name="char",
        command_type="private",
        trigger="char",
        menu_text="选择角色",
        show_in_menu=True,
        menu_weight=6,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        conversation = PrivateConv(update, context)
        if not conversation.user:
            return
        markup = Inline.print_char_list("load", "private", conversation.user.id)
        if isinstance(markup, str):
            await update.message.reply_text(markup)
        else:
            await update.message.reply_text("请选择一个角色：", reply_markup=markup)
        await update.message.delete()


class DelcharCommand(BaseCommand):
    meta = CommandMeta(
        name="delchar",
        command_type="private",
        trigger="delchar",
        menu_text="删除角色",
        show_in_menu=True,
        menu_weight=7,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        markup = Inline.print_char_list("del", "private", info["user_id"])
        if isinstance(markup, str):
            await update.message.reply_text(markup)
        else:
            await update.message.reply_text("请选择一个角色：", reply_markup=markup)


class NewcharCommand(BaseCommand):
    meta = CommandMeta(
        name="newchar",
        command_type="private",
        trigger="newchar",
        menu_text="创建新的角色",
        show_in_menu=True,
        menu_weight=6,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        args = context.args if hasattr(context, "args") else []
        if not args or len(args[0].strip()) == 0:
            await update.message.reply_text(
                "请使用 /newchar char_name 的格式指定角色名。"
            )
            return
        char_name = args[0].strip()
        if not hasattr(context.bot_data, "newchar_state"):
            context.bot_data["newchar_state"] = {}
        context.bot_data["newchar_state"][info["user_id"]] = {
            "char_name": char_name,
            "desc_chunks": [],
        }
        await update.message.reply_text(
            "请直接发送文本描述，完成后发送 /done 结束输入。\n如描述较长可分多条消息发送。"
        )


class NickCommand(BaseCommand):
    meta = CommandMeta(
        name="nick",
        command_type="private",
        trigger="nick",
        menu_text="设置你的昵称",
        show_in_menu=True,
        menu_weight=44,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        args = context.args if hasattr(context, "args") else []
        if not args or len(args[0].strip()) == 0:
            await update.message.reply_text(
                "请使用 /nick nickname 的格式指定昵称。如：/nick 脆脆鲨"
            )
            return
        nick_name = args[0].strip()
        result = UserConfigRepository.user_config_arg_update(info["user_id"], "nick", nick_name)
        if result["success"]:
            await update.message.reply_text(f"昵称已更新为：{nick_name}")
        else:
            await update.message.reply_text("昵称更新失败")
        await update.message.delete()


class DoneCommand(BaseCommand):
    meta = CommandMeta(
        name="done",
        command_type="private",
        trigger="done",
        menu_text="完成角色创建",
        show_in_menu=False,  # 通常 /done 命令不直接显示在菜单中
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        user_id = info["user_id"]
        
        # 解析命令参数，检查是否包含sfw参数
        message_text = update.message.text or ""
        args = message_text.split()[1:] if len(message_text.split()) > 1 else []
        is_sfw = "sfw" in args
        
        state = context.bot_data.get("newchar_state", {}).get(user_id)
        if not state:
            await update.message.reply_text(
                "当前无待保存的角色描述。请先使用 /newchar char_name。"
            )
            return
        char_name = state["char_name"]
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
        grandparent_dir = Path(project_root).resolve().parent.parent
        save_dir = os.path.join(grandparent_dir, "characters")
        os.makedirs(save_dir, exist_ok=True)
        if "file_saved" in state:
            save_path = state["file_saved"]
            del context.bot_data["newchar_state"][user_id]
            await update.message.reply_text(f"角色 {char_name} 已保存到 {save_path}")
            return
        desc = "\n".join(state["desc_chunks"])
        try:
            mode_text = "SFW" if is_sfw else "NSFW"
            placeholder_message = await update.message.reply_text(f"正在生成{mode_text}角色...")

            async def _generate_char(
                placeholder, char_description, save_to, name_char, uid, tg_context, nsfw_mode
            ):
                generated_content = None
                try:
                    generated_content = await generate_char(char_description, nsfw=nsfw_mode)
                    if not generated_content:
                        await placeholder.edit_text(f"角色 {name_char} 生成失败，LLM未返回任何内容。")
                        return

                    json_pattern = (
                        r"```json\s*([\s\S]*?)\s*```|```([\s\S]*?)\s*```|\{[\s\S]*\}"
                    )
                    match = re.search(json_pattern, generated_content)
                    if match:
                        json_str = next(group for group in match.groups() if group)
                        char_data = json.loads(json_str)
                        mode_suffix = "_sfw" if not nsfw_mode else ""
                        save_path = os.path.join(save_to, f"{name_char}_{uid}{mode_suffix}.json")
                        with open(save_path, "w", encoding="utf-8") as f:
                            json.dump(char_data, f, ensure_ascii=False, indent=2)
                        await placeholder.edit_text(
                            f"角色 {name_char} 已保存到 {save_path}"
                        )
                    else:
                        mode_suffix = "_sfw" if not nsfw_mode else ""
                        save_path = os.path.join(save_to, f"{name_char}_{uid}{mode_suffix}.txt")
                        with open(save_path, "w", encoding="utf-8") as f:
                            f.write(generated_content)
                        await placeholder.edit_text(
                            f"警告：未能从生成内容中提取 JSON 数据，保存原始内容到 {save_path}。"
                        )
                except json.JSONDecodeError as error:
                    mode_suffix = "_sfw" if not nsfw_mode else ""
                    save_path = os.path.join(save_to, f"{name_char}_{uid}{mode_suffix}.txt")
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(generated_content or "")
                    await placeholder.edit_text(
                        f"错误：无法解析生成的 JSON 内容，保存为原始文本到 {save_path}。错误信息：{str(error)}"
                    )
                except Exception as error:
                    await placeholder.edit_text(
                        f"保存角色 {name_char} 时发生错误：{str(error)}"
                    )
                finally:
                    if uid in tg_context.bot_data.get("newchar_state", {}):
                        del tg_context.bot_data["newchar_state"][uid]

            _task = asyncio.create_task(
                _generate_char(
                    placeholder_message,
                    f"角色名称：{char_name}\r\n角色描述：{desc}",
                    save_dir,
                    char_name,
                    user_id,
                    context,
                    not is_sfw  # nsfw参数：如果是sfw模式则传False，否则传True
                )
            )
        except Exception as e:
            await update.message.reply_text(f"初始化保存过程时发生错误：{str(e)}")


class ApiCommand(BaseCommand):
    meta = CommandMeta(
        name="api",
        command_type="private",
        trigger="api",
        menu_text="选择API",
        show_in_menu=True,
        menu_weight=13,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        markup = Inline.print_api_list(info.get("tier", 0))
        if isinstance(markup, str):
            await update.message.reply_text(markup)
        else:
            await update.message.reply_text("请选择一个api：", reply_markup=markup)
        await update.message.delete()


class PresetCommand(BaseCommand):
    meta = CommandMeta(
        name="preset",
        command_type="private",
        trigger="preset",
        menu_text="选择预设",
        show_in_menu=True,
        menu_weight=6,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        markup = Inline.print_preset_list()
        if isinstance(markup, str):
            await update.message.reply_text(markup)
        else:
            await update.message.reply_text("请选择一个预设：", reply_markup=markup)
        await update.message.delete()


class LoadCommand(BaseCommand):
    meta = CommandMeta(
        name="load",
        command_type="private",
        trigger="load",
        menu_text="加载保存的对话",
        show_in_menu=False,
        menu_weight=7,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        markup = Inline.print_conversations(info["user_id"])
        if isinstance(markup, str):
            await update.message.reply_text(markup)
        else:
            await update.message.reply_text("请选择一个对话：", reply_markup=markup)
        await update.message.delete()


class DeleteCommand(BaseCommand):
    meta = CommandMeta(
        name="delete",
        command_type="private",
        trigger="delete",
        menu_text="删除保存的对话",
        show_in_menu=False,
        menu_weight=7,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        markup = Inline.print_conversations(info["user_id"], "delete")
        if isinstance(markup, str):
            await update.message.reply_text(markup)
        else:
            await update.message.reply_text("请选择一个对话：", reply_markup=markup)
        await update.message.delete()


class DialogCommand(BaseCommand):
    meta = CommandMeta(
        name="dialog",
        command_type="private",
        trigger="dialog",
        menu_text="对话管理",
        show_in_menu=True,
        menu_weight=5,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        info = public.update_info_get(update)
        if not info:
            return
        markup = Inline.print_dialog_conversations(info["user_id"])
        if isinstance(markup, str):
            await update.message.reply_text(markup)
        else:
            await update.message.reply_text("请选择一个对话：", reply_markup=markup)
        await update.message.delete()


class SettingCommand(BaseCommand):
    meta = CommandMeta(
        name="setting",
        command_type="private",
        trigger="setting",
        menu_text="设置",
        show_in_menu=False,
        menu_weight=1,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        """
        处理设置命令，显示设置菜单。
        """
        keyboard = [
            [InlineKeyboardButton("对话管理", callback_data="settings_dialogue_main")],
            [InlineKeyboardButton("角色管理", callback_data="settings_character_main")],
            [InlineKeyboardButton("预设设置", callback_data="settings_preset_main")],
            [InlineKeyboardButton("状态查询", callback_data="settings_status_main")],
            [InlineKeyboardButton("我的信息", callback_data="settings_myinfo_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "请选择要管理的选项：", reply_markup=reply_markup
        )

