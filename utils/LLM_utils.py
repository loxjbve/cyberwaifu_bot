import asyncio
import base64
import json
import logging
import time
from typing import Dict, Optional, Tuple

import httpx
import openai
import tiktoken

# 避免循环导入
import utils.db_utils as db
import utils.file_utils as file
import utils.text_utils as txt
from utils.config_utils import get_api_config, get_config, get_default_api
from utils.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class LLMClientManager:
    """
    LLM客户端管理器，采用单例模式管理多个LLM客户端连接

    特性:
    - 线程安全的客户端创建和获取
    - 并发控制(最大并发数为3)
    - 客户端连接池管理
    """

    _instance = None
    _clients: Dict[Tuple[str, str, str], openai.AsyncOpenAI] = (
        {}
    )  # 客户端连接池，键为(api_key, base_url, model)
    _semaphore: asyncio.Semaphore = asyncio.Semaphore(
        get_config("api.semaphore_limit", 5)
    )  # 并发控制信号量
    _lock = asyncio.Lock()  # 客户端操作锁

    def __new__(cls):
        """
        实现单例模式，确保只有一个LLMClientManager实例。
        """
        if cls._instance is None:
            cls._instance = super(LLMClientManager, cls).__new__(cls)
        return cls._instance

    async def get_client(
        self, api_key: str, base_url: str, model: str
    ) -> openai.AsyncOpenAI:
        """
        获取或创建LLM客户端

        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称

        Returns:
            openai.AsyncOpenAI: 配置好的异步客户端

        Raises:
            ValueError: 客户端初始化失败时抛出
        """
        async with self._lock:
            client_key = (api_key, base_url, model)
            if client_key not in self._clients:
                try:
                    http_client = httpx.AsyncClient()
                    self._clients[client_key] = openai.AsyncOpenAI(
                        api_key=api_key, base_url=base_url, http_client=http_client
                    )
                except Exception as e:
                    raise ValueError(f"客户端初始化失败: {str(e)}")
            return self._clients[client_key]

    async def close_all_clients(self):
        """
        关闭所有已创建的LLM客户端连接并清空连接池。
        """
        async with self._lock:
            for client in self._clients.values():
                await client.close()
            self._clients.clear()

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """
        获取用于控制并发请求的信号量。
        
        Returns:
            asyncio.Semaphore: 并发信号量。
        """
        return self._semaphore


# 全局客户端管理器实例
llm_client_manager = LLMClientManager()


