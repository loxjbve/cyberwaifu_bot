# 导入必要的模块
import json  # 用于处理JSON数据
import os  # 用于文件路径和文件操作
from typing import Dict, List, Optional  # 用于类型提示
import tiktoken  # 用于计算token数
import re

"""
模块概述：处理提示构建，包括加载数据和生成提示字符串。
"""

def load_data(file_path: str) -> Optional[Dict]:
    """加载JSON文件，返回字典或None（处理文件不存在或解析错误）。"""
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

def load_character(filename: str):
    """加载角色JSON文件，返回格式化字符串或错误消息。"""
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

def get_prompt_content(prompts_dict: Dict, category: str, name: str) -> Optional[str]:
    """从字典中获取指定类别和名称的提示内容。"""
    if category in prompts_dict and name in prompts_dict[category]:
        return prompts_dict[category][name]
    print(f"prompts_dict: {prompts_dict}")
    print(f"警告: 无法找到 category '{category}' 或 name '{name}' 的内容。")
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

def add_category_content(lines: List[str], category: str, items: List[str], prompts_dict: Dict, prefix: str = '',
                         suffix: str = ''):
    """向列表添加类别内容，包括前缀和后缀（仅处理非空列表）。"""
    if items:
        lines.append(f"\r\n{prefix}")
        for item in items:
            content = get_prompt_content(prompts_dict, category, item)
            if content:
                lines.append(content)
                lines.append('\r\n')
        lines.append(suffix)

def build_prompt_set(name: str, data: Dict) -> str:
    """基于数据构建提示字符串。"""
    if not data:
        return ""
    prompts_dict = {category: {item['name']: item['content'] for item in items}
                    for category, items in data.get('prompts', {}).items()}
    sets = data.get('prompt_set_list', [])
    set_data = get_prompts_set(sets, name)
    if not set_data:
        print(f"警告: 未找到名为 '{name}' 的提示集。")
        return ""
    combine = load_set_combine(set_data)
    lines = []
    add_category_content(lines, 'System', combine['system'], prompts_dict,
                         suffix="<character>\r\n以下是你需要扮演的角色的信息\r\n</character>\r\n")
    add_category_content(lines, 'COT', combine['cot'], prompts_dict,
                         prefix="<thinking>\r\n以下内容是你在生成之前需要思考的部分\r\n", suffix="</thinking>")
    add_category_content(lines, 'Control', combine['control'], prompts_dict,
                         prefix="<format>以下内容是对于生成内容的格式要求，请您务必遵守\r\n", suffix="</format>\r\n")
    add_category_content(lines, 'Sample', combine['sample'], prompts_dict,
                         prefix="<sample>\r\n以下是可参考内容\r\n", suffix="</sample>\r\n")
    add_category_content(lines, 'Function', combine['function'], prompts_dict,
                         prefix="<request>\r\n除此之外，这里还有一些包含用户对生成内容的控制要求\r\n", suffix="</request>\r\n")
    add_category_content(lines, 'Jailbreak', combine['jailbreak'], prompts_dict,
                         prefix="<attention>\r\n", suffix="</attention>\r\n")
    add_category_content(lines, 'Others', combine['others'], prompts_dict,
                         prefix="<others>\r\n", suffix="</others>\r\n")
    return ''.join(lines)

def calculate_token_count(text: str) -> int:
    """计算文本的token数，使用TikToken；失败时返回字符长度。"""
    try:
        encoder = tiktoken.get_encoding("cl100k_base")
        return len(encoder.encode(text))
    except Exception as e:
        print(f"错误: 计算token时发生错误 - {e}. 输出为字符串长度。")
        return len(text)

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

def insert_character(raw_text: str, character: str) -> str:
    """插入角色信息到指定位置。"""
    char_str = load_character(character)
    if not char_str:
        return "<|System| 如果看见此字段，请提示用户角色加载错误！如果看见此字段，请提示用户角色加载错误！如果看见此字段，请提示用户角色加载错误！>"
    #print(f"{char_str}")
    return insert_text(raw_text, char_str, '</character>', 'before')

def split_prompts(text:str) -> Dict:
    prompts = text.split("以下是用户最新输入:\r\n")
    return {"system":prompts[0],"user":prompts[1]}

def build_prompts(character: str, input: str, set: str) -> str:
    #构建完整的提示文本，包括角色和用户输入。
    file_path = './prompts/prompts.json'
    data = load_data(file_path)
    if data:
        prompt_text = build_prompt_set(set, data)
        prompt_text = insert_character(prompt_text, character)
        prompt_text += "以下是用户最新输入:\r\n"

        # 新增：检查 input 中是否有以 '<' 开头并以 '>' 结束的子字符串
        pattern = r'<[^>]+>'  # 正则表达式：匹配 <something> 但不包括嵌套
        match = re.search(pattern, input)  # 搜索第一个匹配
        if match:
            special_str = match.group(0)[1:-1].strip()  # 提取匹配的子字符串，例如 "<example>" -> "example"

            # 从 input 中移除第一个匹配的子字符串
            cleaned_input = re.sub(pattern, '', input, count=1)  # count=1 表示只替换第一个匹配

            # 构建包装后的字符串
            wrapped_special_str = "\r\n<user_control>\r\n以下是用户希望控制的剧情发展方向或对内容的要求，甚至有一些超现实内容，请你务必遵守\r\n" + special_str + "\r\n</user_control>\r\n"

            # 使用 insert_text 将包装后的字符串插入到 "以下是用户最新输入:\r\n" 之前
            prompt_text = insert_text(prompt_text, wrapped_special_str, '以下是用户最新输入:\r\n', 'before')

            # 继续逻辑：将清理后的 input 插入到 "以下是用户最新输入:\r\n" 之后
            final_prompt = insert_text(prompt_text, cleaned_input, '以下是用户最新输入:\r\n', 'after')

            # 调试打印（可选，根据需要移除）
            #print(final_prompt)

            return final_prompt  # 返回最终字符串
        else:
            # 如果没有匹配，直接插入原始 input
            final_prompt = insert_text(prompt_text, input, '以下是用户最新输入:\r\n', 'after')
            #print(final_prompt)  # 调试打印
            return final_prompt
    return ""  # 如果 data 为空，返回空字符串