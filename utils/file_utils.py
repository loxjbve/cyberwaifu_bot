import json
import os
from typing import Optional, Dict

config_path = "./config/config_local.json"
config_local = "./config/config_local.json"
characters_path = "./characters/"
prompt_path = "./prompts/prompts.json"


def load_config(config_file=config_local):
    """
    从 JSON 文件加载配置
    返回：(TG_TOKEN, API_LIST, KEYWORDS, whitelist) 或在出错时返回 None
    """
    try:
        if not os.path.exists(config_file):
            config_file = config_path
            if not os.path.exists(config_file):
                raise FileNotFoundError(f"配置文件 {config_file} 不存在")

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 加载 Telegram Bot Token
        TG_TOKEN = config.get("TG_TOKEN", "")
        if not TG_TOKEN:
            raise ValueError("配置文件中未找到 TG_TOKEN")

        # 加载 API 列表
        API_LIST = config.get("api_list", [])
        if not API_LIST:
            raise ValueError("配置文件中未找到 api_list")
        ADMIN_LIST = config.get("ADMIN", [])
        if not API_LIST:
            raise ValueError("配置文件中未找到 ADMIN")

        # print("配置文件加载成功")
        return {'token': TG_TOKEN, 'api': API_LIST, 'admin': ADMIN_LIST}

    except Exception as e:
        print(f"加载配置文件时出错: {str(e)}")
        return None


def list_all_characters(char_dir: str = characters_path) -> list[str]:
    """
    列出所有可用角色
    :param char_dir: 角色文件目录
    :return: 角色名称列表
    """
    result = []
    for f in os.listdir(char_dir):
        name, ext = os.path.splitext(f)
        if ext not in (".txt", ".json"):
            continue
        result.append(name)
    return result


def load_char(char_file_name: str, char_dir: str = characters_path):
    """
    加载指定的角色文件。
    :param char_file_name: 角色文件名 (例如 'my_character.json')
    :param char_dir: 角色文件所在的目录
    :return: 角色文件的JSON内容，如果文件不存在或解析失败则返回None
    """
    file_path = os.path.join(char_dir, char_file_name)
    try:
        if not os.path.exists(file_path):
            print(f"错误: 角色文件 {file_path} 不存在。")
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            char_data = json.load(f)
            return char_data
    except json.JSONDecodeError as e:
        print(f"错误: 解析角色文件 {file_path} 失败 - {str(e)}")
        return None
    except Exception as e:
        print(f"加载角色文件 {file_path} 时发生未知错误: {str(e)}")
        return None


def load_prompts(prompt_file: str = prompt_path):
    """
    加载预设文件
    返回：预设列表或 None
    """
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            prompt_data = json.load(f)
            return prompt_data.get('prompt_set_list', [])
    except Exception as e:
        print(f"读取预设文件失败: {str(e)}")
        return None


def get_api_multiple(api_name):
    api_list = load_config()['api']
    for api in api_list:
        if api['name'] == api_name:
            return api['multiple'] or 1


def get_api_config(api_name: str) -> tuple[str, str, str]:
    """
    根据API名称获取对应的配置信息

    Args:
        api_name: API配置名称

    Returns:
        Tuple[str, str, str]: 返回(api_key, base_url, model)三元组

    Raises:
        ValueError: 当找不到对应API配置时抛出
    """
    api_list = load_config()['api']
    for api_config_item in api_list:
        if api_config_item['name'] == api_name:
            return api_config_item['key'], api_config_item['url'], api_config_item['model']
    raise ValueError(f"未找到名为 '{api_name}' 的API配置")


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
