import asyncio
import re
import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from utils import prompt_utils as prompt, LLM_utils as llm, text_utils as txt, db_utils as db
from telegram.error import BadRequest, TelegramError
from bot_core import public
from bot_core import conversation as conv
import telegram

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


# 自定义异常类
class BotError(Exception):
    """自定义Bot异常基类"""
    pass


class DatabaseError(BotError):
    """数据库操作相关异常"""
    pass


class LLMError(BotError):
    """LLM服务调用相关异常"""
    pass


async def msg_group_handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await public.group_info_update_or_create(update, context)
    info = public.update_info_get(update)
    public.group_dialog_add(info)
    needs_reply = public.group_msg_needs_reply(update, context)
    logger.info(f"群聊消息检查回复需求，结果: {needs_reply}，用户ID: {update.effective_user.id}")
    if needs_reply == 'random' or needs_reply == 'keyword':
        await group_once_handle(update, context, needs_reply)
        return
    if needs_reply == 'reply' or needs_reply == '@':
        await group_chat_handle(update)
        return


async def msg_private_handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理私聊文本消息。
    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Keep existing logic, decorators are for commands
    try:
        info = public.update_info_get(update)
        if not info['conv_id']:  # 创建聊天
            conv.private_new(info['user_id'], info)
            info = public.update_info_get(update)

        logger.info(f"处理私聊消息，用户: {info['user_name']}\r\n{info['message_text']}")
        if info['remain'] > 0:
            result = await private_chat_handle(update)
            if result is not None:
                try:
                    await update.message.reply_text(result, parse_mode="markdown")
                except telegram.error.BadRequest as e:
                    logger.warning(f"Markdown 解析错误: {str(e)}, 禁用 Markdown 重试")
                    await update.message.reply_text(result, parse_mode=None)
        else:
            await update.message.reply_text("您的额度已用尽")

    except Exception as e:
        logger.error(f"处理私聊消息时出错: {str(e)}", exc_info=True)
        await update.message.reply_text(f"处理消息时发生错误{str(e)}，请稍后重试。")


async def newchar_handle(update, newchar_state, user_id):
    if update.message.document:
        file = update.message.document
        if file.mime_type in ['application/json', 'text/plain'] or file.file_name.endswith(('.json', '.txt')):
            file_obj = await file.get_file()
            import os
            save_dir = os.path.join(os.path.dirname(__file__), 'characters')
            os.makedirs(save_dir, exist_ok=True)
            char_name = newchar_state['char_name']
            target_ext = os.path.splitext(file.file_name)[1] if os.path.splitext(file.file_name)[1] else '.txt'
            save_path = os.path.join(save_dir, f"{char_name}_{user_id}{target_ext}")
            await file_obj.download_to_drive(save_path)
            newchar_state['file_saved'] = save_path
            await update.message.reply_text(f"文件已保存为 {save_path}，如需补充文本可继续发送，发送 /done 完成。")
        else:
            await update.message.reply_text("仅支持json或txt文件。")
        return
    # 文本输入
    if update.message.text:
        newchar_state['desc_chunks'].append(update.message.text)
        await update.message.reply_text("文本已接收，可继续发送文本或文件，发送 /done 完成。")
        return


async def group_once_handle(update, context, trigger_type: str) -> Optional[str]:
    """
    一次性生成群聊消息回复。

    Args:
        update (Update): Telegram更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
        trigger_type (str): 触发类型。

    Returns:
        Optional[str]: 生成的回复内容。如果是异步后台处理，返回 None。
    """
    info = public.update_info_get(update)
    try:
        api, char, preset = db.group_config_get(info['group_id'])
        key, url, model_name = llm.get_api_config(api)
        client, model = llm.build_client(key, url, model_name)
        prompts_str = prompt.build_prompts(char, info['message_text'], preset)
        # 发送占位符消息
        placeholder_message = await update.message.reply_text("思考中...")
        # 后台异步生成并编辑消息
        asyncio.create_task(
            _generate_message_once_background(client, model, prompts_str, info['group_name'], info['user_name'], info['message_id'], info['group_id'],
                                              trigger_type, placeholder_message))
        return None
    except Exception as e:
        logger.error(f"一次性生成群聊回复失败, group: {info['group_name']}, user: {info['user_name']}, 错误: {str(e)}")
        raise LLMError(f"一次性生成群聊回复失败: {str(e)}")


