import datetime
import json
import sqlite3
from sqlite3 import Error
from typing import Any, List, Optional, Tuple

default_api = 'gemini-2'
default_preset = 'Default_meeting'
default_character = 'cuicuishark_public'
default_stream = 'no'


def create_connection(db_file: str = "./data/data.db") -> Optional[sqlite3.Connection]:
    """创建数据库连接"""
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Error as e:
        print(f"连接数据库时发生错误: {e}")
        return None


def revise_db(command: str, params: Tuple = ()) -> int:
    """执行数据库更新操作，返回受影响的行数"""
    conn = create_connection()
    if not conn:
        return 0
    try:
        cursor = conn.cursor()
        cursor.execute(command, params)
        conn.commit()
        return cursor.rowcount
    except sqlite3.Error as e:
        print(f"数据库更新错误: {e}")
        return 0
    finally:
        conn.close()


def query_db(command: str, params: Tuple = ()) -> List[Any]:
    """执行数据库查询操作，返回查询结果"""
    conn = create_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute(command, params)
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"数据库查询错误: {e}")
        return []
    finally:
        conn.close()


def user_config_get(userid: int) -> Optional[Tuple]:
    """获取用户配置，返回角色、api、预设、当前对话"""
    command = "SELECT char, api, preset, conv_id,stream FROM user_config WHERE uid = ?"
    result = query_db(command, (userid,))
    return result[0] if result else None


def user_stream_get(userid: int) -> Optional[Tuple]:
    """获取用户是否开启流式"""
    command = "SELECT stream FROM user_config WHERE uid = ?"
    result = query_db(command, (userid,))
    return result[0][0] if result else None


def user_stream_switch(userid: int) -> bool:
    """切换用户流式传输"""
    if user_stream_get(userid) == 'yes':
        command = "UPDATE  user_config set stream = 'no' WHERE uid = ?"
    else:
        command = "UPDATE  user_config set stream = 'yes' WHERE uid = ?"
    result = revise_db(command, (userid,))
    return result > 0


def user_config_update(userid: int, char: str, api: str, preset: str, conv_id: int) -> bool:
    """更新用户配置"""
    command = "UPDATE user_config SET char = ?, api = ?, preset = ?, conv_id = ? WHERE uid = ?"
    result = revise_db(command, (char, api, preset, conv_id, userid))
    return result > 0


def user_config_arg_update(user_id: int, field: str, value: any) -> bool:
    """更新用户配置信息"""
    command = f"UPDATE user_config SET {field} = ? WHERE uid = ?"
    result = revise_db(command, (value, user_id))
    return result > 0


def user_config_new(userid: int) -> bool:
    """创建新用户配置"""
    command = "INSERT INTO user_config (char, api, preset, uid,stream) VALUES (?, ?, ?, ?,?)"
    result = revise_db(command, (default_character, default_api, default_preset, userid, default_stream))
    return result > 0


def user_config_check(userid: int) -> bool:
    """检查用户是否存在"""
    command = "SELECT uid FROM users WHERE uid = ?"
    result = query_db(command, (userid,))
    return bool(result)


def user_conversations_get(userid: int) -> Optional[List[Tuple]]:
    """获取用户对话列表，返回id、角色、总结"""
    command = "SELECT conv_id, character, summary FROM conversations WHERE user_id = ? AND delete_mark = 'no'"
    result = query_db(command, (userid,))
    return result if result else None


def user_info_get(userid: int) -> Optional[Tuple]:
    """获取用户信息"""
    command = "SELECT first_name, last_name, account_tier, remain_frequency, balance,uid FROM users WHERE uid = ?"
    result = query_db(command, (userid,))
    return result[0] if result else None


def user_info_usage_get(userid: int, info: str) -> Any:
    """获取用户指定字段信息"""
    command = "SELECT ? FROM users WHERE uid = ?"
    result = query_db(command, (info, userid))
    return result[0][0] if result else 0


