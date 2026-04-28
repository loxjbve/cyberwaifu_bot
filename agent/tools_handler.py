"""
用于构建需要LLM参与的函数，输入的主要内容是字符串，由LLM处理后直接操作db或os，并返回结果
"""
import asyncio
import json
import re

from agent.tools_registry import get_tool_spec, logger, tool_executor


class ToolHandler:
    """
    处理来自LLM的响应，解析并执行其中包含的工具调用。

    该类封装了从原始文本中提取JSON、解析工具调用、执行工具以及处理结果和错误的完整逻辑。

    Attributes:
        ai_response (str): 来自LLM的原始响应字符串。
        llm_text_output (str): 从响应中分离出的纯文本部分。
        tool_results_for_llm (list): 工具执行结果的列表，用于反馈给LLM。
        had_tool_calls (bool): 标记是否成功解析并调用了任何工具。
    """

    def __init__(self, ai_response: str):
        """
        初始化ToolHandler。

        Args:
            ai_response (str): 来自LLM的原始响应。
        """
        self.ai_response = ai_response
        self.llm_text_output = ai_response.strip()
        self.tool_results_for_llm = []
        self.had_tool_calls = False

    def _attempt_json_repair(self, s: str) -> str | None:
        """
        尝试修复一个可能不完整或格式错误的JSON字符串。
        """
        try:
            # 简单的修复：确保括号和引号闭合
            s = s.strip()
            if not s.startswith('{'):
                s = '{' + s
            if not s.endswith('}'):
                s = s + '}'
            
            # 尝试替换单引号为双引号
            s = s.replace("'", '"')

            # 移除尾随逗号
            s = re.sub(r',\s*([\}\]])', r'\1', s)

            json.loads(s)
            return s
        except json.JSONDecodeError:
            return None

    def _extract_json(self) -> tuple[str | None, str]:
        """
        从AI响应中稳健地提取JSON内容。

        它会尝试多种策略来查找和解析JSON：
        1.  从Markdown代码块中提取。
        2.  查找响应中所有可能的JSON对象（包括不完整的）。
        3.  尝试将整个响应作为JSON解析。
        4.  对找到的潜在JSON字符串进行修复。

        在所有成功解析的JSON中，选择最长（信息量最大）的一个作为最终结果。

        Returns:
            tuple[str | None, str]: 一个元组，包含最佳的JSON字符串（如果找到）和响应中剩余的文本部分。
        """
        candidates = []

        # 策略 1: 从Markdown代码块中提取
        for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", self.ai_response):
            content = match.group(1).strip()
            try:
                json.loads(content)
                candidates.append((content, match.group(0)))
                logger.debug(f"从Markdown块中找到有效JSON候选: {content[:100]}...")
            except json.JSONDecodeError:
                repaired = self._attempt_json_repair(content)
                if repaired:
                    candidates.append((repaired, match.group(0)))
                    logger.debug(f"从Markdown块中修复并找到有效JSON候选: {repaired[:100]}...")

        # 策略 2: 查找所有独立的JSON对象
        # 这个正则表达式可以找到以'{'开头、以'}'结尾的平衡括号结构
        for match in re.finditer(r"\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}", self.ai_response):
            content = match.group(0).strip()
            try:
                json.loads(content)
                candidates.append((content, match.group(0)))
                logger.debug(f"从文本中找到有效JSON候选: {content[:100]}...")
            except json.JSONDecodeError:
                # 即使独立对象解析失败，也通常不进行修复，因为可能只是文本的一部分
                pass

        # 策略 3: 尝试将整个响应作为JSON
        try:
            json.loads(self.ai_response)
            candidates.append((self.ai_response, self.ai_response))
            logger.debug("整个响应是一个有效的JSON候选。")
        except json.JSONDecodeError:
            repaired = self._attempt_json_repair(self.ai_response)
            if repaired:
                candidates.append((repaired, self.ai_response))
                logger.debug(f"修复了整个响应并找到有效JSON候选: {repaired[:100]}...")

        if not candidates:
            logger.debug("在所有策略中均未找到有效的JSON内容。")
            return None, self.ai_response

        # 选择最长的有效JSON作为最佳候选
        best_json, source_text = max(candidates, key=lambda item: len(item[0]))
        
        remaining_text = self.ai_response.replace(source_text, "").strip()
        logger.debug(f"最终选择的JSON内容 (长度 {len(best_json)}), 剩余文本: '{remaining_text}'")
        
        return best_json, remaining_text

    async def _invoke_tool(self, tool_call: dict) -> dict:
        """
        执行单个工具调用。

        Args:
            tool_call (dict): 包含'tool_name'和'parameters'的字典。

        Returns:
            dict: 包含工具名称、参数以及包含 'display' 和 'llm_feedback' 的结果字典。
        """
        tool_name = tool_call.get("tool_name")
        parameters = tool_call.get("parameters", {})
        logger.info(f"准备执行工具: {tool_name}，参数: {parameters}")

        result_payload = {"display": f"工具 '{tool_name}' 未能执行。", "llm_feedback": f"Tool '{tool_name}' failed."}

        if not isinstance(tool_name, str):
            error_msg = f"工具名称无效或缺失: {tool_name}"
            logger.error(error_msg)
            result_payload = {"display": error_msg, "llm_feedback": error_msg}
            return {"tool_name": "unknown", "parameters": parameters, "result": result_payload}

        tool_spec = get_tool_spec(tool_name)
        tool_func = tool_executor.get_callable(tool_name)
        if not tool_func or not tool_spec:
            error_msg = f"未找到工具: {tool_name}"
            logger.warning(error_msg)
            result_payload = {"display": error_msg, "llm_feedback": error_msg}
            return {"tool_name": tool_name, "parameters": parameters, "result": result_payload}

        try:
            import inspect
            sig = inspect.signature(tool_func)
            allowed_params = set(tool_spec.parameters.keys())
            filtered_params = {
                k: v
                for k, v in parameters.items()
                if k in sig.parameters and k in allowed_params
            }

            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**filtered_params)
            else:
                result = tool_func(**filtered_params)
            
            # 确保返回的是我们期望的字典格式
            if isinstance(result, dict) and "display" in result and "llm_feedback" in result:
                result_payload = result
            else:
                # 如果工具没有按新格式返回，进行兼容处理
                logger.warning(f"工具 {tool_name} 返回了旧格式的结果。将进行兼容转换。")
                result_payload = {"display": str(result), "llm_feedback": str(result)}

            logger.debug(f"工具 {tool_name} 执行成功: {result_payload['llm_feedback']}")
            return {"tool_name": tool_name, "parameters": parameters, "result": result_payload}
        except Exception as e:
            error_msg = f"工具 {tool_name} 执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result_payload = {"display": error_msg, "llm_feedback": error_msg}
            return {"tool_name": tool_name, "parameters": parameters, "result": result_payload}

    def _handle_parsing_error(self, json_content: str, error: json.JSONDecodeError) -> tuple[str, list, list, bool]:
        """
        处理JSON解析失败的情况，根据内容决定是反馈错误给LLM还是当作纯文本。
        """
        # 检查是否存在工具调用的强信号
        if '"tool_calls"' in json_content or '"tool_name"' in json_content:
            error_message = (
                "Your tool call was not successful because the JSON format was invalid. "
                f"I received the following content which I could not parse: '{json_content[:200]}...'. "
                f"Error details: {error}. "
                "Please ensure your response contains only a single, valid JSON object with the correct syntax, including all necessary brackets and commas."
            )
            logger.warning(f"检测到格式错误的工具调用尝试: {json_content}")
            # 格式化为LLM反馈的格式
            llm_feedback = [{"tool_name": "error_handler", "result": error_message}]
            # 格式化为用户展示的格式
            display_results = [{"tool_name": "JSON Parser", "parameters": {"content": json_content}, "result": f"Failed to parse tool call: {error}"}]
            # 将无法解析的内容也放入文本输出，以防万一
            self.llm_text_output = (self.llm_text_output + "\n" + json_content).strip()
            return self.llm_text_output, display_results, llm_feedback, True # had_tool_calls is True because an attempt was made
        else:
            # 如果没有工具调用的信号，则当作纯文本
            logger.info(f"无法解析JSON，且未检测到工具调用关键字。将其视为纯文本。内容: '{json_content}'")
            self.llm_text_output = (self.llm_text_output + "\n" + json_content).strip()
            return self.llm_text_output, [], [], False

    async def handle_response(self) -> tuple[str, list, list, bool]:
        """
        解析并处理LLM的响应，执行任何工具调用。

        这是该类的主要入口点。它协调JSON提取、工具调用和结果聚合。

        Returns:
            tuple[str, list, list, bool]:
                - llm_text_output (str): LLM响应的文本部分。
                - display_results (list): 包含每个工具调用详细结果的字典列表，用于用户展示。
                - llm_feedback (list): 工具调用的简洁结果列表，用于反馈给LLM。
                - had_tool_calls (bool): 如果成功解析并调用了任何工具，则为True。
        """
        json_content, self.llm_text_output = self._extract_json()

        if not json_content:
            return self.llm_text_output, [], [], False

        try:
            response_data = json.loads(json_content)
        except json.JSONDecodeError as e:
            return self._handle_parsing_error(json_content, e)

        tool_calls = response_data.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            tool_calls = []

        if not tool_calls and "tool_name" in response_data:
            tool_calls = [{"tool_name": response_data["tool_name"], "parameters": response_data.get("parameters", {})}]

        if not tool_calls:
            # 如果在提取JSON后，解析出的数据中没有工具调用，
            # 那么我们将提取出的JSON内容视为普通文本，并将其附加到剩余文本中。
            # 这可以处理LLM返回不符合工具调用格式的JSON的情况。
            if json_content:
                self.llm_text_output = (self.llm_text_output + "\n" + json_content).strip()
            return self.llm_text_output, [], [], False

        self.had_tool_calls = True
        tasks = [self._invoke_tool(call) for call in tool_calls]
        execution_results = await asyncio.gather(*tasks)

        display_results = []
        llm_feedback = []

        for res in execution_results:
            tool_name = res.get("tool_name", "unknown")
            parameters = res.get("parameters", {})
            result_payload = res.get("result", {"display": "No result", "llm_feedback": "No result"})
            
            # 构建用于用户展示的详细结果字典
            display_results.append({
                "tool_name": tool_name,
                "parameters": parameters,
                "result": result_payload.get('display', 'N/A')
            })

            # 构建用于LLM反馈的简洁结果字典
            llm_feedback.append({
                "tool_name": tool_name,
                "result": result_payload.get('llm_feedback', 'N/A')
            })
        
        return self.llm_text_output, display_results, llm_feedback, self.had_tool_calls


async def parse_and_invoke_tool(ai_response: str) -> tuple[str, list, list, bool]:
    """
    解析AI响应并根据需要调用工具。

    此函数作为 ToolHandler 类的便捷包装器。它会实例化处理器，执行响应处理，并返回结果。
    此函数提取响应中的JSON内容（忽略周围的文本）并处理工具调用。

    Args:
        ai_response (str): 来自LLM的原始响应。

    Returns:
        tuple[str, list, list, bool]:
            - llm_text_output (str): LLM响应的文本部分。
            - display_results (list): 包含每个工具调用详细结果的字典列表，用于用户展示。
            - llm_feedback (list): 工具调用的简洁结果列表，用于反馈给LLM。
            - had_tool_calls (bool): 如果成功解析并调用了任何工具，则为True。
    """
    handler = ToolHandler(ai_response)
    return await handler.handle_response()
