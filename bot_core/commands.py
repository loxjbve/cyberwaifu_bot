from telegram import Update
from utils import file_utils
from telegram.ext import ContextTypes
import logging
from asyncio import Semaphore
from bot_core import tg, user, public, group
from bot_core import conversation as conv
from bot_core.decorators import handle_command_errors, check_message_and_user  # Import decorators
from utils import db_utils as db

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
ADMIN = file_utils.load_config()['admin']


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
    user_info = tg.user_msg_parse(update)  # Still need user_id
    info = user.info_get(user_info['user_id'])
    await update.message.reply_text(
        f"您好，{info['first_name']} {info['last_name']}！这是由 @Xi_cuicui 开发的`CyberWaifu`项目。\r\n已为您创建用户档案。\r\n使用`/char"
        f"`可以切换角色\r\n"
        f"使用`/preset`可切换聊天预设\r\n使用`/new`可展开新对话\r\n使用`/save`可以保存当前会话，并通过`/load` `/delete`读取或删除\r\n"
        f"使用`/stream`可切换流式传输模式\r\n使用`/newchar`和`/delchar`可以管理您的角色")


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
    user_info = tg.user_msg_parse(update)  # Still need user_id
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
    user_info = tg.user_msg_parse(update)  # Still need user_id
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
    user_info = tg.user_msg_parse(update)  # Still need user_id
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
    user_info = tg.user_msg_parse(update)  # Still need user_id
    config = user.config_get(user_info['user_id'])
    result = await conv.private_save(config)
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
    user_info = tg.user_msg_parse(update)  # Still need user_id
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
    user_info = tg.user_msg_parse(update)
    markup = public.print_char_list('load', 'private', user_info['user_id'])
    if markup == "没有可操作的角色。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个角色：", reply_markup=markup)


@handle_command_errors
@check_message_and_user
async def delchar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /delchar 命令，删除角色。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles checks and basic logging
    user_info = tg.user_msg_parse(update)
    markup = public.print_char_list('del', 'private', user_info['user_id'])
    if markup == "没有可操作的角色。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个角色：", reply_markup=markup)


@handle_command_errors
@check_message_and_user
async def newchar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /newchar 命令，创建私人角色

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    user_info = tg.user_msg_parse(update)
    user_id = user_info['user_id']
    # 解析命令参数
    args = context.args if hasattr(context, 'args') else []
    if not args or len(args[0].strip()) == 0:
        await update.message.reply_text("请使用 /newchar char_name 的格式指定角色名。")
        return
    char_name = args[0].strip()
    # 标记用户进入角色描述输入状态
    if not hasattr(context.bot_data, 'newchar_state'):
        context.bot_data['newchar_state'] = {}
    context.bot_data['newchar_state'][user_id] = {'char_name': char_name, 'desc_chunks': []}
    await update.message.reply_text(
        f"请上传角色描述文件（json/txt）或直接发送文本描述，完成后发送 /done 结束输入。\n如描述较长可分多条消息发送。")


# 新增/done命令，完成角色描述输入
@handle_command_errors
@check_message_and_user
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = tg.user_msg_parse(update)['user_id']
    state = context.bot_data.get('newchar_state', {}).get(user_id)
    if not state:
        await update.message.reply_text("当前无待保存的角色描述。请先使用 /newchar char_name。")
        return
    char_name = state['char_name']
    import os
    save_dir = os.path.join(os.path.dirname(__file__), 'characters')
    os.makedirs(save_dir, exist_ok=True)
    # 优先保存文件，如果有文件则直接提示，否则保存文本为txt
    if 'file_saved' in state:
        save_path = state['file_saved']
        del context.bot_data['newchar_state'][user_id]
        await update.message.reply_text(f"角色 {char_name} 已保存到 {save_path}")
        return
    desc = '\n'.join(state['desc_chunks'])
    save_path = os.path.join(save_dir, f"{char_name}_{user_id}.txt")
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(desc)
    del context.bot_data['newchar_state'][user_id]
    await update.message.reply_text(f"角色 {char_name} 已保存到 {save_path}")


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
    user_info = tg.user_msg_parse(update)  # Still need user_id
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
    user_info = tg.user_msg_parse(update)  # Still need user_id
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
    user_info = tg.user_msg_parse(update)  # Still need user_id
    markup = public.print_conversations(user_info['user_id'], 'delete')
    if markup == "没有可用的对话。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个对话：", reply_markup=markup)


@handle_command_errors  # Only apply error handling for now
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
@check_message_and_user  # Apply user check, admin check remains inside
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
        await update.message.reply_text("该指令仅管理员可用")
        return
    group_info = await tg.group_msg_parse(update)
    markup = public.print_char_list('load', 'group', group_info['group_id'])
    if markup == "没有可操作的角色。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个角色：", reply_markup=markup)


@handle_command_errors
@check_message_and_user
async def addf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /addf 命令，管理员专用，接收 target_user_id 和 value 两个参数。
    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    user_info = tg.user_msg_parse(update)
    user_id = user_info['user_id']
    # 获取命令参数
    args = context.args if hasattr(context, 'args') else []
    if len(args) < 2:
        await update.message.reply_text("请以 /addf target_user_id value 的格式输入参数。")
        return
    target_user_id = args[0]
    value = int(args[1])
    # 权限检查
    if user.is_admin(user_id):
        if target_user_id == 'all':
            if db.user_frequency_free(value):
                await update.message.reply_text(f"已为所有用户添加{value}条额度")
        else:
            if db.user_info_update(target_user_id, 'remain_frequency', value, True):
                await update.message.reply_text(f"已为{user.info_get(target_user_id)['user_name']}添加{value}条额度")
    else:
        await update.message.reply_text("无权限操作，仅管理员可用。")
