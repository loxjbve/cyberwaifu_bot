"""处理主要输入是str，经由LLM处理的函数。"""
import logging
from typing import AsyncGenerator, Dict, Any, Tuple, List
import datetime 
from utils.config_utils import get_config, get_default_api
from agent.tools_handler import parse_and_invoke_tool
from utils.LLM_utils import LLM, llm_client_manager, PromptsBuilder
from utils.logging_utils import setup_logging
from utils import file_utils, LLM_utils
import utils.db_utils as db
import json
import re
setup_logging()
logger = logging.getLogger(__name__)


async def run_agent_session(
    user_input: str,
    prompt_text: str,
    character_prompt: str = "",
    bias_prompt: str = "",
    llm_api: str = 'gemini-2.5',
    max_iterations: int = 15,
    enable_memory: bool = False,
    session_id: str = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    运行一个多轮 Agent 会话，在每一步中通过 yield 返回状态更新。
    此函数处理与 LLM 和工具交互的核心逻辑，但不处理向用户发送消息。

    Args:
        user_input: 用户的初始输入。
        prompt_text: 用于系统提示的文本，包括工具定义。
        character_prompt: LLM 的角色提示。
        bias_prompt: LLM 的偏向提示。
        llm_api: 要使用的 LLM API。
        max_iterations: 最大迭代次数。
        enable_memory: 是否启用记忆功能。
        session_id: 会话ID，用于记忆管理。

    Yields:
        一个字典，表示 Agent 在每一步的状态。
        可能的状态: 'initializing', 'thinking', 'tool_call', 
                      'final_response', 'max_iterations_reached', 'error'。
    """
    try:
        yield {"status": "initializing", "message": "正在初始化 LLM 客户端..."}
        client = LLM(api=llm_api)

        # 读取记忆和经验库
        memory_context = ""
        experience_context = ""
        
        if enable_memory:
            # 读取记忆库
            try:
                with open("agent/docs/mem.json", 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        memories = json.loads(content)
                        # 清理过期记忆
                        current_time = datetime.datetime.now()
                        valid_memories = {}
                        for key, mem in memories.items():
                            try:
                                expires_at = datetime.datetime.fromisoformat(mem.get('expires_at', ''))
                                if current_time <= expires_at:
                                    valid_memories[key] = mem
                                    # 如果是当前会话，刷新过期时间
                                    if session_id and key == session_id:
                                        mem['expires_at'] = (current_time + datetime.timedelta(minutes=10)).isoformat()
                                        mem['last_updated'] = current_time.isoformat()
                            except (ValueError, TypeError):
                                continue
                        
                        # 保存清理后的记忆
                        if valid_memories != memories:
                            with open("agent/docs/mem.json", 'w', encoding='utf-8') as f:
                                json.dump(valid_memories, f, ensure_ascii=False, indent=2)
                        
                        # 获取10分钟内的记忆作为上下文
                        if valid_memories:
                            # 筛选10分钟内的记忆
                            recent_memories = []
                            ten_minutes_ago = current_time - datetime.timedelta(minutes=10)
                            
                            for mem_id, mem_data in valid_memories.items():
                                try:
                                    mem_timestamp = datetime.datetime.fromisoformat(mem_data.get('timestamp', ''))
                                    if mem_timestamp >= ten_minutes_ago:
                                        recent_memories.append((mem_id, mem_data))
                                except (ValueError, TypeError):
                                    continue
                            
                            # 按时间戳排序，最新的在前
                            recent_memories.sort(key=lambda x: x[1].get('timestamp', ''), reverse=True)
                            
                            if recent_memories:
                                memory_summaries = []
                                for mem_id, mem_data in recent_memories:
                                    summary = mem_data.get('summary', {})
                                    # 提取关键信息
                                    session_info = {
                                        "session_id": mem_id,
                                        "timestamp": mem_data.get('timestamp', ''),
                                        "user_request": summary.get('session_summary', {}).get('user_request', ''),
                                        "completed_tasks": summary.get('session_summary', {}).get('completed_tasks', []),
                                        "important_info": summary.get('cached_data', {}).get('important_info', []),
                                        "user_preferences": summary.get('cached_data', {}).get('user_preferences', {}),
                                        "pending_tasks": summary.get('cached_data', {}).get('pending_tasks', [])
                                    }
                                    memory_summaries.append(session_info)
                                
                                memory_context = f"\n\n=== 近期会话记忆（10分钟内） ===\n{json.dumps(memory_summaries, ensure_ascii=False, indent=2)}\n"
                                logger.info(f"已加载 {len(memory_summaries)} 条近期记忆（10分钟内）")
                            
                            # 如果当前会话ID存在，刷新其过期时间
                            if session_id and session_id in valid_memories:
                                valid_memories[session_id]['expires_at'] = (current_time + datetime.timedelta(minutes=10)).isoformat()
                                valid_memories[session_id]['last_updated'] = current_time.isoformat()
                                logger.info(f"已刷新当前会话记忆过期时间: {session_id}")
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.info(f"无法读取记忆库: {e}")
            
            # 读取经验库
            try:
                with open("agent/docs/exp.json", 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        experiences = json.loads(content)
                        if experiences:
                            # 只取最近的5条经验
                            recent_experiences = experiences[-5:] if len(experiences) > 5 else experiences
                            experience_context = f"\n\n=== 经验库 ===\n{json.dumps(recent_experiences, ensure_ascii=False, indent=2)}\n"
                            logger.info(f"已加载 {len(recent_experiences)} 条经验")
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.info(f"无法读取经验库: {e}")

        system_prompt = f"{prompt_text}\n\n{character_prompt}{bias_prompt}{memory_context}{experience_context}"
        current_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户输入: {user_input}"}
        ]

        iteration = 0
        while iteration < max_iterations:
            iteration += 1

            yield {"status": "thinking", "iteration": iteration}

            client.set_messages(current_messages)
            logger.debug(f"已设置 messages (当前会话): {current_messages}")

            ai_response = await client.final_response()
            logger.debug(f"LLM 原始响应: {ai_response}")

            llm_text_part, display_results, llm_feedback, had_tool_calls = await parse_and_invoke_tool(ai_response)

            if had_tool_calls:
                # 检查工具调用是否有错误
                has_tool_errors = any(
                    "error" in str(res.get('result', '')).lower() or 
                    "failed" in str(res.get('result', '')).lower() or
                    "exception" in str(res.get('result', '')).lower()
                    for res in llm_feedback
                )
                
                # 如果有工具调用，则 yield tool_call 状态并准备下一次迭代
                yield {
                    "status": "tool_call",
                    "iteration": iteration,
                    "llm_text": llm_text_part,
                    "tool_results": display_results,
                    "had_tool_calls": True,
                    "has_tool_errors": has_tool_errors,
                    "raw_ai_response": ai_response
                }
                
                # 如果检测到工具调用错误且启用记忆，进行失败模式分析
                if has_tool_errors and enable_memory:
                    try:
                        failure_result = await analyze_failure_patterns(current_messages + [{"role": "assistant", "content": ai_response}])
                        if failure_result.get("success") and failure_result.get("has_errors"):
                            logger.info("检测到工具调用错误，已分析并保存失败模式经验")
                    except Exception as analysis_e:
                        logger.error(f"工具调用错误分析过程中发生错误: {analysis_e}")
                
                # 为下一次迭代更新消息历史
                current_messages.append({"role": "assistant", "content": ai_response})
                feedback_content_to_llm = "工具调用结果:\n" + "\n".join(
                    [f"{res.get('tool_name', '未知工具')} 执行结果: {res.get('result', '')}" for res in llm_feedback]
                )
                current_messages.append({"role": "user", "content": feedback_content_to_llm})
                logger.debug("已将原始LLM响应和完整工具调用结果反馈给 LLM")
            else:
                # 如果没有工具调用，这被视为最终回复
                logger.debug(f"第{iteration}轮未调用工具，给出最终回复: {llm_text_part}")
                yield {"status": "final_response", "content": llm_text_part}
                
                # 会话正常结束，进行记忆总结
                if enable_memory:
                    logger.info(f"会话正常结束，开始记忆总结，session_id: {session_id}")
                    try:
                        # 添加最终的AI回复到消息历史中
                        final_messages = current_messages + [{"role": "assistant", "content": llm_text_part}]
                        memory_result = await summarize_memory(final_messages, session_id)
                        if memory_result.get("success"):
                            logger.info(f"记忆总结完成: {memory_result.get('session_id')}")
                        else:
                            logger.error(f"记忆总结失败: {memory_result.get('error')}")
                    except Exception as mem_e:
                        logger.error(f"记忆总结过程中发生错误: {mem_e}")
                else:
                    logger.debug("记忆功能未启用，跳过记忆总结")
                
                return

        # 如果循环结束，说明已达到最大迭代次数
        logger.warning(f"分析轮次已达上限 ({max_iterations})")
        yield {"status": "max_iterations_reached", "max_iterations": max_iterations}
        
        # 达到最大迭代次数，可能存在问题，进行失败模式分析
        if enable_memory:
            try:
                failure_result = await analyze_failure_patterns(current_messages)
                if failure_result.get("success") and failure_result.get("has_errors"):
                    logger.info("已分析并保存失败模式经验")
                
                # 同时进行记忆总结
                memory_result = await summarize_memory(current_messages, session_id)
                if memory_result.get("success"):
                    logger.info(f"记忆总结完成: {memory_result.get('session_id')}")
            except Exception as analysis_e:
                logger.error(f"失败模式分析过程中发生错误: {analysis_e}")

    except Exception as e:
        logger.error(f"处理 Agent 会话时发生错误: {str(e)}", exc_info=True)
        
        # 发生异常，进行失败模式分析
        if enable_memory:
            try:
                failure_result = await analyze_failure_patterns(current_messages)
                if failure_result.get("success") and failure_result.get("has_errors"):
                    logger.info("已分析并保存异常失败模式经验")
                
                # 同时进行记忆总结
                memory_result = await summarize_memory(current_messages, session_id)
                if memory_result.get("success"):
                    logger.info(f"异常情况下记忆总结完成: {memory_result.get('session_id')}")
            except Exception as analysis_e:
                logger.error(f"异常情况下失败模式分析过程中发生错误: {analysis_e}")
        
        yield {"status": "error", "message": str(e)}

async def analyze_image_for_rating(
    base64_data: str,
    mime_type: str,
    hard_mode: bool = False,
    parse_mode: str = "markdown",
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    分析图像的base64数据，并返回分析结果和消息历史。

    Args:
        base64_data (str): 图像的base64编码数据。
        mime_type (str): 图像的MIME类型。
        hard_mode (bool): 是否启用更激进的评价模式。
        parse_mode (str): 输出格式，可以是 'markdown' 或 'html'。

    Returns:
        Tuple[str, List[Dict[str, Any]]]: 包含格式化响应和发送给LLM的消息列表的元组。

    Raises:
        ValueError: 如果缺少必要的 prompt 或数据。
    """


    prompt_name = "fuck_or_not_group" if parse_mode == "html" else "fuck_or_not"
    system_prompt = file_utils.load_single_prompt(prompt_name)
    if not system_prompt:
        raise ValueError(f"无法加载 '{prompt_name}' prompt。")

    if hard_mode:
        hard_supplement = file_utils.load_single_prompt("fuck_or_not_hard_mode_supplement")
        if hard_supplement:
            system_prompt += hard_supplement

    user_text = "兄弟看看这个，你想不想操？"
    if hard_mode:
        user_text += "（请使用最极端和粗俗的语言进行评价）"

    llm_messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_data}"},
                },
            ],
        },
    ]

    fuck_api = get_config("fuck_or_not_api", "gemini-2.5")
    llm = LLM_utils.LLM(api=fuck_api)
    llm.set_messages(llm_messages)
    response = await llm.final_response()

    try:
        match = re.search(r"```json\n(.*?)\n```", response, re.DOTALL)
        json_str = match.group(1) if match else response
        data = json.loads(json_str)

        if parse_mode == "html":
            score = data.get("score", "N/A")
            reason_short = data.get("reason_short", "N/A")
            reason_detail = data.get("reason_detail", "N/A")
            fantasy_short = data.get("fantasy_short", "N/A")
            fantasy_detail = data.get("fantasy_detail", "N/A")
            formatted_response = (
                " <b>分析结果</b> \n\n"
                f"<b>评分</b>: {score}/10\n\n"
                f"<b>理由</b>: {reason_short}\n"
                f"<blockquote expandable>{reason_detail}</blockquote>\n\n"
                f"<b>评价</b>: {fantasy_short}\n"
                f"<blockquote expandable>{fantasy_detail}</blockquote>"
            )
        else:  # markdown
            score = data.get("score", "N/A")
            reason = data.get("reason", "N/A")
            fantasy = data.get("fantasy", "N/A")
            formatted_response = f"```\n分数：{score}\n```\n\n理由：{reason}\n\n评价：{fantasy}"
        
        return formatted_response, llm_messages
        
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"解析LLM JSON响应失败: {e}。将使用原始响应。")
        return response, llm_messages


