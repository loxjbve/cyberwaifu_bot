from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import db_utils as db
from bot_core import public
from bot_core.decorators import group_admin_required


@group_admin_required
async def handle_keyword_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = public.update_info_get(update)
    if info['need_update']:
        await public.group_info_update_or_create(update, context)
        info = public.update_info_get(update)
    keywords = db.group_keyword_get(info['group_id'])
    if not keywords:
        keywords_text = "当前群组没有设置关键词。"
    else:
        keywords_text = "当前群组的关键词列表：\r\n" + ", ".join([f"`{kw}`" for kw in keywords])
    keyboard = [
        [InlineKeyboardButton("添加关键词", callback_data=f"group_kw_add_{info['group_id']}"),
         InlineKeyboardButton("删除关键词", callback_data=f"group_kw_del_{info['group_id']}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(keywords_text, reply_markup=reply_markup, parse_mode='Markdown')


@group_admin_required
async def handle_keyword_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split('_')[-1])
    keyboard = [[InlineKeyboardButton("取消", callback_data=f"group_kw_cancel_{group_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data['original_message_id'] = query.message.message_id
    await query.message.edit_text("请回复此消息，输入要添加的关键词（用空格分隔）。", reply_markup=reply_markup)
    context.user_data['keyword_action'] = 'add'
    context.user_data['group_id'] = group_id


@group_admin_required
async def handle_keyword_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split('_')[-1])
    keywords = db.group_keyword_get(group_id)
    if not keywords:
        await query.message.edit_text("当前群组没有关键词可删除。")
        return
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
    await query.message.edit_text("请选择要删除的关键词：", reply_markup=reply_markup)


@group_admin_required
async def handle_keyword_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    keyword = parts[3]
    group_id = int(parts[-1])
    if 'to_delete' not in context.user_data:
        context.user_data['to_delete'] = []
    if keyword not in context.user_data['to_delete']:
        context.user_data['to_delete'].append(keyword)
    keywords = db.group_keyword_get(group_id)
    remaining_keywords = [kw for kw in keywords if kw not in context.user_data['to_delete']]
    if not remaining_keywords:
        await query.message.edit_text("已选择所有关键词进行删除。")
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
    selected_text = ", ".join([f"`{kw}`" for kw in context.user_data['to_delete']]) if context.user_data['to_delete'] else "无"
    await query.message.edit_text(f"已选择删除的关键词：{selected_text}\r\n请选择更多要删除的关键词：",
                                  reply_markup=reply_markup, parse_mode='Markdown')


@group_admin_required
async def handle_keyword_submit_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split('_')[-1])
    if 'to_delete' in context.user_data and context.user_data.get('keyword_action') == 'delete':
        keywords = db.group_keyword_get(group_id)
        new_keywords = [kw for kw in keywords if kw not in context.user_data['to_delete']]
        db.group_keyword_set(group_id, new_keywords)
        await query.message.edit_text(f"已成功删除关键词：{', '.join(context.user_data['to_delete'])}")
    else:
        await query.message.edit_text("删除操作未完成或已取消。")
    context.user_data.clear()


@group_admin_required
async def handle_keyword_add_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'keyword_action' not in context.user_data or context.user_data['keyword_action'] != 'add':
        return
    group_id = context.user_data.get('group_id')
    original_message_id = context.user_data.get('original_message_id')
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        input_text = update.message.text.strip()
        new_keywords = [kw.strip() for kw in input_text.split() if kw.strip()]
        if not new_keywords:
            await update.message.reply_text("未提供有效的关键词。")
            return
        current_keywords = db.group_keyword_get(group_id)
        updated_keywords = list(set(current_keywords + new_keywords))
        db.group_keyword_set(group_id, updated_keywords)
        try:
            await context.bot.delete_message(chat_id=update.message.chat.id, message_id=update.message.message_id)
        except Exception as e:
            print(f"删除用户回复消息失败: {e}")
        try:
            await context.bot.delete_message(chat_id=update.message.chat.id,
                                             message_id=update.message.reply_to_message.message_id)
        except Exception as e:
            print(f"删除提示消息失败: {e}")
        if original_message_id:
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=update.message.chat.id,
                    message_id=original_message_id,
                    reply_markup=None
                )
            except Exception as e:
                print(f"清除按钮失败: {e}")
        await context.bot.send_message(
            chat_id=update.message.chat.id,
            text=f"已成功添加关键词：{', '.join(new_keywords)}"
        )
        context.user_data.clear()
    else:
        await update.message.reply_text("请回复 Bot 的消息来添加关键词。")


@group_admin_required
async def handle_keyword_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split('_')[-1])
    original_message_id = context.user_data.get('original_message_id')
    if original_message_id:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=query.message.chat.id,
                message_id=original_message_id,
                reply_markup=None
            )
        except Exception as e:
            print(f"清除按钮失败: {e}")
    context.user_data.clear()
    await query.message.edit_text("操作已取消，关键词列表未修改。")
