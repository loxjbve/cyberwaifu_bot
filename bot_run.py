from telegram import Update, BotCommand, BotCommandScopeDefault
from utils import file_utils
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import logging
from asyncio import Semaphore
from bot_core import tg, user, msg, public, group, callback, keyword as kw
from bot_core import conversation as conv
from bot_core.decorators import handle_command_errors, check_message_and_user # Import decorators
from bot_core.exceptions import BotRunError # Import from new exceptions file

# 设置日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

semaphore = Semaphore(5)
BOT_TOKEN, _ = file_utils.load_config()




@handle_command_errors
@check_message_and_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /start 命令，发送欢迎消息。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    await update.message.reply_text("你好！我是由 @Xi_cuicui 开发的CyberWaifu项目。")


@handle_command_errors
@check_message_and_user
async def stream(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /stream  命令，切换流式传输。
    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    user_info = tg.user_info_get(update) # Still need user_id
    if user.stream_switch(user_info['user_id']):
        await update.message.reply_text("切换成功！")


@handle_command_errors
@check_message_and_user
async def me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /me 命令，显示用户信息。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    user_info = tg.user_info_get(update) # Still need user_id
    info = user.info_get(user_info['user_id'])
    result = (
    f"您好，{info['first_name']} {info['last_name']}！\r\n"
    f"您的帐户等级是：`{info['tier']}`；\r\n"
    f"您今日的剩余额度还有`{info['remain']}`条；\r\n"
    f"您的余额是`{info['balance']}`。"
)
    await update.message.reply_text(f"{result}", parse_mode='MarkDown')


@handle_command_errors
@check_message_and_user
async def new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /new 命令，创建新对话。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    user_info = tg.user_info_get(update) # Still need user_id
    config = user.config_get(user_info['user_id'])
    result = conv.private_new(user_info['user_id'], config)
    await update.message.reply_text(f"{result}", parse_mode='MarkDown')


@handle_command_errors
@check_message_and_user
async def save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /save 命令，保存当前对话。

    Args:
        update (Update): Telegram 更新对象。
    """
    # Decorator handles checks and basic logging
    user_info = tg.user_info_get(update) # Still need user_id
    config = user.config_get(user_info['user_id'])
    result = await conv.private_save(config['conv_id'])
    await update.message.reply_text(f"{result}")


@handle_command_errors
@check_message_and_user
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /status 命令，显示当前配置状态。

    Args:
        update (Update): Telegram 更新对象。
    """
    # Decorator handles checks and basic logging
    user_info = tg.user_info_get(update) # Still need user_id
    config = user.config_get(user_info['user_id'])
    result = f"当前角色：`{config['char']}`\r\n当前接口：`{config['api']}`\r\n当前预设：`{config['preset']}`\r\n流式传输：`{config['stream']}`\r\n"
    await update.message.reply_text(result, parse_mode='MarkDown')


@handle_command_errors
@check_message_and_user
async def char(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /char 命令，选择角色。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    markup = public.print_char_list(update)
    if markup == "没有可用的角色。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个角色：", reply_markup=markup)


@handle_command_errors
@check_message_and_user
async def api(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /api 命令，选择API。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    user_info = tg.user_info_get(update) # Still need user_id
    bot_user_info = user.info_get(user_info['user_id'])
    markup = public.print_api_list(bot_user_info['tier'])
    if markup == "没有可用的api。" or markup == "没有符合您账户等级的可用api。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个api：", reply_markup=markup)


@handle_command_errors
@check_message_and_user
async def preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /preset 命令，选择预设。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    markup = public.print_preset_list()
    if markup == "没有可用的预设。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个预设：", reply_markup=markup)


@handle_command_errors
@check_message_and_user
async def load(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /load 命令，加载保存的对话。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    user_info = tg.user_info_get(update) # Still need user_id
    markup = public.print_conversations(user_info['user_id'])
    if markup == "没有可用的对话。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个对话：", reply_markup=markup)


@handle_command_errors
@check_message_and_user
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /delete 命令，删除保存的对话。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    user_info = tg.user_info_get(update) # Still need user_id
    markup = public.print_conversations(user_info['user_id'], 'delete')
    if markup == "没有可用的对话。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个对话：", reply_markup=markup)