def user_info_create(userid: int, first_name: str, last_name: str, user_name: str) -> bool:
    """创建用户信息"""
    create_at = str(datetime.datetime.now())
    command = "INSERT INTO users VALUES (?, ?, ?, ?, ?, 0, 0, ?, 0, 0, 0, 0, 1.5)"
    result = revise_db(command, (userid, first_name, last_name, user_name, create_at, create_at))
    return result > 0


def user_info_update(userid: int, field: str, value: Any, increment: bool = False) -> bool:
    """
    更新用户信息
    :param userid: 用户ID
    :param field: 需要更新的字段名
    :param value: 更新值或增量值
    :param increment: 是否为增量更新，默认为 False（直接设置值）
    :return: 更新是否成功
    """
    if increment:
        command = f"UPDATE users SET {field} = {field} + ? WHERE uid = ?"
    else:
        command = f"UPDATE users SET {field} = ? WHERE uid = ?"
    result = revise_db(command, (value, userid))
    return result > 0


def dialog_content_add(conv_id: int, role: str, turn_order: int, raw_content: str, processed_content: str, msg_id: int,
                       type: str = 'private') -> bool:
    """添加对话内容"""
    create_at = str(datetime.datetime.now())
    if type == 'private':
        command = "INSERT INTO dialogs (conv_id, role, raw_content, turn_order, created_at, processed_content,msg_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
        result = revise_db(command, (conv_id, role, raw_content, turn_order, create_at, processed_content, msg_id))
        if result:
            command = "UPDATE conversations SET update_at = ? WHERE conv_id = ?"
            return revise_db(command, (create_at, conv_id)) > 0
        return False
    else:
        command = "INSERT INTO group_user_dialogs (conv_id, role, raw_content, turn_order, created_at, processed_content) VALUES (?, ?, ?, ?, ?, ?)"
        result = revise_db(command, (conv_id, role, raw_content, turn_order, create_at, processed_content))
        if result:
            command = "UPDATE group_user_conversations SET update_at = ? WHERE conv_id = ?"
            return revise_db(command, (create_at, conv_id)) > 0
        return False


def dialog_latest_del(conv_id: int) -> int:
    """
    删除指定conv_id中turn_order最大的记录
    参数:
        conv_id: 会话ID
    返回:
        受影响的行数（通常为1，如果删除成功；0，如果没有记录被删除）
    """
    # 步骤1：查询指定conv_id中最大的turn_order
    query_cmd = "SELECT MAX(turn_order) FROM dialogs WHERE conv_id = ?"
    result = query_db(query_cmd, (conv_id,))

    # 检查查询结果，如果没有记录，则返回0
    max_turn_order = result[0][0] if result and result[0][0] is not None else None
    if max_turn_order is None:
        return 0

    # 步骤2：删除该conv_id中turn_order最大的记录
    delete_cmd = "DELETE FROM dialogs WHERE conv_id = ? AND turn_order = ?"
    affected_rows = revise_db(delete_cmd, (conv_id, max_turn_order))

    return affected_rows


def dialog_latest_get(conv_id: int) -> str:
    """
    获取指定conv_id中turn_order最大的记录的raw_content值
    参数:
        conv_id: 会话ID
    返回:
        raw_content的值，如果没有记录则返回空字符串
    """
    # 查询指定conv_id中turn_order最大的记录的raw_content
    query_cmd = "SELECT raw_content FROM dialogs WHERE conv_id = ? ORDER BY turn_order DESC LIMIT 1"
    result = query_db(query_cmd, (conv_id,))
    dialog_latest_del(conv_id)

    # 检查查询结果，如果有记录则返回raw_content，否则返回空字符串
    return result[0][0] if result else ""


def dialog_turn_get(conv_id: int, type: str = 'private') -> int:
    """获取对话轮数"""
    command = "SELECT MAX(turn_order) FROM dialogs WHERE conv_id = ?" if type == 'private' else "SELECT MAX(turn_order) FROM group_user_dialogs WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result[0][0] if result and result[0][0] is not None else 0


