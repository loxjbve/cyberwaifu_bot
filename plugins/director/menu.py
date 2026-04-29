import json
import os
from typing import Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# 按钮行为类型
class ButtonType:
    NAVIGATE = "navigate"  # 跳转到其他菜单
    ACTION = "action"  # 触发功能


# 按钮元素定义
class ButtonElement:
    def __init__(self, text: str, btn_type: str, target: str, description: str = ""):
        self.text = text
        self.btn_type = btn_type  # ButtonType.NAVIGATE 或 ButtonType.ACTION
        self.target = target  # 对于 NAVIGATE 是 menu_id，对于 ACTION 是功能数据（如 undo, regen, 或字符串）
        self.description = description  # 按钮描述，用于提示用户

    def get_callback_data(self) -> str:
        """生成回调数据"""
        if self.btn_type == ButtonType.NAVIGATE:
            return f"director_nav_{self.target}"
        else:  # ACTION
            return f"director_act_{self.target}"


# 菜单（页面）定义
class MenuElement:
    def __init__(self, menu_id: str, display_name: str, buttons: List[ButtonElement], parent_menu: str = None):
        self.menu_id = menu_id
        self.display_name = display_name
        self.buttons = buttons
        self.parent_menu = parent_menu  # 父菜单 ID，用于返回逻辑


# 导演菜单管理类
class DirectorMenu:
    # noinspection SpellCheckingInspection
    def __init__(self):
        # 从配置文件加载数据
        self._load_config()
        
        # 构建菜单对象
        self.menus: Dict[str, MenuElement] = self._build_menus()
    
    def _load_config(self):
        """从JSON配置文件加载菜单数据"""
        # 获取当前文件的目录，然后构建配置文件路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, '..', '..', 'config', 'director_menu.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                self.data_mapping = config_data.get('data_mapping', {})
                self.menu_definitions = config_data.get('menu_definitions', {})
        except FileNotFoundError:
            print(f"警告：配置文件 {config_path} 未找到，使用默认配置")
            self._load_default_config()
        except json.JSONDecodeError as e:
            print(f"警告：配置文件格式错误 {e}，使用默认配置")
            self._load_default_config()
    
    def _load_default_config(self):
        """加载默认配置（作为备用）"""
        self.data_mapping = {
            "undo": "",
            "regen": "",
        }
        self.menu_definitions = {
            "main_menu": {
                "display_name": "主菜单",
                "parent_menu": None,
                "buttons": [
                    {"text": "重新生成", "type": "action", "target": "regen", "description": "重新生成当前内容"},
                    {"text": "撤回", "type": "action", "target": "undo", "description": "撤回上一步操作"},
                ]
            }
        }

    def _build_menus(self) -> Dict[str, MenuElement]:
        """从字典定义构建菜单对象"""
        menus = {}
        for menu_id, config in self.menu_definitions.items():
            buttons = [
                ButtonElement(
                    btn["text"],
                    btn["type"],
                    btn["target"],
                    btn.get("description", f"{btn['text']} 的默认描述")
                )
                for btn in config["buttons"]
            ]
            menus[menu_id] = MenuElement(
                menu_id=menu_id,
                display_name=config["display_name"],
                buttons=buttons,
                parent_menu=config["parent_menu"]
            )
        return menus

    def get_menu_keyboard(self, menu_id: str) -> InlineKeyboardMarkup:
        """根据菜单ID生成键盘布局"""
        menu = self.menus.get(menu_id)
        if not menu:
            return InlineKeyboardMarkup([])

        keyboard = []
        row = []
        for btn in menu.buttons:
            callback_data = btn.get_callback_data()
            row.append(InlineKeyboardButton(btn.text, callback_data=callback_data))
            if len(row) == 3:  # 每行最多3个按钮（可根据需求调整）
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # 如果有父菜单，添加返回按钮
        if menu.parent_menu:
            keyboard.append([
                InlineKeyboardButton("返回", callback_data=f"director_nav_{menu.parent_menu}")
            ])

        return InlineKeyboardMarkup(keyboard)

    def get_menu_meta(self, menu_id: str) -> MenuElement:
        """获取菜单元数据"""
        return self.menus.get(menu_id, None)

    def get_main_menu_id(self) -> str:
        """返回主菜单ID"""
        return "main_menu"

    def get_action_data(self, target: str) -> str:
        """根据 target 获取对应的长字符串数据"""
        return self.data_mapping.get(target, f"未定义的数据映射: {target}")

    def get_menu_description_text(self, menu_id: str) -> str:
        """生成菜单的描述文本，格式为 '按钮名称：描述' 的逐行显示"""
        menu = self.menus.get(menu_id)
        if not menu:
            return f"菜单 {menu_id} 未找到。"

        description_lines = [f"请选择 {menu.display_name} 选项："]
        for btn in menu.buttons:
            description_lines.append(f"{btn.text}: {btn.description}")
        return "\n".join(description_lines)
