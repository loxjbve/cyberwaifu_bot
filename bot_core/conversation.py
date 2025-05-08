import asyncio
import random
import re
import logging
from telegram import Update
from utils import LLM_utils as llm, db_utils as db
from bot_core.exceptions import BotError, DatabaseError, LLMError

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


def private_new(user_id, config) -> str:
    """
    创建新的私聊对话。

    Returns:
        str: 创建结果信息。
    """
    try:
        while True:
            new_conv_id = random.randint(10000000, 99999999)
            if db.conversation_private_check(new_conv_id):
                character = config['char']
                api = config['api']
                preset = config['preset']
                db.conversation_private_create(new_conv_id, user_id, character, preset)
                db.user_config_update(user_id, character, api, preset, new_conv_id)
                logger.info(f"新建私聊对话, user_id: {user_id}, conv_id: {new_conv_id}")
                db.user_info_update(user_id, 'conversations', 1, True)
                return f"新建对话成功，对话id:`{new_conv_id}`"
    except Exception as e:
        logger.error(f"新建私聊对话失败, user_id: {user_id}, 错误: {str(e)}")
        raise DatabaseError(f"新建私聊对话失败: {str(e)}")


async def group_new(group_info) -> int:
    """
    创建新的群聊对话。

    Args:
        update (Update): Telegram更新对象。
    """
    user_id = group_info['user_id']
    user_name = group_info['user_name']
    group_id = group_info['group_id']
    group_name = group_info['group_name']
    try:
        while True:
            new_conv_id = random.randint(10000000, 99999999)
            if db.conversation_group_check(new_conv_id):
                db.conversation_group_create(new_conv_id, user_id, user_name, group_id, group_name)
                logger.info(f"新建群聊对话, group_name: {group_name}, user_name: {user_name}, conv_id: {new_conv_id}")
                return new_conv_id
    except Exception as e:
        logger.error(f"新建群聊对话失败, group_id: {group_id}, 错误: {str(e)}")
        raise DatabaseError(f"新建群聊对话失败: {str(e)}")


async def group_delete(group_info) -> str:
    group_id = group_info['group_id']
    user_id = group_info['user_id']
    try:
        if db.conversation_group_delete(group_id, user_id):
            logger.info(f"删除群聊对话, group_id: {group_id}, user_id: {user_id}")
            return "您已重开对话"
        return "删除失败"
    except Exception as e:
        logger.error(f"删除群聊对话失败, group_id: {group_id}, 错误: {str(e)}")
        raise DatabaseError(f"删除群聊对话失败: {str(e)}")


async def private_save(config) -> str:
    try:

        if db.conversation_private_update(config['conv_id'], config['char'],
                                          config['preset']) and db.conversation_private_save(config['conv_id']):
            summary = await llm.generate_summary(config['conv_id'])
            print(f'总结:{summary}')
            if db.conversation_private_summary_add(config['conv_id'], summary):
                logger.info(f"保存对话并生成总结, conv_id: {config['conv_id']}, summary: {summary}")
                return f"保存成功，对话总结:`{summary}`"
        return "保存失败"
    except Exception as e:
        logger.error(f"保存对话失败, conv_id: {config['conv_id']}, 错误: {str(e)}")
        raise BotError(f"保存对话失败: {str(e)}")


async def dialog_add(user_id: int, conv_id: int, prompts: str, input_text: str, full_response: str,
                     cleared_response: str, msg_id: int) -> None:
    """
    记录响应相关的指标和对话内容到数据库 (异步)。
    Args:
        user_id (int): 用户 ID。
        conv_id (int): 对话 ID。
        prompts (str): 提示词。
        input_text (str): 用户输入文本。
        full_response (str): 完整响应内容。
        cleared_response (str): 处理后的响应内容。
        msg_id (int): 消息 ID。
    """
    try:
        response_token = llm.calculate_token_count(full_response)
        # Await the async get_current_input_token
        input_token = await llm.get_current_input_token(conv_id, 'private', prompts)
        logger.info(
            f"流式生成私聊回复完成, user_id: {user_id}, input_token:{input_token}, output_token: {response_token}")
        # Run database operations in a separate thread
        current_turn_order = await asyncio.to_thread(db.dialog_turn_get, conv_id, 'private')
        db.dialog_content_add(conv_id, 'user', current_turn_order + 1, input_text,
                              re.sub(r'<[^>]*>', '', input_text), msg_id, 'private')
        db.dialog_content_add(conv_id, 'assistant', current_turn_order + 2, full_response,
                              cleared_response, msg_id, 'private')
        db.user_info_update(user_id, 'input_tokens', input_token, True)
        db.user_info_update(user_id, 'output_tokens', response_token, True)
        db.user_info_update(user_id, 'dialog_turns', 2, True)
    except Exception as e:
        # Log database update errors specifically
        logger.error(f"数据库更新错误: {e}", exc_info=True)
        # Consider raising or handling the error further if needed


async def group_update(info, response, cleared_response, placeholder_message):
    conv_id = info['conv_id']
    input_text = info['message_text']
    message_id = info['message_id']
    group_id = info['group_id']
    current_turn_order = await asyncio.to_thread(db.dialog_turn_get, conv_id, 'group')

    await asyncio.to_thread(db.dialog_content_add, conv_id, 'user', current_turn_order + 1, input_text,
                            re.sub(r'<[^>]*>', '', input_text), message_id, 'group')
    await asyncio.to_thread(db.dialog_content_add, conv_id, 'assistant', current_turn_order + 2, response,
                            cleared_response, placeholder_message.message_id, 'group')
    await asyncio.to_thread(db.group_dialog_update, message_id, 'trigger_type', 'reply', group_id)
    await asyncio.to_thread(db.group_dialog_update, message_id, 'raw_response', response, group_id)
    await asyncio.to_thread(db.group_dialog_update, message_id, 'processed_response', cleared_response, group_id)