async def group_chat_handle(update) -> Optional[str]:
    """处理群聊消息"""
    info = public.update_info_get(update)
    conv_id = db.conversation_group_get(info['group_id'], info['user_id'])
    info['conv_id'] = conv_id
    if not conv_id:
        await conv.group_new(info)
        conv_id = db.conversation_group_get(info['group_id'], info['user_id'])
    try:
        api_char_preset = db.group_config_get(info['group_id'])
        if not api_char_preset:
            logger.error(f"群组配置不存在，group_id: {info['group_id']}")
            await update.message.reply_text("群组未初始化或配置缺失，请先设置群组角色和API。")
            return None
        api, char, preset = api_char_preset
        key, url, model_name = llm.get_api_config(api)
        client, model = llm.build_client(key, url, model_name)
        prompts = prompt.insert_text(prompt.build_prompts(char, info['message_text'], preset),
                                     f"用户的姓名或网名是‘{info['user_name']}’\r\n",
                                     '以下是用户最新输入:\r\n', 'before')
        # 发送占位符消息
        placeholder_message = await update.message.reply_text("思考中...")
        # 后台异步生成并编辑消息
        # print(f"{group_name}的{user_name}需要回复，对话id{conv_id}输入内容{input_text}")
        asyncio.create_task(
            _generate_group_message_background(info, client, model, prompts, conv_id, info['group_name'],
                                               info['user_name'],
                                               placeholder_message))
        return None
    except Exception as e:
        logger.error(f"{info['group_name']}群组配置获取失败,, 错误: {str(e)}")
        raise DatabaseError(f"群组配置获取失败: {str(e)}")


async def private_chat_handle(update: Update) -> Optional[str]:
    """处理私聊消息"""
    info = public.update_info_get(update)
    key, url, model_name = llm.get_api_config(info['api'])
    client, model = llm.build_client(key, url, model_name)
    prompts = prompt.build_prompts(info['char'], info['message_text'], info['preset'])
    if info['stream'] == 'yes':
        # 使用 asyncio.create_task 将流式处理放到后台执行
        asyncio.create_task(_streaming_response(update))
        return None  # 立即返回，不阻塞事件循环
    else:

        placeholder_message = await update.message.reply_text("思考中...")  # 发送占位符
        # 非流式也使用后台任务处理
        asyncio.create_task(
            _non_streaming_response(info, client, model, prompts, placeholder_message))
        return None  # 立即返回


async def _generate_message_once_background(client, model,
                                            prompts_str, group_name, user_name, message_id, group_id,
                                            trigger_type, placeholder_message):
    try:
        response = await llm.get_response_no_stream(client, model, prompts_str, conv_id=0, output_type='once')
        response_token = llm.calculate_token_count(response)
        logger.info(
            f"一次性群聊回复完成, group_name: {group_name}, user_name: {user_name}, output_token: {response_token}")
        cleared_response = txt.extract_tag_content(response, 'content') or response
        # 检查回复是否为空
        if not cleared_response or cleared_response.strip() == "":
            logger.warning(f"一次性群聊回复内容为空, group_name: {group_name}, user_name: {user_name}")
            cleared_response = "抱歉，我暂时无法回复这条消息。"
        db.group_dialog_update(message_id, 'trigger_type', trigger_type, group_id)
        db.group_dialog_update(message_id, 'raw_response', response, group_id)
        db.group_dialog_update(message_id, 'processed_response', cleared_response, group_id)
        await _finalize_message(placeholder_message, cleared_response)
    except Exception as e:
        logger.error(f"一次性群聊回复后台处理失败: {str(e)}", exc_info=True)
        try:
            await placeholder_message.edit_text(f"处理消息时出错，请稍后再试。\r\n{str(e)}")
        except Exception as edit_e:
            logger.error(f"编辑群聊错误消息失败: {edit_e}")


async def _generate_group_message_background(info, client, model, prompts, conv_id, group_name, user_name,
                                             placeholder_message):
    try:
        response = await llm.get_response_no_stream(client, model, prompts, conv_id, 'group')
        response_token = llm.calculate_token_count(response)
        logger.info(
            f"群聊非流式回复完成, group_name: {group_name}, user_name: {user_name}, output_token: {response_token}")
        cleared_response = txt.extract_tag_content(response, 'content') or response
        # 检查回复是否为空
        if not cleared_response or cleared_response.strip() == "":
            cleared_response = response
        await conv.group_update(info, response, cleared_response, placeholder_message)
        await _finalize_message(placeholder_message, str(cleared_response))
    except Exception as e:
        logger.error(f"群聊非流式回复后台处理失败: {str(e)}", exc_info=True)
        try:
            await placeholder_message.edit_text("处理消息时出错，请稍后再试。")
        except Exception as edit_e:
            logger.error(f"编辑群聊错误消息失败: {edit_e}")