async def analyze_image_for_kao(
    base64_data: str,
    mime_type: str,
    parse_mode: str = "markdown",
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    分析图像的base64数据，并返回颜值分析结果和消息历史。

    Args:
        base64_data (str): 图像的base64编码数据。
        mime_type (str): 图像的MIME类型。
        parse_mode (str): 输出格式，可以是 'markdown' 或 'html'。

    Returns:
        Tuple[str, List[Dict[str, Any]]]: 包含格式化响应和发送给LLM的消息列表的元组。

    Raises:
        ValueError: 如果缺少必要的 prompt 或数据。
    """
    prompt_name = "kao_group"
    system_prompt = file_utils.load_single_prompt(prompt_name)
    if not system_prompt:
        raise ValueError(f"无法加载 '{prompt_name}' prompt。")

    user_text = "请帮我分析一下这张图片的颜值。"

    llm_messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_data}"},
                },
            ],
        },
    ]

    kao_api = get_config("fuck_or_not_api", "gemini-2.5") # We can reuse the same API for now
    llm = LLM_utils.LLM(api=kao_api)
    llm.set_messages(llm_messages)
    response = await llm.final_response()

    try:
        match = re.search(r"```json\n(.*?)\n```", response, re.DOTALL)
        json_str = match.group(1) if match else response
        data = json.loads(json_str)

        if parse_mode == "html":
            score = data.get("score", "N/A")
            age = data.get("age", "N/A")
            gender = data.get("gender", "N/A")
            face_shape = data.get("face_shape", "N/A")
            expression = data.get("expression", "N/A")
            skin_color = data.get("skin_color", "N/A")
            evaluation = data.get("evaluation", "N/A")
            
            formatted_response = (
                " <b>颜值分析结果</b> \n\n"
                f"<b>总分</b>: {score}/10\n"
                f"<b>年龄</b>: {age}\n"
                f"<b>性别</b>: {gender}\n"
                f"<b>脸型</b>: {face_shape}\n"
                f"<b>表情</b>: {expression}\n"
                f"<b>肤色</b>: {skin_color}\n\n"
                f"<b>评价</b>:\n<blockquote expandable>{evaluation}</blockquote>"
            )
        else:  # markdown
            score = data.get("score", "N/A")
            age = data.get("age", "N/A")
            gender = data.get("gender", "N/A")
            face_shape = data.get("face_shape", "N/A")
            expression = data.get("expression", "N/A")
            skin_color = data.get("skin_color", "N/A")
            evaluation = data.get("evaluation", "N/A")
            formatted_response = f"```\n总分：{score}/10\n年龄：{age}\n性别：{gender}\n脸型：{face_shape}\n表情：{expression}\n肤色：{skin_color}\n```\n\n评价：{evaluation}"
        
        return formatted_response, llm_messages
        
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"解析LLM JSON响应失败: {e}。将使用原始响应。")
        return response, llm_messages


async def generate_summary(conversation_id: int,summary_type:str = 'save',start:int=0,end:int=0) -> str:
        """
        生成对话总结

        Args:
            conversation_id: 对话ID
            summary_type: 总结类型，save:保存总结，zip:压缩总结
            start: 开始位置
            end: 结束位置

        Returns:
            str: 生成的总结文本

        Raises:
            ValueError: 总结生成失败时抛出
        """
        async with llm_client_manager.semaphore:
            try:
                # 构建对话历史
                client = LLM("gemini-2", "private")

                if summary_type == 'save':
                    turns = db.dialog_turn_get(conversation_id, 'private')
                    start = turns - 70 if turns > 70 else 0
                    messages = PromptsBuilder.build_conv_messages_for_summary(conversation_id, "private", start, turns)
                    user_prompt = file_utils.load_single_prompt("summary_save_user_prompt")
                    if not user_prompt:
                        raise ValueError("无法加载 'summary_save_user_prompt' prompt。")
                    messages.append({"role": "user", "content": user_prompt})
                    client.set_messages(messages)
                elif summary_type == 'zip':
                    messages = PromptsBuilder.build_conv_messages_for_summary(conversation_id, "private", start, end)
                    logger.debug(f"总结文本内容：\r\n{messages}")
                    user_prompt = file_utils.load_single_prompt("summary_zip_user_prompt")
                    if not user_prompt:
                        raise ValueError("无法加载 'summary_zip_user_prompt' prompt。")
                    messages.append({"role": "user", "content": user_prompt})
                    client.set_messages(messages)
                return await client.final_response()

            except Exception as e:
                raise ValueError(f"生成总结失败: {str(e)}")

async def generate_char(character_description: str,nsfw:bool=True) -> str:
        """
        根据用户输入生成角色描述文档

        Args:
            character_description: 用户提供的角色描述文本
            nsfw: 是否生成NSFW内容，默认为True

        Returns:
            str: 生成的JSON格式角色描述文档

        Raises:
            ValueError: 角色生成失败时抛出
        """
        async with llm_client_manager.semaphore:
            try:
                # 根据nsfw参数选择对应的prompt
                prompt_key = "generate_char_prompt" if nsfw else "generate_char_prompt_sfw"
                system_prompt = file_utils.load_single_prompt(prompt_key)
                if not system_prompt:
                    raise ValueError(f"无法加载 '{prompt_key}' prompt。")

                # 构建对话历史
                history = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": character_description},
                ]
                client = LLM(get_default_api(), "private")
                client.set_messages(history)
                client.set_default_client()
                result = await client.final_response()
                logger.debug(f"LLM输出角色\r\n{result}\r\n")
                return result

            except Exception as e:
                raise ValueError(f"生成角色失败: {str(e)}")

async def generate_user_profile(group_id: int) -> str:

    """
    分析群组聊天记录，为最活跃的用户生成JSON格式的画像。

    Args:
        group_id: 目标群组的ID。

    Returns:
        str: 一个包含用户画像分析结果的JSON字符串。
             如果找不到聊天记录或发生错误，则返回错误信息的字符串。
    """
    try:
        # 1. 获取最近800条群聊数据
        command = """
            SELECT msg_text, msg_user_name, processed_response, create_at, msg_user
            FROM (SELECT msg_text, msg_user_name, processed_response, create_at, msg_user, msg_id
                  FROM group_dialogs
                  WHERE group_id = ? AND msg_user IS NOT NULL
                  ORDER BY msg_id DESC
                  LIMIT 800) sub
            ORDER BY msg_id ASC
        """
        dialogs_with_user_id = db.query_db(command, (group_id,))

        if not dialogs_with_user_id:
             return json.dumps({"error": f"无法找到群组 {group_id} 的聊天记录，或记录为空。"}, ensure_ascii=False)

        formatted_dialogs = "\n".join(
            [
                f"用户ID {row[4]} (昵称: {row[1]}) 在 {row[3]} 说: {row[0]}" + (f" -> Bot回应: {row[2]}" if row[2] else "")
                for row in dialogs_with_user_id
            ]
        )

        # 3. 构建 Prompt
        system_prompt = file_utils.load_single_prompt("generate_user_profile_system", "prompts/features_prompts.json")
        user_prompt_template = file_utils.load_single_prompt("generate_user_profile_user", "prompts/features_prompts.json")

        if not system_prompt or not user_prompt_template:
            raise ValueError("无法从 features_prompts.json 加载用户画像生成所需的Prompt。")
            
        final_user_prompt = user_prompt_template.format(dialog_content=formatted_dialogs)

        # 4. 调用 LLM
        client = LLM(api=get_config("analysis.default_api", "gemini-2.5"))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": final_user_prompt},
        ]
        client.set_messages(messages)
        
        logger.info(f"正在为群组 {group_id} 生成用户画像...")
        response_data_str = await client.final_response()

        instruction_to_agent = (
            "已成功生成用户画像的JSON。请解析下面的 `raw_response` 字段（它是一个JSON字符串），"
            "提取每位用户的信息，并将这些信息更新到 `user_profiles` 数据库表中。"
            "对于每个用户，请先查询数据库确认是否存在旧画像。如果存在，"
            "请结合旧内容和新内容作为参考进行更新；如果不存在，请直接插入新画像。"
            "为了防止单次操作过大，一次调用工具最多处理2-3人的信息。"
            "对于每个用户的'recent_activities'字段，需要把日期加进去，保留5天的结果。如果超过5天，则去掉最早的结果。"
            f"现在的时间是 {str(datetime.datetime.now())}，请确保使用当前时间戳更新 `last_updated` 字段。"
        )
        
        return json.dumps({
            "raw_response": response_data_str,
            "instruction": instruction_to_agent
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"为群组 {group_id} 生成用户画像时发生错误: {e}", exc_info=True)
        return json.dumps({"error": "An internal error occurred while generating user profiles."}, ensure_ascii=False, indent=2)

async def analyze_database(sql: str, prompts: str) -> str:
    """
    分析数据库参数，接受sql语句和prompts，将sql语句查询到的数据，拼接prompts内容发送给llm获取返回

    Args:
        sql (str): The SQL query to execute.
        prompts (str): The prompts to be sent to the LLM.

    Returns:
        str: The response from the LLM.
    """
    try:
        # 1. 执行SQL查询
        query_result = db.query_db(sql)

        # 2. 格式化查询结果
        if not query_result:
            formatted_result = "查询未返回任何结果。"
        else:
            # 将结果转换为更易读的格式，例如JSON或格式化字符串
            formatted_result = json.dumps(query_result, ensure_ascii=False, indent=2)

        # 3. 构建发送给LLM的最终提示
        final_prompt = f"根据以下数据:\n\n{formatted_result}\n\n请回答以下问题:\n{prompts}"

        # 4. 调用LLM
        client = LLM(api=get_config("analysis.default_api", "gemini-2.5"))
        messages = [
            {"role": "user", "content": final_prompt},
        ]
        client.set_messages(messages)
        
        logger.info("正在分析数据库...")
        response_data_str = await client.final_response()

        return response_data_str

    except Exception as e:
        logger.error(f"分析数据库时发生错误: {e}", exc_info=True)
        return json.dumps({"error": "分析数据库时发生内部错误。"}, ensure_ascii=False, indent=2)


async def analyze_failure_patterns(conversation_messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    失败模式总结函数
    
    Args:
        conversation_messages: 完整对话列表
    
    Returns:
        Dict[str, Any]: 包含成功/失败状态和失败原因的字典
    """
    try:
        # 读取现有的经验数据
        exp_file_path = "agent/docs/exp.json"
        existing_experiences = []
        
        try:
            with open(exp_file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    existing_experiences = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("exp.json文件不存在或为空，将创建新的经验库")
            existing_experiences = []
        
        # 构建分析提示词
        system_prompt = """
你是一个专业的AI助手经验总结专家。请分析以下对话，提取简洁的执行经验。

请重点关注：
1. 任务类型和执行顺序
2. 关键函数的正确调用方法
3. 需要注意的事项

请以JSON格式返回简洁的经验：
{
  "has_experience": true/false,
  "experiences": [
    {
      "task_type": "任务类型",
      "execution_order": "执行顺序说明",
      "key_points": "关键注意事项",
      "function_usage": "重要函数调用方法"
    }
  ]
}
        """
        
        # 格式化对话历史
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {str(msg.get('content', ''))[:500]}..."
            for msg in conversation_messages
        ])
        
        # 添加现有经验作为参考
        existing_exp_text = "\n\n现有经验库：\n" + json.dumps(existing_experiences, ensure_ascii=False, indent=2) if existing_experiences else ""
        
        user_prompt = f"请分析以下对话中的工具调用错误：\n\n{conversation_text}{existing_exp_text}"
        
        # 调用LLM进行分析
        client = LLM(api=get_config("analysis.default_api", "gemini-2.5"))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        client.set_messages(messages)
        
        logger.info("正在分析失败模式...")
        response = await client.final_response()
        
        # 解析LLM响应
        try:
            # 尝试提取JSON
            match = re.search(r"```json\n(.*?)\n```", response, re.DOTALL)
            if match:
                analysis_result = json.loads(match.group(1))
            else:
                analysis_result = json.loads(response)
            
            # 如果提取到了经验，将新经验添加到经验库
            if analysis_result.get("has_experience", False):
                for exp in analysis_result.get("experiences", []):
                    new_experience = {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "task_type": exp.get("task_type", ""),
                        "execution_order": exp.get("execution_order", ""),
                        "key_points": exp.get("key_points", ""),
                        "function_usage": exp.get("function_usage", "")
                    }
                    existing_experiences.append(new_experience)
                
                # 保持经验库大小合理（最多保留50条）
                if len(existing_experiences) > 50:
                    existing_experiences = existing_experiences[-50:]
                
                # 保存更新后的经验库
                with open(exp_file_path, 'w', encoding='utf-8') as f:
                    json.dump(existing_experiences, f, ensure_ascii=False, indent=2)
                
                logger.info(f"已保存新的失败经验到 {exp_file_path}")
            
            return {
                "success": True,
                "has_experience": analysis_result.get("has_experience", False),
                "experiences_count": len(analysis_result.get("experiences", []))
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"解析LLM分析结果失败: {e}")
            return {
                "success": False,
                "error": f"解析分析结果失败: {str(e)}"
            }
    
    except Exception as e:
        logger.error(f"分析失败模式时发生错误: {e}", exc_info=True)
        return {
             "success": False,
             "error": f"分析失败: {str(e)}"
         }