@handle_command_errors # Only apply error handling for now
async def remake(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /remake 命令，重开对话。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # check_message_and_user might not be suitable due to group context
    # Keep specific checks inside if needed
    if tg.is_message_expired(update):
        logger.warning(f"忽略过期的 /remake 命令，消息ID: {update.message.message_id}")
        return
    info = await tg.group_msg_parse(update)
    if await conv.group_delete(info):
        logger.info(f"处理 /remake 命令，用户ID: {update.effective_user.id}")
        await update.message.reply_text("您已重开对话！")


@handle_command_errors
@check_message_and_user # Apply user check, admin check remains inside
async def switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /switch 命令，切换群组内角色。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles basic checks and user update
    if not await group.admin_check(update, context):
        logger.warning(f"非管理员尝试使用 /switch 命令，用户ID: {update.effective_user.id}")
        return
    markup = public.print_char_list(update, 'group')
    if markup == "没有可用的角色。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个角色：", reply_markup=markup)


async def msg_group_handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理群聊文本消息。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Keep existing logic, decorators are for commands
    try:
        if tg.is_message_expired(update):
            logger.warning(f"忽略过期的群聊消息，消息ID: {update.message.message_id}")
            return
        if 'keyword_action' in context.user_data and context.user_data['keyword_action'] == 'add':
            logger.info(f"用户正在添加关键词，忽略普通回复逻辑，用户ID: {update.effective_user.id}")
            await kw.handle_keyword_add_reply(update, context)
            return
        info = await tg.group_msg_parse(update)
        await user.group_info_update_or_create(update, context)
        await group.dialog_add(info)
        needs_reply = await group.msg_needs_reply(update, context)
        logger.info(f"群聊消息检查回复需求，结果: {needs_reply}，用户ID: {update.effective_user.id}")
        if needs_reply == 'random' or needs_reply == 'keyword':
            # 发送占位消息，后台异步处理实际回复
            # 注意：generate_message_once 已经在内部发送占位消息并处理回复，不需要在这里重复处理
            await msg.reply_group_msg_once(update, context, needs_reply)
            return
        if needs_reply == 'reply' or needs_reply == '@':
            # 注意：MessageHandler.handle_group_message 已经在内部发送占位消息并处理回复，不需要在这里重复处理
            await msg.handle_group_message(update)
            return
    except Exception as e:
        logger.error(f"处理群聊消息时出错: {str(e)}", exc_info=True)
        # 不再向用户重复发送错误消息，避免多次回复


async def msg_private_handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理私聊文本消息。
    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Keep existing logic, decorators are for commands
    try:
        if tg.is_message_expired(update):
            logger.warning(f"忽略过期的私聊消息，消息ID: {update.message.message_id}")
            return
        user_info = tg.user_info_get(update)
        if user.info_update_or_create(user_info['user_id'], user_info['username'], user_info['first_name'],
                                      user_info['last_name']):
            logger.info(f"处理私聊消息，用户ID: {user_info['user_id']}")
            result = await msg.handle_private_message(update)
            if result is not None:
                try:
                    await update.message.reply_text(result, parse_mode="markdown")
                except telegram.error.BadRequest as e:
                    logger.warning(f"Markdown 解析错误: {str(e)}, 禁用 Markdown 重试")
                    await update.message.reply_text(result, parse_mode=None)

    except Exception as e:
        logger.error(f"处理私聊消息时出错: {str(e)}", exc_info=True)
        # Consider if BotRunError should be raised here too for consistency
        # raise BotRunError(f"处理私聊消息失败: {str(e)}")
        # For now, just log, as the global handler might catch it
        # Optionally send a generic error message
        # await update.message.reply_text("处理消息时发生错误，请稍后重试。")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    全局错误处理器，捕获并处理所有未捕获的异常。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Keep existing logic
    try:
        raise context.error  # 重新抛出错误以获取详细信息
    except telegram.error.BadRequest as e:
        logger.error(f"BadRequest 错误: {str(e)}", exc_info=True)
        if update and update.message:
            await update.message.reply_text("发送消息时发生错误，请稍后重试。", parse_mode=None)
    except BotRunError as e: # This should now correctly catch the imported BotRunError
        logger.error(f"BotRunError 错误: {str(e)}", exc_info=True)
        if update and update.message:
            # Avoid sending duplicate error messages if the decorator already sent one
            # Consider adding a flag in context or modifying decorator behavior
            await update.message.reply_text("发生Bot运行错误，请稍后重试。", parse_mode=None)
    except Exception as e:
        logger.error(f"未处理的错误: {str(e)}", exc_info=True)
        if update and update.message:
            await update.message.reply_text("发生未知错误，请稍后重试。", parse_mode=None)