async def _streaming_response(update) -> None:
    """处理流式传输回复逻辑，生成并逐步更新响应内容"""

    info = public.update_info_get(update)
    logger.info(f"使用流式传输生成私聊回复, user_id: {info['user_id']}")
    key, url, model_name = llm.get_api_config(info['api'])
    client, model = llm.build_client(key, url, model_name)
    prompts = prompt.build_prompts(info['char'], info['message_text'], info['preset'])
    sent_message = None  # 初始化 sent_message
    try:
        # 初始化响应消息
        sent_message = await update.message.reply_text("...", parse_mode="markdown")
        msg_id = sent_message.message_id
        # 获取流式响应并处理
        full_response = await _process_streaming_response_background(client, model, prompts, info['conv_id'],
                                                                     sent_message)
        cleared_response = txt.extract_tag_content(full_response, 'content') or full_response
        # 最终更新消息内容
        await _finalize_message(sent_message, cleared_response)
        # 记录 token 和对话内容 (awaiting the async function)
        await conv.dialog_add(info['user_id'], info['conv_id'], prompts, info['message_text'], full_response,
                              cleared_response, msg_id)
        if not cleared_response.startswith('API调用失败:'):
            if db.user_info_update(info['user_id'], 'remain_frequency', -1, True):
                logger.info(f"{info['user_name']}已扣除，剩余{info['remain']}")
    except Exception as e:
        logger.error(f"处理流式响应时出错: {e}", exc_info=True)
        if sent_message:
            try:
                await sent_message.edit_text("处理消息时出错，请稍后再试。")
            except Exception as edit_e:
                logger.error(f"编辑流式错误消息失败: {edit_e}")


async def _non_streaming_response(info, client, model, prompts,
                                  placeholder_message: telegram.Message) -> None:
    """
    处理非流式传输回复逻辑 (后台任务)。

    Args:
        update (Update): Telegram更新对象。
        client: LLM客户端。
        model: LLM模型。
        prompts (str): 提示词。
        conv_id (int): 对话ID。
        placeholder_message (telegram.Message): 占位符消息对象。
    """

    try:
        logger.info(f"{info['user_name']}后台处理非流式私聊回复，模型{model}")
        # 注意：llm.get_response_no_stream 是异步函数，必须直接 await，不能用 asyncio.to_thread
        full_response = await llm.get_response_no_stream(client, model, prompts, info['conv_id'], 'private')
        response_token = llm.calculate_token_count(full_response)
        # 调用异步版本的 get_current_input_token
        input_token = await llm.get_current_input_token(info['conv_id'], 'private', prompts, True)
        logger.info(
            f"非流式生成私聊回复完成, user_id: {info['user_name']}, input_token: {input_token}, output_token: {response_token}")

        cleared_response = txt.extract_tag_content(full_response, 'content') or full_response

        # 数据库操作也放入后台线程
        current_turn_order = await asyncio.to_thread(db.dialog_turn_get, info['conv_id'], 'private')
        await asyncio.to_thread(db.dialog_content_add, info['conv_id'], 'user', current_turn_order + 1,
                                info['message_text'],
                                re.sub(r'<[^>]*>', '', info['message_text']), info['message_id'], 'private')  # 记录原始消息ID
        await asyncio.to_thread(db.dialog_content_add, info['conv_id'], 'assistant', current_turn_order + 2,
                                full_response, cleared_response, placeholder_message.message_id, 'private')  # 记录占位符消息ID
        await asyncio.to_thread(db.conversation_turns_update, info['conv_id'], current_turn_order + 2, 'private')
        await asyncio.to_thread(db.user_info_update, info['user_id'], 'input_tokens', input_token, True)
        await asyncio.to_thread(db.user_info_update, info['user_id'], 'output_tokens', response_token, True)
        await asyncio.to_thread(db.user_info_update, info['user_id'], 'dialog_turns', 2, True)
        # 编辑占位符消息
        await _finalize_message(placeholder_message, cleared_response)
        if cleared_response.startswith('API调用失败:') == False:
            if db.user_info_update(info['user_id'], 'remain_frequency', -1, True):
                logger.info(f"{info['user_name']}已扣除，剩余{info['remain'] - 1}")

    except TypeError as te:
        # Catch the specific TypeError if calculate_token_count fails
        logger.error(f"后台处理非流式回复时发生类型错误 (可能在 token 计算时): {te}", exc_info=True)
        logger.error(f"full_response type: {type(full_response)}, value: {full_response}")
        try:
            await placeholder_message.edit_text("处理回复时发生内部错误 (类型错误)。")
        except Exception as edit_e:
            logger.error(f"编辑错误消息失败: {edit_e}")
    except Exception as e:
        logger.error(f"{info['user_name']}后台处理非流式回复失败, 错误: {e}", exc_info=True)
        try:
            await placeholder_message.edit_text("处理消息时出错，请稍后再试。")
        except Exception as edit_e:
            logger.error(f"编辑错误消息失败: {edit_e}")


