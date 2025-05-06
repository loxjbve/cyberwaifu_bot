import os
import json
import time


def load_config(config_file="./config/config.json"):
    """
    从 JSON 文件加载配置
    返回：(TG_TOKEN, API_LIST, KEYWORDS, whitelist) 或在出错时返回 None
    """
    try:
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


        # print("配置文件加载成功")
        return TG_TOKEN, API_LIST

    except Exception as e:
        print(f"加载配置文件时出错: {str(e)}")
        return None




def list_characters(user_id, char_dir="./characters/"):
    """
    列出所有可用角色
    返回：角色名称列表
    """
    result = []
    for f in os.listdir(char_dir):
        name, ext = os.path.splitext(f)
        if ext in (".txt", ".json"):
            if name.endswith("_public") or name.endswith(f"_{user_id}"):
                result.append(name)
    return result


def load_prompts(prompt_file="./prompts/prompts.json"):
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