class LLM:
    """
    LLM类用于处理与大型语言模型（LLM）的交互，包括构建消息、发送请求和处理响应。
    """
    def __init__(self, api: Optional[str] = None, chat_type="private"):
        """
        初始化LLM实例。

        Args:
            api (str): API名称，默认为DEFAULT_API。
            chat_type (str): 聊天类型，'private' 或 'group'。
        """
        api_name = api or get_default_api()
        self.key, self.base_url, self.model = get_api_config(api_name)
        self.client = None
        self.messages = []
        self.chat_type = chat_type
        self.conv_id = 0
        self.prompts = None

    async def embedd_image(self, images: list, context, text_content: str = ""):
        """
        将图片嵌入到最新的消息中

        Args:
            images (list): 图片列表
            context: Telegram上下文对象
            text_content (str, optional): 要附加的文本内容。默认为空字符串
        """
        logger.info(f"含有图片，尝试嵌入")
        content_list = []
        if text_content:
            content_list.append({"type": "text", "text": text_content})

        for img in images:
            base64_img = await txt.convert_file_id_to_base64(img, context)
            if base64_img:
                logger.info(f"图片 {img} 嵌入成功")
                content_list.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{base64_img['mime_type']};base64,{base64_img['data']}"
                        },
                    }
                )
            else:
                logger.warning(f"图片 {img} 嵌入失败")

        if content_list:
            self.messages.append({"role": "user", "content": content_list})
            logger.info(f"图片嵌入完成，共处理 {len(images)} 张图片，成功 {len(content_list) - (1 if text_content else 0)} 张")
        else:
            logger.warning("图片嵌入失败，所有图片处理均失败")

    def set_messages(self, messages):
        """
        设置LLM实例的消息列表。

        Args:
            messages (list): 消息列表。
        """
        self.messages = messages

    def set_default_client(self):
        """
        将LLM实例的API配置重置为默认API。
        """
        self.key, self.base_url, self.model = get_api_config(get_default_api())

    async def response(self, stream: bool = False):
        """
        向LLM发送请求并获取响应。

        Args:
            stream (bool): 是否以流式方式获取响应。默认为False。

        Yields:
            str: 响应内容。

        Raises:
            RuntimeError: API调用失败时抛出。
        """
        self.client = await llm_client_manager.get_client(
            self.key, self.base_url, self.model
        )
        async with llm_client_manager.semaphore:
            try:
                if stream:
                    response_stream = await self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        max_tokens=get_config("api.max_tokens", 8000),
                        stream=True,
                    )
                    async for chunk in response_stream:
                        if (
                            chunk.choices
                            and chunk.choices[0].delta
                            and chunk.choices[0].delta.content
                        ):
                            yield chunk.choices[0].delta.content
                else:
                    response_completion = await self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        max_tokens=get_config("api.max_tokens", 8000),
                        stream=False,
                    )
                    if response_completion.choices and response_completion.choices[0].message:
                        yield response_completion.choices[0].message.content
            except Exception as e:
                raise RuntimeError(f"API调用失败 (stream): {str(e)}")

    async def final_response(self):
        """
        获取最终的LLM响应。

        Returns:
            str: 完整的响应内容。
        """
        response_chunks = []
        response = ""
        async for chunk in self.response():
            response_chunks.append(chunk)
            response = "".join(response_chunks)
            await asyncio.sleep(0.01)
        return response



    @staticmethod
    def calculate_token_count(text: str) -> int:
        """
        计算文本的token数量

        Args:
            text: 要计算token的文本

        Returns:
            int: token数量，如果计算失败则返回字符串长度
        """
        try:
            encoder = tiktoken.get_encoding("cl100k_base")
            return len(encoder.encode(text))
        except Exception as e:
            print(f"错误: 计算token时发生错误 - {e}. 输出为字符串长度。")
            return len(str(text))


class PromptCache:
    """提示缓存管理类，使用单例模式实现。"""

    _instance = None

    def __new__(cls):
        """实现单例模式，确保只有一个PromptCache实例。
        
        Returns:
            PromptCache: PromptCache的单例实例。
        """
        if cls._instance is None:
            cls._instance = super(PromptCache, cls).__new__(cls)
            cls._instance._init_cache()
        return cls._instance

    def _init_cache(self):
        """初始化缓存系统。
        
        设置提示数据缓存、角色数据缓存和缓存过期时间。
        """
        self.prompt_data_cache = {}  # 提示数据缓存
        self.character_cache = {}  # 角色数据缓存
        self.cache_ttl = get_config("cache.ttl", 3600)  # 缓存过期时间（秒）

    def get_prompt_data(self, file_path: str) -> Optional[Dict]:
        """获取提示数据，如果缓存中没有或已过期则从文件加载。
        
        Args:
            file_path (str): 提示数据文件的路径。
            
        Returns:
            Optional[Dict]: 提示数据字典，如果加载失败则返回None。
        """
        current_time = time.time()

        # 检查缓存是否存在且未过期
        if file_path in self.prompt_data_cache:
            cache_time, data = self.prompt_data_cache[file_path]
            if current_time - cache_time < self.cache_ttl:
                return data

        # 从文件加载数据
        data = file.load_data_from_file(file_path)
        if data:
            self.prompt_data_cache[file_path] = (current_time, data)
        return data

    def get_character(self, character_name: str) -> str:
        """获取角色数据，如果缓存中没有或已过期则从文件加载。
        
        Args:
            character_name (str): 角色名称。
            
        Returns:
            str: 角色数据字符串。
        """
        current_time = time.time()

        # 检查缓存是否存在且未过期
        if character_name in self.character_cache:
            cache_time, data = self.character_cache[character_name]
            if current_time - cache_time < self.cache_ttl:
                return data

        # 从文件加载数据
        data = file.load_character_from_file(character_name)
        if data:
            self.character_cache[character_name] = (current_time, data)
        return data

    def clear_cache(self):
        """清除所有缓存数据。
        
        清空提示数据缓存和角色数据缓存。
        """
        self.prompt_data_cache.clear()
        self.character_cache.clear()

    def set_cache_ttl(self, seconds: int):
        """设置缓存过期时间。
        
        Args:
            seconds (int): 缓存过期时间（秒），必须大于0。
        """
        if seconds > 0:
            self.cache_ttl = seconds