async def _process_streaming_response_background(client, model, prompts: str, conv_id: int, sent_message) -> str:
    """
    处理流式传输响应，定期更新消息内容。
    """
    response_chunks = []
    last_update_time = asyncio.get_event_loop().time()
    last_updated_content = "..."
    # Correctly iterate over the async generator
    async for chunk in llm.get_response_stream(client, model, prompts, conv_id, 'private'):
        response_chunks.append(chunk)
        full_response = "".join(response_chunks)
        current_time = asyncio.get_event_loop().time()
        # 每 8 秒或内容显著变化时更新消息
        if current_time - last_update_time >= 8 and full_response != last_updated_content:
            await _update_message(sent_message, full_response, last_updated_content)
            last_updated_content = full_response
            last_update_time = current_time
        # 短暂让出事件循环控制权，避免长时间占用
        await asyncio.sleep(0.01)
    return "".join(response_chunks)


async def _update_message(sent_message, full_response: str, last_updated_content: str) -> None:
    """
    更新消息内容，避免频繁更新导致 Telegram API 过载。
    Args:
        sent_message: 已发送的消息对象。
        full_response (str): 当前完整的响应内容。
        last_updated_content (str): 上次更新的内容。
    """
    try:
        # Telegram 单条消息最大长度限制4096字符，保险起见用4000
        MAX_LEN = 4000
        if len(full_response) > MAX_LEN:
            full_response = full_response[-MAX_LEN:]
        await sent_message.edit_text(full_response, parse_mode="markdown")
    except BadRequest as e:
        logger.warning(f"Markdown 解析错误: {str(e)}, 禁用 Markdown 重试")
        try:
            await sent_message.edit_text(full_response, parse_mode=None)
        except Exception as e2:
            logger.error(f"再次尝试发送消息失败: {e2}")
    except TelegramError as e:
        if "Message is not modified" in str(e):
            logger.debug(f"消息内容未变化，跳过更新: {str(e)}")
        else:
            logger.error(f"更新消息时出错: {str(e)}")


async def _finalize_message(sent_message, cleared_response: str) -> None:
    """
    最终更新消息内容，确保显示最终的处理后的响应。
    Args:
        sent_message: 已发送的消息对象。
        cleared_response (str): 处理后的最终响应内容。
    """
    try:
        # Telegram 单条消息最大长度限制4096字符，保险起见用4000
        MAX_LEN = 4000
        if len(cleared_response) <= MAX_LEN:
            await sent_message.edit_text(cleared_response, parse_mode="markdown")
        else:
            # 超长时分两段发送，先发前半段，再发后半段
            await sent_message.edit_text(cleared_response[:MAX_LEN], parse_mode="markdown")
            await sent_message.reply_text(cleared_response[MAX_LEN:], parse_mode="markdown")
    except BadRequest as e:
        logger.warning(f"Markdown 解析错误: {str(e)}, 禁用 Markdown 重试")
        try:
            if len(cleared_response) <= MAX_LEN:
                await sent_message.edit_text(cleared_response, parse_mode=None)
            else:
                await sent_message.edit_text(cleared_response[:MAX_LEN], parse_mode=None)
                await sent_message.reply_text(cleared_response[MAX_LEN:], parse_mode=None)
        except Exception as e2:
            logger.error(f"再次尝试发送消息失败: {e2}")
    except TelegramError as e:
        if "Message is not modified" in str(e):
            logger.debug(f"最终更新时消息内容未变化，跳过更新: {str(e)}")
        else:
            logger.error(f"最终更新消息时出错: {str(e)}")
