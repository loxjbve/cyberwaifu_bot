from typing import Optional, Dict, List, Any
from telegram import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeAllGroupChats
from utils import file_utils
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import logging
from asyncio import Semaphore
from bot_core import public, msg, callback, keyword as kw, commands as cmd, decorators
from bot_core.exceptions import BotRunError, ConfigError

def setup_logging() -> None:
    """初始化日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("bot.log"),
            logging.StreamHandler()
        ]
    )

def load_config() -> Dict[str, Any]:
    """加载并验证配置
    
    Returns:
        Dict[str, Any]: 包含验证后的配置信息
        
    Raises:
        ConfigError: 配置验证失败时抛出
    """
    config = file_utils.load_config()
    required_fields = ['admin', 'token']
    
    for field in required_fields:
        if field not in config:
            raise ConfigError(f"缺少必需的配置项: {field}")
        if not config[field]:
            raise ConfigError(f"配置项不能为空: {field}")
    
    return config

setup_logging()
logger = logging.getLogger(__name__)

try:
    config = load_config()
    ADMIN = config['admin']
    BOT_TOKEN = config['token']
    semaphore = Semaphore(5)  # 用于限制并发请求数
except ConfigError as e:
    logger.critical(f"配置加载失败: {str(e)}")
    raise SystemExit(1)


@decorators.check_message_and_user
async def group_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理群聊文本消息。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。

    Note:
        此函数已使用 @check_message_and_user 装饰器进行用户和消息有效性检查。
        如果消息过期或用户无效，装饰器会自动处理并返回。
    """
    try:
        if public.is_message_expired(update):
            logger.warning(f"忽略过期的群聊消息，消息ID: {update.message.message_id}，群组ID: {update.message.chat.id}")
            return

        # 检查是否在关键词添加模式
        keyword_action = context.user_data.get('keyword_action')
        if keyword_action == 'add':
            user_id = update.effective_user.id
            logger.info(f"用户正在添加关键词，忽略普通回复逻辑，用户ID: {user_id}，群组ID: {update.message.chat.id}")
            await kw.handle_keyword_add_reply(update, context)
            return

        # 处理普通群聊消息
        await msg.msg_group_handle(update, context)
    except Exception as e:
        logger.error(
            f"处理群聊消息时出错: {str(e)}，用户ID: {update.effective_user.id}，群组ID: {update.message.chat.id}",
            exc_info=True
        )


@decorators.check_message_and_user
async def private_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理私聊消息。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。

    Note:
        此函数已使用 @check_message_and_user 装饰器进行用户和消息有效性检查。
        如果消息无效或用户未注册，装饰器会自动处理并返回。
    """
    try:
        user_info = public.update_info_get(update)
        user_id = user_info['user_id']
        
        # 检查是否在新建角色状态
        newchar_state = context.bot_data.get('newchar_state', {}).get(user_id)
        if newchar_state:
            logger.info(f"用户处于新建角色状态，用户ID: {user_id}")
            await msg.newchar_handle(update, newchar_state, user_id)
            return

        # 处理普通私聊消息
        await msg.msg_private_handle(update, context)
    except Exception as e:
        logger.error(f"处理私聊消息时出错: {str(e)}，用户ID: {user_id}", exc_info=True)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    全局错误处理器，捕获并处理所有未捕获的异常。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。

    Note:
        错误处理的优先级：
        1. Telegram API相关错误
        2. Bot运行时错误
        3. 配置错误
        4. 其他未捕获的异常
    """
    error = context.error
    chat_id = update.effective_chat.id if update and update.effective_chat else "未知"
    user_id = update.effective_user.id if update and update.effective_user else "未知"

    try:
        if isinstance(error, telegram.error.BadRequest):
            logger.error(f"Telegram API错误: {str(error)}，用户ID: {user_id}，聊天ID: {chat_id}", exc_info=True)
            error_message = "发送消息时发生错误，请稍后重试。"
        elif isinstance(error, BotRunError):
            logger.error(f"Bot运行错误: {str(error)}，用户ID: {user_id}，聊天ID: {chat_id}", exc_info=True)
            error_message = "Bot运行出现错误，请稍后重试。"
        elif isinstance(error, ConfigError):
            logger.error(f"配置错误: {str(error)}，用户ID: {user_id}，聊天ID: {chat_id}", exc_info=True)
            error_message = "Bot配置出现错误，请联系管理员。"
        else:
            logger.error(f"未处理的错误: {str(error)}，用户ID: {user_id}，聊天ID: {chat_id}", exc_info=True)
            error_message = "发生未知错误，请稍后重试。"

        # 仅在有效的消息上下文中发送错误提示
        if update and update.message and not context.user_data.get('error_notified'):
            await update.message.reply_text(error_message, parse_mode=None)
            context.user_data['error_notified'] = True  # 标记已发送错误消息
    except Exception as e:
        # 确保错误处理器本身的错误不会导致程序崩溃
        logger.critical(f"错误处理器发生错误: {str(e)}，原始错误: {str(error)}", exc_info=True)


