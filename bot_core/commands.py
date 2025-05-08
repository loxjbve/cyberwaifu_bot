from telegram import Update
from utils import file_utils
from telegram.ext import ContextTypes
import logging
from asyncio import Semaphore
from bot_core import public
from bot_core import conversation as conv
from bot_core.decorators import handle_command_errors, check_message_and_user,group_admin_required  # Import decorators
from utils import db_utils as db, LLM_utils as llm
import os
import json
import re

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
    info = public.update_info_get(update)
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
    info = public.update_info_get(update)  # Still need user_id
    if db.user_stream_switch(info['user_id']):
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
    info = public.update_info_get(update)
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
    info = public.update_info_get(update)
    result = conv.private_new(info['user_id'], info)
    await update.message.reply_text(f"{result}", parse_mode='MarkDown')

    # 添加选择预设的逻辑
    preset_markup = public.print_preset_list()
    if preset_markup == "没有可用的预设。":
        await update.message.reply_text(preset_markup)
    else:
        await update.message.reply_text("请为新对话选择一个预设：", reply_markup=preset_markup)

    # 添加选择角色的逻辑
    char_markup = public.print_char_list('load', 'private', info['user_id'])
    if char_markup == "没有可操作的角色。":
        await update.message.reply_text(char_markup)
    else:
        await update.message.reply_text("请为新对话选择一个角色：", reply_markup=char_markup)


