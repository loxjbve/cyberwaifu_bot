import json, os

config_path = "./config/config.json"
characters_path = "./characters/"
prompt_path = "./prompts/prompts.json"


def load_config(config_file=config_path):
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
        ADMIN_LIST = config.get("ADMIN", [])
        if not API_LIST:
            raise ValueError("配置文件中未找到 ADMIN")

        # print("配置文件加载成功")
        return {'token':TG_TOKEN,'api':API_LIST,'admin':ADMIN_LIST}

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