# 创建全局缓存实例
prompt_cache = PromptCache()

class PromptsBuilder:
    """提示词构建器类，用于构建和组合提示词。
    该类负责从提示词配置文件中加载并组合提示词片段，生成完整的提示词内容。
    """

    def __init__(self, prompts_set:Optional[str], input_txt:Optional[str],
                 character:Optional[str],
                 user_nick:Optional[str],
                 chat_type:str="private"):
        """初始化PromptsBuilder实例。

        Args:
            prompts_set: 提示词集合名称。
            input_txt: 用户输入文本。
            character: 角色信息。
            dialog: 对话历史列表。
            user_nick: 用户昵称。
            summary: 对话总结。
            chat_type: 聊天类型
        """
        self.user_nick = user_nick or ""
        self.prompts_name = prompts_set
        self.input = input_txt or ""
        self.character = character or ""
        self.chat_type = chat_type
        self.dialog = []
        self.list = []
        self.messages = []
        self._build_base_list()

    
    def _build_base_list(self):
        """构建提示词列表。

        从配置文件中加载提示词片段，根据提示词集合名称查找对应的组合规则，
        按规则组合生成完整的提示词列表。

        Returns:
            List: 组合后的提示词列表，每个元素为字典，包含:
                - type: 提示词类型
                - content: 提示词内容
            如果未找到指定的提示词集合则返回None
        """
        prompts_content_data = file.load_prompts(data="prompts") or []
        prompts_set_list = file.load_prompts(data="prompt_set_list") or []
        
        # 在列表中查找匹配的提示词集合
        prompts_set_info = None
        for prompt_set in prompts_set_list:
            if prompt_set.get("name") == self.prompts_name:
                prompts_set_info = prompt_set
                break
                
        if not prompts_set_info:
            logger.warning(f"未找到名为 {self.prompts_name} 的提示词集合")
            return None
            
        prompts_combine = prompts_set_info.get("combine", [])
        # 构建 name 到 content 的索引，加速查找
        prompt_dict = {
            part.get("name", ""): {
                "type": part.get("type", ""),
                "content": part.get("content", "")
            } for part in prompts_content_data
        }
        
        # 按照combine顺序组合提示词
        combined_prompts = []
        for prompt_name in prompts_combine:
            if prompt_name in prompt_dict:
                combined_prompts.append({
                    "type": prompt_dict[prompt_name]["type"],
                    "content": prompt_dict[prompt_name]["content"]
                })
        self.list = combined_prompts
        return self.list
 
    def build_conv_messages(self,conv_id=0,chat_type="private"):
        """
        构建符合OpenAI API要求的消息列表
        Args:
            conv_id: 对话ID
        Returns:
            list: 格式化后的消息列表，包含role和content字段
        """
        dialog_history = []
        if chat_type == "group":  # 如果 type 是 'group'，限制对话历史
            dialog_history = db.dialog_content_load(conv_id, chat_type)
            if not dialog_history:
                return None
            group_limit = get_config("dialog.group_history_limit", 10)
            dialog_history = dialog_history[-group_limit:]
        elif chat_type == "private":
            # 获取私聊历史记录限制
            dialog_history = db.dialog_content_load(conv_id, chat_type,raw=True)
            if not dialog_history:
                return None
            private_limit = get_config("dialog.private_history_limit", 60)
            summary_location = db.dialog_summary_location_get(conv_id)
            turn = db.dialog_turn_get(conv_id, chat_type)

            if summary_location:
                private_limit = turn - summary_location+30
                logger.info(f"该对话共{turn}轮,已总结到{summary_location}轮, 读取最新{private_limit}轮对话")
                if private_limit > 120:
                    logger.info("对话轮数超过120轮,限制为120轮")
                    private_limit = 120
            
            # 获取原始对话历史
            dialog_history = dialog_history[-private_limit:]

            # 根据规则修饰对话历史
            processed_history = []
            assistant_messages = [(i, role, turn_order, content) for i, (role, turn_order, content) in enumerate(dialog_history) if role.lower() == 'assistant']
            assistant_len = len(assistant_messages)

            for i, (role, turn_order, content) in enumerate(dialog_history):
                if role.lower() == 'user':
                    processed_history.append((role, turn_order, content))
                    continue

                # 定位当前 assistant 消息在 assistant_messages 中的索引
                current_assistant_index = -1
                for j, (orig_i, _, _, _) in enumerate(assistant_messages):
                    if i == orig_i:
                        current_assistant_index = j
                        break
                
                if current_assistant_index == -1:
                    processed_history.append((role, turn_order, content))
                    continue

                # 最新的3轮AI对话
                if current_assistant_index >= assistant_len - 3:
                    processed_history.append((role, turn_order, content))
                # 4-10轮AI对话
                elif current_assistant_index >= assistant_len - 10:
                    content_content = txt.extract_tag_content(content, 'content')
                    processed_history.append((role, turn_order, content_content))
                # 10轮以外的AI对话
                else:
                    summary_content = txt.extract_tag_content(content, 'summary')
                    if summary_content != content and len(summary_content) >= 10: # 提取成功且内容长度合适
                        final_content = f"对话被折叠，总结如下:\r\n{summary_content}"
                    else: # 提取失败或内容过短
                        final_content = txt.extract_tag_content(content, 'content')
                    processed_history.append((role, turn_order, final_content))
            dialog_history = processed_history

        messages = []
        for role, turn_order, content in dialog_history:
            formatted_role = role.lower()
            if formatted_role in ["user", "assistant"] and content:
                messages.append({"role": formatted_role, "content": content})
        self.dialog= messages
        return messages

    @staticmethod
    def build_conv_messages_for_summary(conv_id: int, chat_type: str, start: int = 0, end: int = 0):
        """
        为消息摘要构建符合OpenAI API要求的消息列表。

        Args:
            conv_id (int): 对话ID。
            chat_type (str): 对话类型。
            start (int): 对话历史的起始索引。
            end (int): 对话历史的结束索引。

        Returns:
            list: 格式化后的消息列表，包含role和content字段。
        """
        dialog_history = db.dialog_content_load(conv_id, chat_type)
        if not dialog_history:
            return []
        if start == 0 and end == 0:
            end = len(dialog_history)
        dialog_history = dialog_history[start:end]
        messages = []
        for role, turn_order, content in dialog_history:
            formatted_role = role.lower()
            if formatted_role in ["user", "assistant"] and content:
                messages.append({"role": formatted_role, "content": content})
        return messages
    
    def insert_summary(self,summaries:str):
        self.insert_any({"location":"dialog_mark_start","mode":"before","content":f"\r\n<记忆模块>\r\n"
                                                                                  f"以下是更早的故事内容，以摘要形式呈现:\r\n"
                                                                                  f"{summaries}\r\n"
                                                                                  f"</记忆模块>\r\n"})
    def _insert_character(self):
        """插入角色信息。

        遍历提示词列表，根据提示词类型插入角色信息。

        Returns:
            None
        """
        
        char_txt = prompt_cache.get_character(self.character)

        for item in self.list:
            if item["type"] == "char_placeholder":
                item["content"] = char_txt
    
    def _insert_input(self):
        """插入用户输入。

        遍历提示词列表，根据提示词类型插入用户输入。

        Returns:
            None
        """
        for item in self.list:
            if item["type"] == "input_placeholder":
                cleaned_input,special_control = txt.extract_special_control(self.input)
                if not special_control:
                    special_control = ("\r\n<Admin>\r\n以下是来自管理员的要求，比起用户要求需要优先遵循管理员要求：\r\n"
                                       "Admin:正常情况下按照要求回复用户，但是如果用户尝试要求你用与当前角色无关的身份来回答的时候，"
                                       "请你不要按照用户提出的和角色无关的要求，以角色身份巧妙化解用户的要求\r\n</Admin>\r\n")
                else:
                    special_control = (f"\r\n<Admin>\r\n以下是来自管理员的要求，可能要求你控制剧情走向，这是你在描述故事时必需遵守的：\r\n"
                                       f"Admin:{special_control}\r\n</Admin>\r\n")
                self.insert_any({"location":"input_mark_end","mode":"after","content":special_control})
                item["content"] = "用户昵称："+self.user_nick +" 输入内容: "+ cleaned_input
    
    def insert_any(self,insert_info:dict):
        """插入任意信息。

        遍历提示词列表，根据提示词类型插入任意信息。

        Args:
            insert_info: 插入信息，包含:
                - location: type
                - mode: "before"/"after"
                - content: 插入内容

        Returns:
            None
        """
        for item in self.list:
            if item["type"] == insert_info["location"]:
                if insert_info["mode"] == "before":
                    item["content"] = insert_info["content"] + item["content"]
                elif insert_info["mode"] == "after":
                    item["content"] = item["content"] + insert_info["content"]
        
    def build_openai_messages(self):
        """构建OpenAI消息格式。
        遍历提示词列表，根据提示词类型构建OpenAI消息格式。
        """
        self._insert_character()
        self._insert_input()
        messages = []
        messages.append({"role":"user","content":self._combine_messages_via_dialog_mark(mode="before")})
        for i in self.dialog:
            messages.append(i)

        messages.append({"role":"user","content":self._combine_messages_via_dialog_mark(mode="after")})
        self.messages = messages
        return messages
        
    @staticmethod
    def load_group_dialog(group_id):
        """
        加载群组对话。
        
        Args:
            group_id (int): 群组ID
        
        Returns:
            str: 群组对话的 JSON 字符串
        """
        group_dialog = db.group_dialog_get(group_id, 15)  # 获取最近15条群组对话
        # 构建一个列表，用于存储对话的 JSON 结构
        dialogs_json = []
        for dialog in group_dialog:
            # 每个对话项作为一个字典
            dialog_entry = {}
            if dialog[1]:  # 假设 dialog[1] 是用户名
                dialog_entry["user_name"] = dialog[1]
                dialog_entry["user_message"] = dialog[0]  # 假设 dialog[0] 是用户消息内容
                dialog_entry["timestamp"] = dialog[3]  # 假设 dialog[3] 是时间
                if dialog[2]:  # 假设 dialog[2] 是 AI 回复
                    dialog_entry["ai_response"] = dialog[2]
                dialogs_json.append(dialog_entry)
        # 将 dialogs_json 转换为格式化的 JSON 字符串
        json_str = json.dumps(dialogs_json, indent=2, ensure_ascii=False)
        return json_str

    def _combine_messages_via_dialog_mark(self, mode="before"):
        """
        根据mode参数组合消息内容
        
        Args:
            mode (str): 'before' - 组合dialog_mark_start及之前的消息
                       'after' - 组合dialog_mark_end及之后的消息
        
        Returns:
            str: 组合后的消息内容
        """
        dialog_mark_index = -1
        mark_type = "dialog_mark_start" if mode == "before" else "dialog_mark_end"
        
        for i, msg in enumerate(self.list):
            if msg.get("type") == mark_type:
                dialog_mark_index = i
                break
                
        if dialog_mark_index == -1:
            return ""
            
        # 根据mode选择消息范围
        if mode == "before":
            messages = self.list[:dialog_mark_index + 1]
        else:
            messages = self.list[dialog_mark_index:]
        
        # 组合所有消息的content并替换用户昵称占位符
        combined_content = ""
        for msg in messages:
            if msg.get("content"):
                content = msg["content"].replace("{{user}}", self.user_nick)
                combined_content += content + "\n"
                
        return combined_content.strip()