def setup_command_handlers(app: Application) -> None:
    """
    设置命令处理器。

    Args:
        app (Application): Telegram Application 实例。
    """
    # 私聊命令处理器
    private_handlers = [
        CommandHandler("start", cmd.start, filters=filters.ChatType.PRIVATE),
        CommandHandler("me", cmd.me, filters=filters.ChatType.PRIVATE),
        CommandHandler("status", cmd.status, filters=filters.ChatType.PRIVATE),
        CommandHandler("char", cmd.char, filters=filters.ChatType.PRIVATE),
        CommandHandler('newchar', cmd.newchar, filters=filters.ChatType.PRIVATE),
        CommandHandler('delchar', cmd.delchar, filters=filters.ChatType.PRIVATE),
        CommandHandler("api", cmd.api, filters=filters.ChatType.PRIVATE),
        CommandHandler("load", cmd.load, filters=filters.ChatType.PRIVATE),
        CommandHandler("preset", cmd.preset, filters=filters.ChatType.PRIVATE),
        CommandHandler("new", cmd.new, filters=filters.ChatType.PRIVATE),
        CommandHandler("save", cmd.save, filters=filters.ChatType.PRIVATE),
        CommandHandler("delete", cmd.delete, filters=filters.ChatType.PRIVATE),
        CommandHandler("stream", cmd.stream, filters=filters.ChatType.PRIVATE),
        CommandHandler('done', cmd.done, filters=filters.ChatType.PRIVATE),
        CommandHandler('addf', cmd.addf, filters=filters.ChatType.PRIVATE),
    ]
    
    # 群组命令处理器
    group_handlers = [
        CommandHandler("cremake", cmd.remake, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        CommandHandler("switch", cmd.switch, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        CommandHandler("kw", kw.handle_keyword_list, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        CommandHandler("rate", cmd.rate, filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
    ]
    
    # 关键词处理器
    keyword_handlers = [
        CallbackQueryHandler(kw.handle_keyword_add, pattern=r"^group_kw_add_"),
        CallbackQueryHandler(kw.handle_keyword_delete, pattern=r"^group_kw_del_"),
        CallbackQueryHandler(kw.handle_keyword_select, pattern=r"^group_kw_select_"),
        CallbackQueryHandler(kw.handle_keyword_submit_delete, pattern=r"^group_kw_submit_del_"),
        CallbackQueryHandler(kw.handle_keyword_cancel, pattern=r"^group_kw_cancel_"),
    ]
    
    # 消息处理器
    message_handlers = [
        MessageHandler(
            (filters.TEXT | filters.Document.ALL) & ~filters.COMMAND & filters.ChatType.PRIVATE,
            private_msg_handler
        ),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
            group_msg_handler
        ),
    ]
    
    # 注册所有处理器
    for handler in private_handlers + group_handlers + keyword_handlers:
        app.add_handler(handler)
    
    # 添加通用回调处理器
    app.add_handler(CallbackQueryHandler(callback.CallbackHandler.handle_callback_query))
    
    # 添加消息处理器（确保在最后添加）
    for handler in message_handlers:
        app.add_handler(handler)

def main() -> None:
    """
    主函数，初始化并启动Telegram Bot。
    
    Note:
        1. 初始化应用实例
        2. 设置命令菜单
        3. 注册消息处理器
        4. 启动轮询
        5. 确保资源正确释放
    """
    try:
        # 创建 Application 实例
        app = Application.builder().token(BOT_TOKEN).build()

        def get_command_menus() -> Dict[str, List[BotCommand]]:
            """
            获取命令菜单配置。

            Returns:
                Dict[str, List[BotCommand]]: 包含私聊和群组命令菜单的字典。
            """
            return {
                'private': [
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
                ],
                'group': [
                    BotCommand("cremake", "重开对话"),
                    BotCommand("kw", "设置bot触发关键词"),
                    BotCommand("switch", "切换群组内的角色"),
                    BotCommand("rate", "设置触发频率"),
                ]
            }

        async def setup_command_menu(app_instance: Application) -> None:
            """
            设置Bot的命令菜单。

            Args:
                app_instance (Application): Telegram Application 实例。

            Raises:
                BotRunError: 设置命令菜单失败时抛出。
            """
            try:
                command_menus = get_command_menus()
                
                # 设置私聊命令菜单
                await app_instance.bot.set_my_commands(
                    command_menus['private'],
                    scope=BotCommandScopeDefault()
                )
                logger.info("私聊命令菜单已设置完成")

                # 设置群组命令菜单
                await app_instance.bot.set_my_commands(
                    command_menus['group'],
                    scope=BotCommandScopeAllGroupChats()
                )
                logger.info("群组命令菜单已设置完成")
            except Exception as e:
                error_msg = f"设置命令菜单失败: {str(e)}"
                logger.error(error_msg, exc_info=True)
                raise BotRunError(error_msg)

        # 设置初始化函数
        app.post_init = setup_command_menu

        # 设置命令处理器
        setup_command_handlers(app)

        # 添加错误处理器
        app.add_error_handler(error_handler)
        logger.info("机器人初始化完成，准备启动...")

        # 启动机器人并确保资源正确释放
        try:
            logger.info("开始轮询更新...")
            app.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            logger.error(f"轮询过程中发生错误: {str(e)}", exc_info=True)
            raise
        finally:
            logger.info("正在关闭数据库连接...")
            from utils.db_utils import close_all_connections
            close_all_connections()
            logger.info("数据库连接已关闭")
    except Exception as e:
        logger.error(f"机器人启动失败: {str(e)}", exc_info=True)
        raise BotRunError(f"机器人启动失败: {str(e)}")


if __name__ == "__main__":
    main()