def dialog_content_load(conv_id: int, type: str = 'private') -> Optional[List[Tuple]]:
    """加载对话内容"""
    command = "SELECT role, turn_order, processed_content FROM dialogs WHERE conv_id = ?" if type != 'group' else "SELECT role, turn_order, processed_content FROM group_user_dialogs WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result if result else None


def conversation_private_create(conv_id: int, userid: int, character: str, preset: str) -> bool:
    """创建私聊对话"""
    create_at = str(datetime.datetime.now())
    user_info_update(userid, 'update_at', create_at)
    command = "INSERT INTO conversations (conv_id, user_id, character, preset, create_at, update_at, delete_mark) VALUES (?, ?, ?, ?, ?, ?, 'yes')"
    result = revise_db(command, (conv_id, userid, character, preset, create_at, create_at))
    return result > 0


def conversation_private_save(conv_id: int) -> bool:
    """保存私聊对话"""
    command = "UPDATE conversations SET delete_mark = 'no' WHERE conv_id = ?"
    result = revise_db(command, (conv_id,))
    return result > 0


def conversation_private_get(conv_id: int) -> Optional[Tuple]:
    """获取私聊对话信息"""
    command = "SELECT character, preset FROM conversations WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result[0] if result else None


def conversation_group_config_get(conv_id: int) -> Optional[Tuple]:
    """获取私聊对话信息"""
    command = "SELECT group_id FROM group_user_conversations WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    group_id = result[0][0]
    command = "SELECT char, preset FROM groups WHERE group_id = ?"
    result = query_db(command, (group_id,))
    return result[0] if result else None


def conversation_private_update(conv_id: int, char: str, preset: str) -> bool:
    """更新私聊对话信息"""
    command = "UPDATE conversations SET character = ?, preset = ? WHERE conv_id = ?"
    result = revise_db(command, (char, preset, conv_id))
    return result > 0


def conversation_private_arg_update(conv_id: int, field: str, value: str or int, increment: bool = False) -> bool:
    """更新私聊对话信息"""
    if increment:
        command = f"UPDATE conversations SET {field} = {field} + ? WHERE conv_id = ?"
    else:
        command = f"UPDATE conversations SET {field} = ? WHERE conv_id = ?"
    result = revise_db(command, (value , conv_id))
    return result > 0


def conversation_private_delete(conv_id: int) -> bool:
    """更新私聊对话信息"""
    command = "UPDATE conversations SET delete_mark = ? WHERE conv_id = ?"
    result = revise_db(command, ('yes', conv_id))
    return result > 0


def conversation_private_check(conv_id: int) -> bool:
    """检查私聊对话是否存在，返回True表示不存在"""
    command = "SELECT conv_id FROM conversations WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return not bool(result)


def conversation_private_summary_add(conv_id: int, summary: str) -> bool:
    """添加私聊对话总结"""
    command = "UPDATE conversations SET summary = ? WHERE conv_id = ?"
    result = revise_db(command, (summary, conv_id))
    return result > 0


def conversation_group_create(conv_id: int, user_id: int, user_name: str, group_id: int, group_name: str) -> bool:
    """创建群聊对话"""
    create_at = str(datetime.datetime.now())
    group_info_update(group_id, 'update_time', create_at)
    command = "INSERT INTO group_user_conversations (user_id, user_name, group_id, group_name, conv_id, create_at, delete_mark) VALUES (?, ?, ?, ?, ?, ?, 'no')"
    result = revise_db(command, (user_id, user_name, group_id, group_name, conv_id, create_at))
    return result > 0


def conversation_group_check(conv_id: int) -> bool:
    """检查群聊对话是否存在，返回True表示不存在"""
    command = "SELECT conv_id FROM group_user_conversations WHERE conv_id = ? AND delete_mark = 'no'"
    result = query_db(command, (conv_id,))
    return not bool(result)


def conversation_group_get(group_id: int, user_id: int) -> Optional[int]:
    """获取群聊对话ID"""
    command = "SELECT conv_id FROM group_user_conversations WHERE group_id = ? AND user_id = ? AND delete_mark = 'no'"
    result = query_db(command, (group_id, user_id))
    return result[0][0] if result else None


