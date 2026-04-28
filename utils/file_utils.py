import json
import os
from typing import Dict, Optional

from utils.config_utils import get_admin_ids, get_bot_token, get_config, get_path
import time
from PIL import Image
from telegram import Update
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)
# 获取项目根目录的绝对路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    """
    从配置系统获取配置。

    Returns:
        dict: 包含 token, api, admin 的字典，或在出错时返回 None

    Note:
        此函数保留是为了向后兼容，新代码应直接使用 config_utils 模块
    """
    try:
        # 使用新的配置系统

        # 获取API列表
        API_LIST = get_config("api_list", [])
        if not API_LIST:
            raise ValueError("配置中未找到 api_list")

        # 返回与旧版相同格式的配置字典
        return {"token": get_bot_token(), "api": API_LIST, "admin": get_admin_ids()}
    except Exception as e:
        print(f"加载配置时出错: {str(e)}")
        return None


def list_all_characters(char_dir: Optional[str] = None) -> list[str]:
    """
    列出所有可用角色。

    Args:
        char_dir: 角色文件目录，如果为None则使用配置中的路径

    Returns:
        list[str]: 角色名称列表
    """
    if char_dir is None:
        char_dir = get_path("characters_path")

    result = []
    for f in os.listdir(char_dir):
        name, ext = os.path.splitext(f)
        if ext not in (".txt", ".json"):
            continue
        result.append(name)
    return result


def load_char(char_file_name: str, char_dir: Optional[str] = None):
    """
    加载指定的角色文件。

    Args:
        char_file_name: 角色文件名 (例如 'my_character.json')
        char_dir: 角色文件所在的目录，如果为None则使用配置中的路径

    Returns:
        dict: 角色文件的JSON内容，如果文件不存在或解析失败则返回None
    """
    if char_dir is None:
        char_dir = get_path("characters_path")

    file_path = os.path.join(char_dir, char_file_name)
    try:
        if not os.path.exists(file_path):
            print(f"错误: 角色文件 {file_path} 不存在。")
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            char_data = json.load(f)
            return char_data
    except json.JSONDecodeError as e:
        print(f"错误: 解析角色文件 {file_path} 失败 - {str(e)}")
        return None
    except Exception as e:
        print(f"加载角色文件 {file_path} 时发生未知错误: {str(e)}")
        return None


def load_prompts(prompt_file: Optional[str] = None,data:Optional[str] = "prompt_set_list"):

    """
    加载预设文件。

    Args:
        prompt_file: 预设文件路径，如果为None则使用配置中的路径

    Returns:
        list: 预设列表或 None
    """
    if prompt_file is None:
        prompt_file = get_path("prompt_path")

    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_data = json.load(f)
            return prompt_data.get(data, [])
    except Exception as e:
        print(f"读取预设文件失败: {str(e)}")
        return None


def load_data_from_file(file_path: str) -> Optional[Dict]:
    """
    直接从文件加载JSON数据。

    Args:
        file_path: 文件路径

    Returns:
        Optional[Dict]: 字典或None（处理文件不存在或解析错误）
    """
    if not os.path.exists(file_path):
        print(f"错误: 文件 '{file_path}' 不存在。")
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)  # 加载并返回数据
    except json.JSONDecodeError as e:
        print(f"错误: JSON 文件格式错误 - {e}")
        return None
    except Exception as e:
        print(f"错误: 读取文件时发生意外错误 - {e}")
        return None


def load_character_from_file(filename: str) -> str:
    """
    直接从文件加载角色JSON文件，返回格式化字符串或错误消息。

    Args:
        filename: 角色文件名（不含扩展名）

    Returns:
        str: 格式化的JSON字符串或错误消息
    """
    char_dir = get_path("characters_path")
    file_path = os.path.join(char_dir, filename + ".json")

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


def load_single_prompt(prompt_name: str, prompt_file: Optional[str] = None) -> Optional[str]:
    """
    从指定的JSON文件中加载单个prompt。

    Args:
        prompt_name (str): 要加载的prompt的键名。
        prompt_file (Optional[str]): prompt文件路径。如果为None，则使用默认路径。

    Returns:
        Optional[str]: 返回prompt的文本内容，如果找不到则返回None。
    """
    if prompt_file is None:
        # We'll hardcode this for now, but it should come from config
        prompt_file = "prompts/features_prompts.json"

    try:
        # 修正路径问题：如果 prompt_file 不是绝对路径，则基于项目根目录构建
        if not os.path.isabs(prompt_file):
            prompt_file = os.path.join(project_root, prompt_file)

        with open(prompt_file, "r", encoding="utf-8") as f:
            prompts = json.load(f)
        
        prompt_data = prompts.get(prompt_name)
        if not prompt_data:
            print(f"错误: 在 '{prompt_file}' 中未找到名为 '{prompt_name}' 的prompt。")
            return None
            
        prompt_content = prompt_data.get("prompt")
        if not prompt_content:
            # Fallback to system_prompt for backward compatibility
            prompt_content = prompt_data.get("system_prompt")

        if not prompt_content:
            print(f"错误: 在 '{prompt_name}' prompt中未找到 'prompt' 或 'system_prompt' 键。")
            return None
            
        return prompt_content
    except FileNotFoundError:
        print(f"错误: Prompt文件 '{prompt_file}' 不存在。")
        return None
    except json.JSONDecodeError:
        print(f"错误: Prompt文件 '{prompt_file}' 不是有效的JSON。")
        return None
    except Exception as e:
        print(f"加载prompt时发生未知错误: {e}")
        return None



async def download_and_convert_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> str:
    """从消息中下载、转换并保存图像。

    处理照片、贴纸和动画，并将其转换为JPEG格式。

    Args:
        update: Telegram更新对象。
        context: 上下文对象。
        user_id: 用户的ID。

    Returns:
        保存的JPEG图像的文件路径。

    Raises:
        ValueError: 如果在消息中未找到有效的媒体。
    """
    file_id = None
    if update.message and update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message and update.message.sticker:
        file_id = (
            update.message.sticker.thumbnail.file_id
            if update.message.sticker.thumbnail
            else update.message.sticker.file_id
        )
    elif update.message and update.message.animation:
        file_id = (
            update.message.animation.thumbnail.file_id
            if update.message.animation.thumbnail
            else update.message.animation.file_id
        )

    if not file_id:
        raise ValueError("未能识别到图片、贴纸或GIF。")

    pics_dir = "data/pics"
    os.makedirs(pics_dir, exist_ok=True)
    timestamp = int(time.time())
    filepath = os.path.join(pics_dir, f"{user_id}_{timestamp}.jpg")
    download_path = os.path.join(pics_dir, f"{user_id}_{timestamp}_temp")

    new_file = await context.bot.get_file(file_id)
    await new_file.download_to_drive(download_path)

    try:
        with Image.open(download_path) as img:
            if getattr(img, "is_animated", False):
                img.seek(0)
            img.convert("RGB").save(filepath, "jpeg")
        os.remove(download_path)
    except Exception as e:
        logger.warning(
            f"Could not convert with Pillow: {e}. Renaming and using as is."
        )
        os.rename(download_path, filepath)

    return filepath