def main() -> None:
    """
    主函数，初始化并启动Telegram Bot。
    """
    try:
        # 创建 Application 实例
        app = Application.builder().token(BOT_TOKEN).build()

        async def set_commands(app_instance: Application) -> None:
            """
            设置Bot的命令菜单。

            Args:
                app_instance (Application): Telegram Application 实例。
            """
            try:
                # 私聊中的命令菜单
                private_commands = [
                    BotCommand("start", "打招呼"),
                    BotCommand("me", "查看个人信息"),
                    BotCommand("status", "查看当前配置状态"),
                    BotCommand("char", "选择角色"),
                    BotCommand("api", "选择API"),
                    BotCommand("load", "加载保存的对话"),
                    BotCommand("preset", "选择预设"),
                    BotCommand("new", "新建对话"),
                    BotCommand("save", "保存当前对话"),
                    BotCommand("delete", "删除保存的对话"),
                    BotCommand("stream", "切换流式传输"),
                ]
                await app.bot.set_my_commands(private_commands, scope=BotCommandScopeDefault())
                logger.info("私聊命令菜单已设置完成")

                group_commands = [
                    BotCommand("cremake", "重开对话"),
                    BotCommand("kw", "设置bot触发关键词"),
                    BotCommand("switch", "切换群组内的角色"),
                ]
                from telegram import BotCommandScopeAllGroupChats
                await app.bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
                logger.info("群聊命令菜单已设置完成")
            except Exception as e:
                logger.error(f"设置命令菜单时出错: {str(e)}", exc_info=True)
                raise BotRunError(f"设置命令菜单失败: {str(e)}")

        app.post_init = set_commands

        # 添加命令处理器（只处理私聊中的命令）
        app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("me", me, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("status", status, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("char", char, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("api", api, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("load", load, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("preset", preset, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("new", new, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("save", save, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("delete", delete, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("stream", stream, filters=filters.ChatType.PRIVATE))

        # 添加消息处理器（只处理私聊消息）
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, msg_private_handle))

        # 添加命令处理器（只处理群聊中的命令）
        app.add_handler(CommandHandler("cremake", remake, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
        app.add_handler(CommandHandler("switch", switch, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
        app.add_handler(
            CommandHandler("kw", kw.handle_keyword_list, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
        app.add_handler(CallbackQueryHandler(kw.handle_keyword_add, pattern=r"^group_kw_add_"))
        app.add_handler(CallbackQueryHandler(kw.handle_keyword_delete, pattern=r"^group_kw_del_"))
        app.add_handler(CallbackQueryHandler(kw.handle_keyword_select, pattern=r"^group_kw_select_"))
        app.add_handler(CallbackQueryHandler(kw.handle_keyword_submit_delete, pattern=r"^group_kw_submit_del_"))
        app.add_handler(CallbackQueryHandler(kw.handle_keyword_cancel, pattern=r"^group_kw_cancel_"))

        # 添加 Callback 处理器
        app.add_handler(CallbackQueryHandler(callback.CallbackHandler.handle_callback_query))

        # 修改：group_msg_handle 放在之后，确保普通消息处理不会与添加关键词冲突
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
                msg_group_handle
            )
        )

        app.add_error_handler(error_handler)
        logger.info("机器人已启动...")
        # 启动机器人
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"机器人启动失败: {str(e)}", exc_info=True)
        raise BotRunError(f"机器人启动失败: {str(e)}")


if __name__ == "__main__":
    main()