async def summarize_memory(conversation_messages: List[Dict[str, Any]], session_id: str = None) -> Dict[str, Any]:
    """
    记忆总结函数
    
    Args:
        conversation_messages: 完整对话列表
        session_id: 会话ID，用于标识不同的会话
    
    Returns:
        Dict[str, Any]: 包含成功/失败状态和失败原因的字典
    """
    try:
        # 读取现有的记忆数据
        mem_file_path = "agent/docs/mem.json"
        existing_memories = {}
        
        try:
            with open(mem_file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    existing_memories = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("mem.json文件不存在或为空，将创建新的记忆库")
            existing_memories = {}
        
        # 构建记忆总结提示词
        system_prompt = """
你是一个专业的AI助手记忆管理专家。请对这一轮agent工作进行总结，重点关注：

1. 用户的核心需求是什么
2. AI助手完成了哪些任务
3. 哪些信息和数据可能在后续对话中有用
4. 用户的偏好和习惯
5. 未完成的任务或需要跟进的事项

请以JSON格式返回总结结果：
{
  "session_summary": {
    "user_request": "用户的主要需求",
    "completed_tasks": ["已完成的任务列表"],
    "ai_achievements": "AI助手的主要成就",
    "user_satisfaction": "用户满意度评估"
  },
  "cached_data": {
    "important_info": ["重要信息列表"],
    "user_preferences": {"偏好类型": "偏好内容"},
    "context_data": {"上下文键": "上下文值"},
    "pending_tasks": ["待完成任务"]
  },
  "insights": {
    "user_behavior": "用户行为分析",
    "interaction_patterns": "交互模式",
    "improvement_areas": ["可改进领域"]
  }
}
        """
        
        # 格式化对话历史
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {str(msg.get('content', ''))[:800]}..."
            for msg in conversation_messages
        ])
        
        # 添加现有记忆作为参考
        existing_mem_text = ""
        if session_id and session_id in existing_memories:
            existing_mem_text = "\n\n现有会话记忆：\n" + json.dumps(
                existing_memories[session_id], ensure_ascii=False, indent=2
            )
        
        user_prompt = f"请总结以下对话中的agent工作：\n\n{conversation_text}{existing_mem_text}"
        
        # 调用LLM进行总结
        client = LLM(api=get_config("analysis.default_api", "gemini-2.5"))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        client.set_messages(messages)
        
        logger.info("正在生成记忆总结...")
        response = await client.final_response()
        
        # 解析LLM响应
        try:
            # 尝试提取JSON
            match = re.search(r"```json\n(.*?)\n```", response, re.DOTALL)
            if match:
                memory_result = json.loads(match.group(1))
            else:
                memory_result = json.loads(response)
            
            # 准备保存的记忆数据
            session_key = session_id or f"session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            memory_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "last_updated": datetime.datetime.now().isoformat(),
                "expires_at": (datetime.datetime.now() + datetime.timedelta(minutes=10)).isoformat(),
                "summary": memory_result,
                "conversation_length": len(conversation_messages)
            }
            
            # 更新记忆库
            existing_memories[session_key] = memory_entry
            
            # 清理过期的记忆（超过10分钟）
            current_time = datetime.datetime.now()
            expired_sessions = []
            for key, mem in existing_memories.items():
                try:
                    expires_at = datetime.datetime.fromisoformat(mem.get('expires_at', ''))
                    if current_time > expires_at:
                        expired_sessions.append(key)
                except (ValueError, TypeError):
                    # 如果时间格式有问题，也标记为过期
                    expired_sessions.append(key)
            
            for expired_key in expired_sessions:
                del existing_memories[expired_key]
                logger.info(f"已清理过期记忆: {expired_key}")
            
            # 保存更新后的记忆库
            with open(mem_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_memories, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存会话记忆到 {mem_file_path}, 会话ID: {session_key}")
            
            return {
                "success": True,
                "session_id": session_key,
                "memory_summary": memory_result,
                "expires_at": memory_entry["expires_at"]
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"解析LLM记忆总结结果失败: {e}")
            return {
                "success": False,
                "error": f"解析记忆总结结果失败: {str(e)}"
            }
    
    except Exception as e:
        logger.error(f"生成记忆总结时发生错误: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"记忆总结失败: {str(e)}"
        }