def conversation_group_update(group_id: int, user_id: int, field: str, value: Any) -> bool:
    """更新群聊对话信息"""
    command = f"UPDATE group_user_conversations SET {field} = ? WHERE group_id = ? AND user_id = ? AND delete_mark = 'no'"
    result = revise_db(command, (value, group_id, user_id))
    return result > 0


def conversation_group_delete(group_id: int, user_id: int) -> bool:
    """删除群聊对话"""
    command = "UPDATE group_user_conversations SET delete_mark = 'yes' WHERE group_id = ? AND user_id = ?"
    result = revise_db(command, (group_id, user_id))
    return result > 0


def conversation_turns_update(conv_id: int, turn_num: int, type: str = 'private') -> bool:
    """更新对话轮数"""
    table = "conversations" if type == 'private' else "group_user_conversations"
    command = f"UPDATE {table} SET turns = ? WHERE conv_id = ?"
    result = revise_db(command, (turn_num, conv_id))
    return result > 0


def group_check_update(group_id: int) -> bool:
    """检查群组是否需要更新"""
    command = "SELECT update_time FROM groups WHERE group_id = ?"
    result = query_db(command, (group_id,))
    if result:
        update_time = datetime.datetime.strptime(str(result[0][0]), "%Y-%m-%d %H:%M:%S.%f")
        return update_time < datetime.datetime.now() - datetime.timedelta(minutes=5)
    return True


def group_config_get(group_id: int) -> Optional[Tuple]:
    """获取群组配置"""
    command = "SELECT api, char, preset FROM groups WHERE group_id = ?"
    result = query_db(command, (group_id,))
    return result[0] if result else None


def group_admin_list_get(group_id: int) -> List[str]:
    """获取群组管理员列表"""
    try:
        command = "SELECT members_list FROM groups WHERE group_id = ?"
        result = query_db(command, (group_id,))
        return json.loads(result[0][0]) if result and result[0][0] else []
    except Exception as e:
        print(f"获取群管理员错误: {e}")
        return []


def group_keyword_get(group_id: int) -> List[str]:
    """获取群组关键词"""
    try:
        command = "SELECT keywords FROM groups WHERE group_id = ?"
        result = query_db(command, (group_id,))
        return json.loads(result[0][0]) if result and result[0][0] else []
    except Exception as e:
        print(f"获取群组关键词错误: {e}")
        return []


def group_keyword_set(group_id: int, keywords: List[str]) -> bool:
    """设置群组关键词"""
    try:
        keywords_str = json.dumps(keywords, ensure_ascii=False)
        command = "UPDATE groups SET keywords = ? WHERE group_id = ?"
        result = revise_db(command, (keywords_str, group_id))
        return result > 0
    except Exception as e:
        print(f"设置群组关键词错误: {e}")
        return False


def group_info_create(group_id: int) -> bool:
    """创建群组信息"""
    command = "INSERT INTO groups (group_id, api, char, preset) VALUES (?, ?, ?, ?)"
    result = revise_db(command, (group_id, default_api, default_character, default_preset))
    return result > 0


def group_dialog_add(msg_id: int, group_id: int) -> bool:
    """添加群组对话"""
    command = "INSERT INTO group_dialogs (msg_id, group_id) VALUES (?, ?)"
    result = revise_db(command, (msg_id, group_id))
    return result > 0


def group_dialog_update(msg_id: int, field: str, value: Any, group_id: int) -> bool:
    """更新群组对话信息"""
    command = f"UPDATE group_dialogs SET {field} = ? WHERE msg_id = ? AND group_id = ?"
    result = revise_db(command, (value, msg_id, group_id))
    return result > 0


def group_info_update(group_id: int, field: str, value: Any) -> bool:
    """更新群组信息"""
    command = f"UPDATE groups SET {field} = ? WHERE group_id = ?"
    result = revise_db(command, (value, group_id))
    return result > 0
