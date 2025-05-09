# 导入必要的模块
import json  # 用于处理JSON数据
import os  # 用于文件路径和文件操作
from typing import Dict, List, Optional, Tuple, Any  # 用于类型提示
import tiktoken  # 用于计算token数
import re  # 用于正则表达式处理
import time  # 用于缓存过期时间
from utils import text_utils as txt
"""
模块概述：处理提示构建，包括加载数据和生成提示字符串。
重构版本：将大型函数拆分为更小的专用函数，提高代码可读性和可维护性。
优化版本：添加缓存机制，减少文件IO操作。
"""

# ===== 缓存管理类 =====

class PromptCache:
    """提示缓存管理类，使用单例模式实现。"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptCache, cls).__new__(cls)
            cls._instance._init_cache()
        return cls._instance
    
    def _init_cache(self):
        """初始化缓存"""
        self.prompt_data_cache = {}  # 提示数据缓存
        self.character_cache = {}    # 角色数据缓存
        self.cache_ttl = 3600        # 缓存过期时间（秒）
    
    def get_prompt_data(self, file_path: str) -> Optional[Dict]:
        """获取提示数据，如果缓存中没有或已过期则从文件加载"""
        current_time = time.time()
        
        # 检查缓存是否存在且未过期
        if file_path in self.prompt_data_cache:
            cache_time, data = self.prompt_data_cache[file_path]
            if current_time - cache_time < self.cache_ttl:
                return data
        
        # 从文件加载数据
        data = load_data_from_file(file_path)
        if data:
            self.prompt_data_cache[file_path] = (current_time, data)
        return data
    
    def get_character(self, character_name: str) -> str:
        """获取角色数据，如果缓存中没有或已过期则从文件加载"""
        current_time = time.time()
        
        # 检查缓存是否存在且未过期
        if character_name in self.character_cache:
            cache_time, data = self.character_cache[character_name]
            if current_time - cache_time < self.cache_ttl:
                return data
        
        # 从文件加载数据
        data = load_character_from_file(character_name)
        if data:
            self.character_cache[character_name] = (current_time, data)
        return data
    
    def clear_cache(self):
        """清除所有缓存"""
        self.prompt_data_cache.clear()
        self.character_cache.clear()
    
    def set_cache_ttl(self, seconds: int):
        """设置缓存过期时间"""
        if seconds > 0:
            self.cache_ttl = seconds


# 创建全局缓存实例
prompt_cache = PromptCache()


# ===== 文件加载与解析函数 =====

def load_data_from_file(file_path: str) -> Optional[Dict]:
    """直接从文件加载JSON数据，返回字典或None（处理文件不存在或解析错误）。"""
    if not os.path.exists(file_path):
        print(f"错误: 文件 '{file_path}' 不存在。")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)  # 加载并返回数据
    except json.JSONDecodeError as e:
        print(f"错误: JSON 文件格式错误 - {e}")
        return None
    except Exception as e:
        print(f"错误: 读取文件时发生意外错误 - {e}")
        return None


def load_data(file_path: str) -> Optional[Dict]:
    """加载JSON文件，优先从缓存获取，如果缓存中没有则从文件加载。"""
    return prompt_cache.get_prompt_data(file_path)


def load_character_from_file(filename: str) -> str:
    """直接从文件加载角色JSON文件，返回格式化字符串或错误消息。"""
    file_path = os.path.join("./characters/", filename + ".json")
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' does not exist."
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return json.dumps(data, ensure_ascii=False, indent=4)
    except json.JSONDecodeError:
        return f"Error: File '{file_path}' is not a valid JSON file."
    except Exception as e:
        return f"Error: An unexpected error occurred: {str(e)}"


def load_character(filename: str) -> str:
    """加载角色JSON文件，优先从缓存获取，如果缓存中没有则从文件加载。"""
    return prompt_cache.get_character(filename)


# ===== 提示内容获取函数 =====

def get_prompt_content(prompts_dict: Dict, category: str, name: str) -> Optional[str]:
    """从字典中获取指定类别和名称的提示内容（名称不区分大小写）。"""
    name_lower = name.lower()
    # category 键在 prompts_dict 中已经是小写
    if category in prompts_dict and name_lower in prompts_dict[category]:
        return prompts_dict[category][name_lower]
    print(f"警告: 无法找到 category '{category}' 或 name '{name}' (尝试名称小写: '{name_lower}') 的内容。")
    return None


def get_prompts_set(sets: List[Dict], name: str) -> Optional[Dict]:
    """从列表中获取指定名称的提示集，返回其'combine'字典。"""
    for item in sets:
        if item.get('name') == name:
            return item.get('combine')
    return None


def load_set_combine(combine_data: Dict) -> Dict[str, List[str]]:
    """从数据中提取并返回结构化的类别字典。"""
    return {
        'system': combine_data.get('System', []),
        'cot': combine_data.get('COT', []),
        'control': combine_data.get('Control', []),
        'sample': combine_data.get('Sample', []),
        'function': combine_data.get('Function', []),
        'jailbreak': combine_data.get('Jailbreak', []),
        'others': combine_data.get('Others', [])
    }


# ===== 文本处理与操作函数 =====

def insert_text(raw_text: str, insert_text: str, position: str, mode: str) -> str:
    """在字符串中插入文本，基于位置和模式。"""
    if not position:
        print("警告: 关键词为空，无法插入。")
        return raw_text
    
    index = raw_text.find(position)
    if index == -1:
        print(f"警告: 关键词 '{position}' 在字符串中不存在。")
        return raw_text
    
    if mode.lower() not in ["before", "after"]:
        print(f"警告: 无效模式 '{mode}'，默认使用 'after'。")
        mode = "after"
    
    if mode.lower() == "before":
        return raw_text[:index] + insert_text + raw_text[index:]
    return raw_text[:index + len(position)] + insert_text + raw_text[index + len(position):]


def calculate_token_count(text: str) -> int:
    """计算文本的token数，使用TikToken；失败时返回字符长度。"""
    try:
        encoder = tiktoken.get_encoding("cl100k_base")
        return len(encoder.encode(text))
    except Exception as e:
        print(f"错误: 计算token时发生错误 - {e}. 输出为字符串长度。")
        return len(text)


def split_prompts(text: str) -> Dict:
    """将提示文本分割为系统和用户部分。"""
    prompts = text.split("以下是用户最新输入:\r\n")
    return {"system": prompts[0], "user": prompts[1]}


# ===== 提示构建辅助函数 =====

def create_category_wrapper(category: str) -> Tuple[str, str]:
    """根据类别创建相应的前缀和后缀。"""
    wrappers = {
        'system': ("", "<character>\r\n以下是你需要扮演的角色的信息\r\n</character>\r\n"),
        'cot': ("<thinking>\r\n以下内容是你在生成之前需要思考的部分\r\n", "</thinking>"),
        'control': ("<format>以下内容是对于生成内容的格式要求，请您务必遵守\r\n", "</format>\r\n"),
        'sample': ("<sample>\r\n以下是可参考内容\r\n", "</sample>\r\n"),
        'function': ("<request>\r\n除此之外，这里还有一些包含用户对生成内容的控制要求\r\n", "</request>\r\n"),
        'jailbreak': ("<attention>\r\n", "</attention>\r\n"),
        'others': ("<others>\r\n", "</others>\r\n")
    }
    return wrappers.get(category, ("", ""))


def add_category_content(lines: List[str], category: str, items: List[str], prompts_dict: Dict):
    """向列表添加类别内容，包括前缀和后缀（仅处理非空列表）。"""
    if not items:
        return
    
    prefix, suffix = create_category_wrapper(category)
    lines.append(f"\r\n{prefix}")
    
    for item in items:
        content = get_prompt_content(prompts_dict, category, item)
        if content:
            lines.append(content)
            lines.append('\r\n')
    
    lines.append(suffix)


def create_prompts_dict(data: Dict) -> Dict:
    """从数据创建提示字典，便于快速查找。确保类别键和名称键都为小写。"""
    return {category.lower(): {item['name'].lower(): item['content'] for item in items}
            for category, items in data.get('prompts', {}).items()}


def insert_character_info(prompt_text: str, character: str) -> str:
    """插入角色信息到指定位置。如果角色数据包含 'meeting' 字段，则在插入前移除它。"""
    char_str_or_error = load_character(character)

    if not char_str_or_error or char_str_or_error.startswith("Error:"):
        # 如果加载失败或返回的是错误信息，则直接返回错误提示
        return "<|System| 如果看见此字段，请提示用户角色加载错误！如果看见此字段，请提示用户角色加载错误！如果看见此字段，请提示用户角色加载错误！>"

    try:
        # 尝试解析JSON
        char_data = json.loads(char_str_or_error)
        # 如果 'meeting' 存在，则移除它
        if isinstance(char_data, dict) and 'meeting' in char_data:
            del char_data['meeting']
        # 将处理后的数据转回JSON字符串
        processed_char_str = json.dumps(char_data, ensure_ascii=False, indent=4)
    except json.JSONDecodeError:
        # 如果不是有效的JSON（虽然load_character应该返回JSON字符串或错误），则按原样使用
        # 这种情况理论上不应该发生，因为 load_character 应该返回格式化的JSON字符串或错误信息
        print(f"警告: load_character 返回的内容无法解析为JSON: {char_str_or_error[:100]}...") # 打印部分内容以供调试
        processed_char_str = char_str_or_error
    
    return insert_text(prompt_text, processed_char_str, '</character>', 'before')




def format_user_control(control_content: str) -> str:
    """格式化用户控制内容，添加适当的包装。"""
    if not control_content:
        return ""
    
    return ("\r\n<user_control>\r\n"
            "以下是用户希望控制的剧情发展方向或对内容的要求，甚至有一些超现实内容，请你务必遵守\r\n"
            f"{control_content}\r\n"
            "</user_control>\r\n")


# ===== 主要提示构建函数 =====

def build_prompt_set(name: str, data: Dict) -> str:
    """基于数据构建提示字符串。"""
    if not data:
        return ""
    
    # 创建提示字典和获取提示集
    prompts_dict = create_prompts_dict(data)
    sets = data.get('prompt_set_list', [])
    set_data = get_prompts_set(sets, name)
    
    if not set_data:
        print(f"警告: 未找到名为 '{name}' 的提示集。")
        return ""
    
    # 加载提示集合并构建提示
    combine = load_set_combine(set_data)
    lines = []
    
    # 按顺序添加各类别内容
    categories = ['system', 'cot', 'control', 'sample', 'function', 'jailbreak', 'others']
    for category in categories:
        add_category_content(lines, category, combine[category], prompts_dict)
    
    return ''.join(lines)


def build_prompts(character: str, input_text: str, set_name: str) -> str:
    """构建完整的提示文本，包括角色和用户输入。"""
    # 加载提示数据（使用缓存机制）
    file_path = './prompts/prompts.json'
    data = load_data(file_path)
    if not data:
        return ""
    
    # 构建基础提示文本并插入角色信息
    prompt_text = build_prompt_set(set_name, data)
    prompt_text = insert_character_info(prompt_text, character)
    prompt_text += "以下是用户最新输入:\r\n"
    
    # 处理用户输入中的特殊控制标记
    cleaned_input, special_control = txt.extract_special_control(input_text)
    
    # 如果存在特殊控制，添加到提示中
    if special_control:
        control_text = format_user_control(special_control)
        prompt_text = insert_text(prompt_text, control_text, '以下是用户最新输入:\r\n', 'before')
    
    # 添加清理后的用户输入
    final_prompt = insert_text(prompt_text, cleaned_input, '以下是用户最新输入:\r\n', 'after')
    
    return final_prompt


# ===== 缓存管理函数 =====

def clear_prompt_cache():
    """清除所有提示缓存"""
    prompt_cache.clear_cache()


def set_cache_ttl(seconds: int):
    """设置缓存过期时间（秒）"""
    prompt_cache.set_cache_ttl(seconds)