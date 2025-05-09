import datetime
import json
import sqlite3
import threading
from sqlite3 import Error
from typing import Any, List, Optional, Tuple

# --- 默认配置项 (建议未来迁移到专门的配置文件) ---
DEFAULT_API = 'gemini-2'  # 默认使用的LLM API
DEFAULT_PRESET = 'Default_meeting'  # 默认预设名称
DEFAULT_CHAR = 'cuicuishark_public'  # 默认角色名称
DEFAULT_STREAM = 'no'  # 默认是否开启流式传输 ('yes'/'no')
DEFAULT_FREQUENCY = 200  # 用户默认的每日免费使用次数
DEFAULT_BALANCE = 1.5  # 用户默认的初始余额


class DatabaseConnectionPool:
    """数据库连接池，使用单例模式实现"""
    _instance: Optional['DatabaseConnectionPool'] = None
    _lock = threading.Lock()

    def __new__(cls, db_file: str = "./data/data.db", max_connections: int = 5) -> 'DatabaseConnectionPool':
        """
        实现单例模式，确保全局只有一个连接池实例。

        :param db_file: 数据库文件路径。
        :param max_connections: 连接池中的最大连接数。
        :return: DatabaseConnectionPool的单例实例。
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseConnectionPool, cls).__new__(cls)
                cls._instance.db_file = db_file
                cls._instance.max_connections = max_connections
                cls._instance.connections: List[sqlite3.Connection] = []
                cls._instance.connection_locks: List[threading.Lock] = []
                cls._instance.initialize_pool()
        return cls._instance

    def initialize_pool(self):
        """根据 `max_connections` 初始化连接池中的数据库连接。"""
        for _ in range(self.max_connections):
            try:
                conn = sqlite3.connect(self.db_file, check_same_thread=False)
                self.connections.append(conn)
                self.connection_locks.append(threading.Lock())
            except Error as e:
                print(f"初始化连接池时发生错误: {e}")

    def get_connection(self) -> Tuple[Optional[sqlite3.Connection], int]:
        """
        从连接池中获取一个可用的数据库连接及其索引。
        如果所有池中连接都在使用，则尝试创建一个临时连接。

        :return: 一个元组 (connection, index)。
                 如果成功获取连接，connection 是 sqlite3.Connection 对象，index 是连接在池中的索引（临时连接为 -1）。
                 如果获取失败，connection 是 None，index 是 -1。
        """
        for i, lock in enumerate(self.connection_locks):
            if lock.acquire(blocking=False):
                return self.connections[i], i
        # 如果所有连接都在使用中，创建一个临时连接
        try:
            temp_conn = sqlite3.connect(self.db_file, check_same_thread=False)
            return temp_conn, -1  # -1 表示这是一个临时连接
        except Error as e:
            print(f"创建临时连接时发生错误: {e}")
            return None, -1

    def release_connection(self, index: int):
        """
        释放连接池中指定索引的连接锁，使其可被其他线程使用。
        此方法不关闭连接，仅释放锁。

        :param index: 要释放的连接在池中的索引。
        """
        if 0 <= index < len(self.connection_locks):
            self.connection_locks[index].release()

    def close_all(self):
        """关闭连接池中的所有数据库连接，并清空连接列表。应在应用退出时调用。"""
        for conn in self.connections:
            try:
                conn.close()
            except Error:
                pass
        self.connections = []
        self.connection_locks = []


# 创建全局连接池实例
db_pool = DatabaseConnectionPool()


def create_connection(db_file: str = "./data/data.db") -> Optional[sqlite3.Connection]:
    """获取一个数据库连接（主要为兼容旧代码，推荐直接使用连接池）。"""
    conn, _ = db_pool.get_connection()
    return conn


def execute_db_operation(operation_type: str, command: str, params: Tuple = ()):
    """
    执行数据库操作的通用函数。

    :param operation_type: 操作类型，可以是 "query" 或 "update"。
    :param command: 要执行的 SQL 命令。
    :param params: SQL 命令的参数。
    :return: 如果是查询操作，返回结果列表；如果是更新操作，返回受影响的行数。
             发生错误时，查询返回空列表，更新返回0。
    """
    conn, conn_index = db_pool.get_connection()
    if not conn:
        print(f"数据库错误: 无法获取连接以执行 {operation_type} 操作: {command}")
        return [] if operation_type == "query" else 0

    try:
        cursor = conn.cursor()
        cursor.execute(command, params)

        if operation_type == "update":
            conn.commit()
            result = cursor.rowcount
        else:  # query
            result = cursor.fetchall()

        return result
    except sqlite3.Error as e:
        print(f"数据库 {operation_type} 操作失败: {command} 参数: {params} 错误: {e}")
        return [] if operation_type == "query" else 0
    finally:
        if conn_index >= 0:  # 如果是连接池中的连接，释放它
            db_pool.release_connection(conn_index)
        else:  # 如果是临时连接，关闭它
            if conn: # 确保临时连接存在才关闭
                conn.close()


def revise_db(command: str, params: Tuple = ()) -> int:
    """执行数据库更新操作，返回受影响的行数"""
    return execute_db_operation("update", command, params)


def query_db(command: str, params: Tuple = ()) -> List[Any]:
    """执行数据库查询操作，返回查询结果"""
    return execute_db_operation("query", command, params)


def user_config_get(userid: int) -> Optional[Tuple]:
    """获取用户的完整配置信息。返回 (char, api, preset, conv_id, stream)。"""
    command = "SELECT char, api, preset, conv_id,stream FROM user_config WHERE uid = ?"
    result = query_db(command, (userid,))
    return result[0] if result else None


def user_conv_id_get(user_id: int) -> int:
    """获取用户当前激活的对话ID。如果未找到或未设置，返回0。"""
    command = "SELECT conv_id FROM user_config WHERE uid = ?"
    result = query_db(command, (user_id,))
    return result[0][0] if result and result[0] and result[0][0] is not None else 0


def user_api_get(userid: int) -> str:
    """获取用户配置的API。如果未找到或未设置，返回空字符串。"""
    command = "SELECT api FROM user_config WHERE uid = ?"
    result = query_db(command, (userid,))
    return result[0][0] if result else ''


def user_stream_get(userid: int) -> Optional[str]:
    """获取用户是否开启流式传输 ('yes'/'no')。如果未找到配置，返回None。"""
    command = "SELECT stream FROM user_config WHERE uid = ?"
    result = query_db(command, (userid,))
    return result[0][0] if result else None


def user_stream_switch(userid: int) -> bool:
    """切换用户的流式传输设置 ('yes' <-> 'no')。返回操作是否成功。"""
    if user_stream_get(userid) == 'yes':
        command = "UPDATE  user_config set stream = 'no' WHERE uid = ?"
    else:
        command = "UPDATE  user_config set stream = 'yes' WHERE uid = ?"
    result = revise_db(command, (userid,))
    return result > 0


def user_config_update(userid: int, char: str, api: str, preset: str, conv_id: int) -> bool:
    """更新用户的角色、API、预设和当前对话ID。返回操作是否成功。"""
    command = "UPDATE user_config SET char = ?, api = ?, preset = ?, conv_id = ? WHERE uid = ?"
    result = revise_db(command, (char, api, preset, conv_id, userid))
    return result > 0


def user_config_arg_update(user_id: int, field: str, value: Any) -> bool:
    """更新用户配置表中的指定字段。返回操作是否成功。"""
    command = f"UPDATE user_config SET {field} = ? WHERE uid = ?"
    result = revise_db(command, (value, user_id))
    return result > 0


def user_config_create(userid: int) -> bool:
    """为新用户创建默认配置。返回操作是否成功。"""
    command = "INSERT INTO user_config (char, api, preset, uid,stream) VALUES (?, ?, ?, ?,?)"
    result = revise_db(command, (DEFAULT_CHAR, DEFAULT_API, DEFAULT_PRESET, userid, DEFAULT_STREAM))
    return result > 0


def user_config_check(userid: int) -> bool:
    """检查用户是否在 `users` 表中存在（通常用于判断是否是已知用户）。返回True表示存在。"""
    command = "SELECT uid FROM users WHERE uid = ?"
    result = query_db(command, (userid,))
    return bool(result)


def user_conversations_get(userid: int) -> Optional[List[Tuple]]:
    """获取用户未标记为删除的私聊对话列表。返回 (conv_id, character, summary) 元组的列表。"""
    command = "SELECT conv_id, character, summary FROM conversations WHERE user_id = ? AND delete_mark = 'no'"
    result = query_db(command, (userid,))
    return result if result else None


def user_info_get(userid: int) -> Optional[Tuple]:
    """获取用户的基本信息。返回 (first_name, last_name, account_tier, remain_frequency, balance, uid)。"""
    command = "SELECT first_name, last_name, account_tier, remain_frequency, balance,uid FROM users WHERE uid = ?"
    result = query_db(command, (userid,))
    return result[0] if result else None


def user_info_usage_get(userid: int, column_name: str) -> Any:
    """
    获取用户 `users` 表中指定列的信息。
    警告: 此函数直接将 column_name 拼接到SQL查询中，可能存在SQL注入风险。
          应确保调用时 column_name 来自受信任的、预定义的列名集合。
          未来版本建议重构此函数以避免直接拼接。

    :param userid: 用户ID。
    :param column_name: 要查询的列名。
    :return: 指定列的值，如果查询失败或用户不存在则返回0 (或根据列类型可能为其他默认值)。
    """
    # SQL注入风险警告：column_name 未经验证直接拼接到查询中。
    # 仅在 column_name 确定安全的情况下使用。
    allowed_columns = {'first_name', 'last_name', 'user_name', 'create_at', 'update_at', 
                       'input_tokens', 'output_tokens', 'account_tier', 'remain_frequency', 'balance'}
    if column_name not in allowed_columns:
        print(f"错误: user_info_usage_get 查询了不允许的列名: {column_name}")
        return 0 # 或者抛出异常

    command = f"SELECT {column_name} FROM users WHERE uid = ?"
    result = query_db(command, (userid,))
    return result[0][0] if result and result[0] else 0


def user_info_create(userid: int, first_name: str, last_name: str, user_name: str) -> bool:
    """创建用户信息"""
    create_at = str(datetime.datetime.now())
    command = "INSERT INTO users(uid,first_name,last_name,user_name,create_at,update_at,input_tokens,output_tokens,account_tier,remain_frequency,balance) VALUES (?, ?, ?, ?, ?, ?,?,?,?,?,?)"
    result = revise_db(command, (
        userid, first_name, last_name, user_name, create_at, create_at, 0, 0, 0, DEFAULT_FREQUENCY, DEFAULT_BALANCE))
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
        command = f"UPDATE users SET {field} = COALESCE({field}, 0) + ? WHERE uid = ?"
    else:
        command = f"UPDATE users SET {field} = ? WHERE uid = ?"
    result = revise_db(command, (value, userid))
    return result > 0


def user_frequency_free(value: int) -> bool:
    """为所有用户的 `remain_frequency` 增加指定值。返回操作是否影响了行。"""
    command = f"UPDATE users SET remain_frequency = COALESCE(remain_frequency, 0) + ?"
    result = revise_db(command, (value,))
    return result > 0


def _update_conversation_timestamp(conv_id: int, create_at: str, table_name: str) -> bool:
    """辅助函数：更新对话表的时间戳"""
    command = f"UPDATE {table_name} SET update_at = ? WHERE conv_id = ?"
    return revise_db(command, (create_at, conv_id)) > 0

def dialog_content_add(conv_id: int, role: str, turn_order: int, raw_content: str, processed_content: str, msg_id: Optional[int] = None,
                       chat_type: str = 'private') -> bool:
    """
    添加对话内容到相应的对话表，并更新对应会话表的 `update_at` 时间戳。

    :param conv_id: 会话ID。
    :param role: 角色（如 'user', 'assistant'）。
    :param turn_order: 对话轮次。
    :param raw_content: 原始对话内容。
    :param processed_content: 处理后的对话内容。
    :param msg_id: 消息ID，仅对私聊 ('private') 有效。
    :param chat_type: 对话类型，'private' 或 'group'。
    :return: 操作是否成功。
    """
    create_at = str(datetime.datetime.now())
    
    if chat_type == 'private':
        dialog_table = "dialogs"
        conversation_table = "conversations"
        if msg_id is None:
            print("错误: 私聊对话内容添加时 msg_id 不能为空。")
            return False
        insert_command = f"INSERT INTO {dialog_table} (conv_id, role, raw_content, turn_order, created_at, processed_content, msg_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
        params = (conv_id, role, raw_content, turn_order, create_at, processed_content, msg_id)
    elif chat_type == 'group':
        dialog_table = "group_user_dialogs"
        conversation_table = "group_user_conversations"
        insert_command = f"INSERT INTO {dialog_table} (conv_id, role, raw_content, turn_order, created_at, processed_content) VALUES (?, ?, ?, ?, ?, ?)"
        params = (conv_id, role, raw_content, turn_order, create_at, processed_content)
    else:
        print(f"错误: 未知的 chat_type '{chat_type}' 在 dialog_content_add 中。")
        return False

    result = revise_db(insert_command, params)
    if result:
        return _update_conversation_timestamp(conv_id, create_at, conversation_table)
    return False


def dialog_new_content_add(conv_id: int, turn: int) -> bool:
    """（似乎是未完成或特定用途的函数）在 `dialogs` 表中插入一条只有 conv_id 和 turn_order 的记录。返回操作是否成功。"""
    command = "INSERT INTO dialogs (conv_id,turn_order) values (?,?)"
    return revise_db(command, (conv_id, turn)) > 0


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


def dialog_turn_get(conv_id: int, chat_type: str = 'private') -> int:
    """
    获取指定会话的当前对话轮数。

    :param conv_id: 会话ID。
    :param chat_type: 对话类型，'private' 或 'group'。
    :return: 最大轮次数，如果不存在则返回 0。
    """
    if chat_type == 'private':
        table_name = "dialogs"
    elif chat_type == 'group':
        table_name = "group_user_dialogs"
    else:
        print(f"警告: 未知的 chat_type '{chat_type}' 在 dialog_turn_get 中，无法确定表名。")
        return 0
        
    command = f"SELECT MAX(turn_order) FROM {table_name} WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result[0][0] if result and result[0][0] is not None else 0


def dialog_content_load(conv_id: int, chat_type: str = 'private') -> Optional[List[Tuple]]:
    """
    加载指定会话的对话内容。

    :param conv_id: 会话ID。
    :param chat_type: 对话类型，'private' 或 'group'。其他类型将默认查询私聊对话表。
    :return: 对话内容列表 (role, turn_order, processed_content)，如果不存在则返回 None。
    """
    if chat_type == 'group':
        table_name = "group_user_dialogs"
    else: # 默认为 'private' 或其他未知类型也查私聊表
        table_name = "dialogs"
        if chat_type != 'private':
             print(f"警告: 未知的 chat_type '{chat_type}' 在 dialog_content_load 中，默认查询 '{table_name}' 表。")

    command = f"SELECT role, turn_order, processed_content FROM {table_name} WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result if result else None


def conversation_private_create(conv_id: int, userid: int, character: str, preset: str) -> bool:
    """创建一条新的私聊对话记录，并更新用户的 `update_at` 时间。返回操作是否成功。"""
    create_at = str(datetime.datetime.now())
    user_info_update(userid, 'update_at', create_at)
    command = "INSERT INTO conversations (conv_id, user_id, character, preset, create_at, update_at, delete_mark) VALUES (?, ?, ?, ?, ?, ?, 'yes')"
    result = revise_db(command, (conv_id, userid, character, preset, create_at, create_at))
    return result > 0


def conversation_private_save(conv_id: int) -> bool:
    """将私聊对话的 `delete_mark` 设置为 'no'，表示保存该对话。返回操作是否成功。"""
    command = "UPDATE conversations SET delete_mark = 'no' WHERE conv_id = ?"
    result = revise_db(command, (conv_id,))
    return result > 0


def conversation_private_get(conv_id: int) -> Optional[Tuple[str, str]]:
    """获取指定私聊对话的角色和预设。返回 (character, preset) 元组。"""
    command = "SELECT character, preset FROM conversations WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result[0] if result else None


def conversation_user_get(conv_id: int) -> Optional[int]:
    """获取指定私聊对话的用户ID。如果未找到，返回None。"""
    command = "SELECT user_id from conversations where conv_id = ?"
    result = query_db(command, (conv_id,))
    return result[0][0] if result and result[0] else None


def conversation_group_config_get(conv_id: int) -> Optional[Tuple[str, str]]:
    """获取指定群聊用户会话关联的群组的角色和预设。返回 (char, preset) 元组。"""
    command = "SELECT group_id FROM group_user_conversations WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    group_id = result[0][0]
    command = "SELECT char, preset FROM groups WHERE group_id = ?"
    result = query_db(command, (group_id,))
    return result[0] if result else None


def conversation_private_update(conv_id: int, char: str, preset: str) -> bool:
    """更新指定私聊对话的角色和预设。返回操作是否成功。"""
    command = "UPDATE conversations SET character = ?, preset = ? WHERE conv_id = ?"
    result = revise_db(command, (char, preset, conv_id))
    return result > 0


def conversation_private_arg_update(conv_id: int, field: str, value: Any, increment: bool = False) -> bool:
    """更新私聊对话表 (`conversations`) 中的指定字段。返回操作是否成功。"""
    if increment:
        command = f"UPDATE conversations SET {field} = COALESCE({field}, 0) + ? WHERE conv_id = ?"
    else:
        command = f"UPDATE conversations SET {field} = ? WHERE conv_id = ?"
    result = revise_db(command, (value, conv_id))
    return result > 0


def conversation_private_delete(conv_id: int) -> bool:
    """将指定私聊对话的 `delete_mark` 设置为 'yes'，标记为删除。返回操作是否成功。"""
    command = "UPDATE conversations SET delete_mark = ? WHERE conv_id = ?"
    result = revise_db(command, ('yes', conv_id))
    return result > 0


def conversation_private_check(conv_id: int) -> bool:
    """检查具有指定 conv_id 的私聊对话是否存在。返回True表示不存在，False表示存在。"""
    command = "SELECT conv_id FROM conversations WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return not bool(result)


def conversation_private_get_user(conv_id: int) -> Optional[int]:
    """获取指定私聊对话的用户ID。如果未找到，返回None。"""
    command = "SELECT user_id FROM conversations WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result[0][0] if result and result[0] else None


def conversation_private_summary_add(conv_id: int, summary: str) -> bool:
    """为指定私聊对话添加或更新总结。返回操作是否成功。"""
    command = "UPDATE conversations SET summary = ? WHERE conv_id = ?"
    result = revise_db(command, (summary, conv_id))
    return result > 0


def conversation_group_create(conv_id: int, user_id: int, user_name: str, group_id: int, group_name: str) -> bool:
    """为指定用户在指定群组中创建一条新的群聊用户会话记录，并更新群组的 `update_time`。返回操作是否成功。"""
    create_at = str(datetime.datetime.now())
    group_info_update(group_id, 'update_time', create_at)
    command = "INSERT INTO group_user_conversations (user_id, user_name, group_id, group_name, conv_id, create_at, delete_mark) VALUES (?, ?, ?, ?, ?, ?, 'no')"
    result = revise_db(command, (user_id, user_name, group_id, group_name, conv_id, create_at))
    return result > 0


def conversation_group_check(conv_id: int) -> bool:
    """检查具有指定 conv_id 且未标记删除的群聊用户会话是否存在。返回True表示不存在，False表示存在。"""
    command = "SELECT conv_id FROM group_user_conversations WHERE conv_id = ? AND delete_mark = 'no'"
    result = query_db(command, (conv_id,))
    return not bool(result)


def conversation_group_get(group_id: int, user_id: int) -> Optional[int]:
    """获取指定用户在指定群组中未标记删除的群聊用户会话ID (conv_id)。"""
    command = "SELECT conv_id FROM group_user_conversations WHERE group_id = ? AND user_id = ? AND delete_mark = 'no'"
    result = query_db(command, (group_id, user_id))
    return result[0][0] if result else None


def conversation_group_update(group_id: int, user_id: int, field: str, value: Any) -> bool:
    """更新指定用户在指定群组中未标记删除的群聊用户会话的指定字段。返回操作是否成功。"""
    command = f"UPDATE group_user_conversations SET {field} = ? WHERE group_id = ? AND user_id = ? AND delete_mark = 'no'"
    result = revise_db(command, (value, group_id, user_id))
    return result > 0


def conversation_group_delete(group_id: int, user_id: int) -> bool:
    """将指定用户在指定群组中的群聊用户会话标记为删除 (`delete_mark` = 'yes')。返回操作是否成功。"""
    command = "UPDATE group_user_conversations SET delete_mark = 'yes' WHERE group_id = ? AND user_id = ?"
    result = revise_db(command, (group_id, user_id))
    return result > 0


def conversation_turns_update(conv_id: int, turn_num: int, chat_type: str = 'private') -> bool:
    """
    更新指定会话的对话轮数。

    :param conv_id: 会话ID。
    :param turn_num: 新的对话轮数。
    :param chat_type: 对话类型，'private' 或 'group'。
    :return: 操作是否成功。
    """
    if chat_type == 'private':
        table = "conversations"
    elif chat_type == 'group':
        table = "group_user_conversations"
    else:
        print(f"警告: 未知的 chat_type '{chat_type}' 在 conversation_turns_update 中，无法更新轮数。")
        return False
    command = f"UPDATE {table} SET turns = ? WHERE conv_id = ?"
    result = revise_db(command, (turn_num, conv_id))
    return result > 0


def group_check_update(group_id: int) -> bool:
    """检查群组信息是否需要更新（基于上次更新时间是否超过5分钟）。返回True表示需要更新或群组不存在。"""
    command = "SELECT update_time FROM groups WHERE group_id = ?"
    result = query_db(command, (group_id,))
    if result:
        update_time = datetime.datetime.strptime(str(result[0][0]), "%Y-%m-%d %H:%M:%S.%f")
        return update_time < datetime.datetime.now() - datetime.timedelta(minutes=5)
    return True


def group_config_get(group_id: int) -> Optional[Tuple[str, str, str]]:
    """获取指定群组的配置 (api, char, preset)。"""
    command = "SELECT api, char, preset FROM groups WHERE group_id = ?"
    result = query_db(command, (group_id,))
    return result[0] if result else False


def group_admin_list_get(group_id: int) -> List[str]:
    """获取指定群组的管理员列表（从JSON字符串解析）。如果解析失败或无数据，返回空列表。"""
    try:
        command = "SELECT members_list FROM groups WHERE group_id = ?"
        result = query_db(command, (group_id,))
        return json.loads(result[0][0]) if result and result[0][0] else []
    except Exception as e:
        print(f"获取群管理员错误: {e}")
        return []


def group_keyword_get(group_id: int) -> List[str]:
    """获取指定群组的关键词列表（从JSON字符串解析）。如果解析失败或无数据，返回空列表。"""
    try:
        command = "SELECT keywords FROM groups WHERE group_id = ?"
        result = query_db(command, (group_id,))
        return json.loads(result[0][0]) if result and result[0][0] else []
    except Exception as e:
        print(f"获取群组关键词错误: {e}")
        return []


def group_keyword_set(group_id: int, keywords: List[str]) -> bool:
    """设置指定群组的关键词列表（序列化为JSON字符串存储）。返回操作是否成功。"""
    try:
        keywords_str = json.dumps(keywords, ensure_ascii=False)
        command = "UPDATE groups SET keywords = ? WHERE group_id = ?"
        result = revise_db(command, (keywords_str, group_id))
        return result > 0
    except Exception as e:
        print(f"设置群组关键词错误: {e}")
        return False


def group_info_create(group_id: int) -> bool:
    """为指定 group_id 创建一条新的群组记录，使用默认API、角色和预设。返回操作是否成功。"""
    command = "INSERT INTO groups (group_id, api, char, preset) VALUES (?, ?, ?, ?)"
    result = revise_db(command, (group_id, DEFAULT_API, DEFAULT_CHAR, DEFAULT_PRESET))
    return result > 0


def group_dialog_add(msg_id: int, group_id: int) -> bool:
    """在 `group_dialogs` 表中添加一条群聊消息记录。返回操作是否成功。"""
    command = "INSERT INTO group_dialogs (msg_id, group_id) VALUES (?, ?)"
    result = revise_db(command, (msg_id, group_id))
    return result > 0


def group_dialog_update(msg_id: int, field: str, value: Any, group_id: int) -> bool:
    """更新 `group_dialogs` 表中指定消息的指定字段。返回操作是否成功。"""
    command = f"UPDATE group_dialogs SET {field} = ? WHERE msg_id = ? AND group_id = ?"
    result = revise_db(command, (value, msg_id, group_id))
    return result > 0


def group_dialog_get(group_id: int, num: int) -> List[Tuple[Optional[str], Optional[str], Optional[str]]]:
    """获取指定 group_id 的最新 num 条群聊消息 (msg_text, msg_user_name, processed_response)，按 msg_id 降序排序。"""
    command = "SELECT msg_text, msg_user_name, processed_response FROM group_dialogs WHERE group_id = ? ORDER BY msg_id DESC LIMIT ?"
    result = query_db(command, (group_id, num))
    return result if result else []


def group_info_update(group_id: int, field: str, value: Any) -> bool:
    """更新 `groups` 表中指定群组的指定字段。返回操作是否成功。"""
    command = f"UPDATE groups SET {field} = ? WHERE group_id = ?"
    result = revise_db(command, (value, group_id))
    return result > 0


def group_rate_get(group_id: int) -> float:
    """获取指定群组的回复频率 (rate)。如果未设置或查询失败，返回默认值0.05。"""
    command = f"SELECT rate from groups where group_id = ?"
    result = query_db(command, (group_id,))
    return result[0][0] if result and result[0] and result[0][0] is not None else 0.05


# 应用退出时关闭所有数据库连接
def close_all_connections():
    """关闭连接池中的所有数据库连接。应在应用退出时调用。"""
    db_pool.close_all()
