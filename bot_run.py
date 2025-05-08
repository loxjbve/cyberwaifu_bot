from telegram import Update, BotCommand, BotCommandScopeDefault
from utils import file_utils
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import logging
from asyncio import Semaphore
from bot_core import public, msg, public, callback, keyword as kw, commands as cmd, decorators
from bot_core.exceptions import BotRunError  # Import from new exceptions file

ADMIN = file_utils.load_config()['admin']
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
BOT_TOKEN = file_utils.load_config()['token']


async def group_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理群聊文本消息。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Keep existing logic, decorators are for commands
    try:
        if public.is_message_expired(update):
            logger.warning(f"忽略过期的群聊消息，消息ID: {update.message.message_id}")
            return
        if 'keyword_action' in context.user_data and context.user_data['keyword_action'] == 'add':
            logger.info(f"用户正在添加关键词，忽略普通回复逻辑，用户ID: {update.effective_user.id}")
            await kw.handle_keyword_add_reply(update, context)
            return
        else:
            await msg.msg_group_handle(update, context)
    except Exception as e:
        logger.error(f"处理群聊消息时出错: {str(e)}", exc_info=True)
        # 不再向用户重复发送错误消息，避免多次回复


@decorators.check_message_and_user
async def private_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = public.update_info_get(update)['user_id']
    newchar_state = context.bot_data.get('newchar_state', {}).get(user_id)
    if newchar_state:
        await msg.newchar_handle(update, newchar_state, user_id)  # 非角色描述输入状态，交由其他handler处理
        return
    else:
        await msg.msg_private_handle(update, context)
        return


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
    except BotRunError as e:  # This should now correctly catch the imported BotRunError
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
                    BotCommand("newchar", "创建私人角色"),
                    BotCommand("delchar", "删除私人角色"),
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
        app.add_handler(CommandHandler("start", cmd.start, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("me", cmd.me, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("status", cmd.status, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("char", cmd.char, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler('newchar', cmd.newchar, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler('delchar', cmd.delchar, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("api", cmd.api, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("load", cmd.load, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("preset", cmd.preset, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("new", cmd.new, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("save", cmd.save, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("delete", cmd.delete, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("stream", cmd.stream, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler('done', cmd.done, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler('addf', cmd.addf, filters=filters.ChatType.PRIVATE))
        app.add_handler(
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND & filters.ChatType.PRIVATE,
                           private_msg_handler), group=0)
        app.add_handler(
            CommandHandler("cremake", cmd.remake, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
        app.add_handler(
            CommandHandler("switch", cmd.switch, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
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
                group_msg_handler
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