@handle_command_errors
@check_message_and_user
async def save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /save 命令，保存当前对话。

    Args:
        update (Update): Telegram 更新对象。
    """
    # Decorator handles checks and basic logging
    info = public.update_info_get(update)
    result = await conv.private_save(info)
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
    info = public.update_info_get(update)
    result = f"当前角色：`{info['char']}`\r\n当前接口：`{info['api']}`\r\n当前预设：`{info['preset']}`\r\n流式传输：`{info['stream']}`\r\n"
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
    info = public.update_info_get(update)
    conv.private_new(info['user_id'], info)
    markup = public.print_char_list('load', 'private', info['user_id'])
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
    info = public.update_info_get(update)
    markup = public.print_char_list('del', 'private', info['user_id'])
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
    info = public.update_info_get(update)
    # 解析命令参数
    args = context.args if hasattr(context, 'args') else []
    if not args or len(args[0].strip()) == 0:
        await update.message.reply_text("请使用 /newchar char_name 的格式指定角色名。")
        return
    char_name = args[0].strip()
    # 标记用户进入角色描述输入状态
    if not hasattr(context.bot_data, 'newchar_state'):
        context.bot_data['newchar_state'] = {}
    context.bot_data['newchar_state'][info['user_id']] = {'char_name': char_name, 'desc_chunks': []}
    await update.message.reply_text(
        f"请上传角色描述文件（json/txt）或直接发送文本描述，完成后发送 /done 结束输入。\n如描述较长可分多条消息发送。")


@handle_command_errors
@check_message_and_user
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = public.update_info_get(update)['user_id']
    state = context.bot_data.get('newchar_state', {}).get(user_id)
    if not state:
        await update.message.reply_text("当前无待保存的角色描述。请先使用 /newchar char_name。")
        return
    char_name = state['char_name']

    # 明确指定保存目录为项目根目录下的 characters 文件夹
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # 假设当前文件在子目录中，回到根目录
    save_dir = os.path.join(project_root, 'characters')
    os.makedirs(save_dir, exist_ok=True)
    # 优先保存文件，如果有文件则直接提示，否则处理文本并保存
    if 'file_saved' in state:
        save_path = state['file_saved']
        del context.bot_data['newchar_state'][user_id]
        await update.message.reply_text(f"角色 {char_name} 已保存到 {save_path}")
        return
    desc = '\n'.join(state['desc_chunks'])
    try:
        generated_content = await llm.generate_char(desc)
        json_pattern = r'```json\s*([\s\S]*?)\s*```|```([\s\S]*?)\s*```|\{[\s\S]*\}'
        match = re.search(json_pattern, generated_content)
        if match:
            json_str = next(group for group in match.groups() if group)
            char_data = json.loads(json_str)
        else:
            char_data = {"raw_content": generated_content}
            await update.message.reply_text("警告：未能从生成内容中提取 JSON 数据，保存原始内容。")
        save_path = os.path.join(save_dir, f"{char_name}_{user_id}.json")
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(char_data, f, ensure_ascii=False, indent=2)
        del context.bot_data['newchar_state'][user_id]
        await update.message.reply_text(f"角色 {char_name} 已保存到 {save_path}")
    except json.JSONDecodeError as e:
        save_path = os.path.join(save_dir, f"{char_name}_{user_id}.txt")
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(generated_content)
        del context.bot_data['newchar_state'][user_id]
        await update.message.reply_text(f"错误：无法解析生成的 JSON 内容，保存为原始文本到 {save_path}。错误信息：{str(e)}")
    except Exception as e:
        await update.message.reply_text(f"保存角色 {char_name} 时发生错误：{str(e)}")


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
    info = public.update_info_get(update)
    markup = public.print_api_list(info['tier'])
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
    info = public.update_info_get(update)  # Still need user_id
    markup = public.print_conversations(info['user_id'])
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
    info = public.update_info_get(update)  # Still need user_id
    markup = public.print_conversations(info['user_id'], 'delete')
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
    if public.is_message_expired(update):
        logger.warning(f"忽略过期的 /remake 命令，消息ID: {update.message.message_id}")
        return
    info = public.update_info_get(update)
    if info['need_update']:
        public.group_info_update_or_create(update, context)
    info = public.update_info_get(update)
    if await conv.group_delete(info):
        logger.info(f"处理 /remake 命令，用户ID: {update.effective_user.id}")
        await update.message.reply_text("您已重开对话！")


@handle_command_errors
@group_admin_required
async def switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /switch 命令，切换群组内角色。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles basic checks and user update
    info = public.update_info_get(update)
    if info['need_update']:
        await public.group_info_update_or_create(update, context)
    info = public.update_info_get(update)
    markup = public.print_char_list('load', 'group', info['group_id'])
    if markup == "没有可操作的角色。":
        await update.message.reply_text(markup)
    else:
        await update.message.reply_text("请选择一个角色：", reply_markup=markup)

@handle_command_errors
@group_admin_required
async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /rate 命令，设置评分。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Decorator handles basic checks and user update
    info = public.update_info_get(update)
    if info['need_update']:
        await public.group_info_update_or_create(update, context)
        info = public.update_info_get(update)
    
    # 获取并验证输入参数
    args = context.args if hasattr(context, 'args') else []
    if len(args) < 1:
        await update.message.reply_text("请输入一个0-1的小数")
        return
    rate_value = float(args[0])
    if not 0 <= rate_value <= 1:
        await update.message.reply_text("请输入一个0-1的小数")
        return
    if db.group_info_update(info['group_id'],'rate',rate_value):
        await update.message.reply_text(f"已设置触发频率: {rate_value}")



@handle_command_errors
@check_message_and_user
async def addf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 /addf 命令，管理员专用，接收 target_user_id 和 value 两个参数。
    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    info = public.update_info_get(update)
    # 获取命令参数
    args = context.args if hasattr(context, 'args') else []
    if len(args) < 2:
        await update.message.reply_text("请以 /addf target_user_id value 的格式输入参数。")
        return
    target_user_id = args[0]
    value = int(args[1])
    # 权限检查
    if public.user_admin_check(info['user_id']):
        if target_user_id == 'all':
            if db.user_frequency_free(value):
                await update.message.reply_text(f"已为所有用户添加{value}条额度")
        else:
            if db.user_info_update(target_user_id, 'remain_frequency', value, True):
                await update.message.reply_text(
                    f"已为{public.user_info_get(target_user_id)['user_name']}添加{value}条额度")
    else:
        await update.message.reply_text("无权限操作，仅管理员可用。")
