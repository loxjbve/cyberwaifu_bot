import datetime
import json
import logging
import os
import sqlite3
import threading
from sqlite3 import Error
from typing import Any, List, Optional, Tuple, Union

from utils.config_utils import (
    get_config,
    get_default_api,
    get_default_balance,
    get_default_char,
    get_default_frequency,
    get_default_preset,
    get_default_stream,
    project_root,
)
from utils.logging_utils import setup_logging
from utils.schema_migration import check_and_migrate_database_schema

setup_logging()
logger = logging.getLogger(__name__)

from db.runtime import (
    close_database_runtime,
    get_database_runtime,
    manual_wal_checkpoint as runtime_manual_wal_checkpoint,
)


class _RuntimePoolProxy:
    def get_connection(self) -> Tuple[Optional[sqlite3.Connection], int]:
        runtime = get_database_runtime()
        runtime.initialize()
        if not runtime.pool:
            return None, -1
        return runtime.pool.get_connection()

    def release_connection(self, index: int) -> None:
        runtime = get_database_runtime()
        if runtime.pool:
            runtime.pool.release_connection(index)

    def close_all(self) -> None:
        close_database_runtime()

    def trigger_wal_checkpoint(self) -> bool:
        return runtime_manual_wal_checkpoint()


db_pool = _RuntimePoolProxy()



def init_database_if_not_exists():
    """
    检查 data/data.db 是否存在，如果不存在则用 data/database.sql 初始化数据库。
    同时检查所需的表是否都存在，如果有缺失则创建。
    现在还会检查表结构是否符合 database.sql，如果不符合则进行迁移。
    """
    # 使用绝对路径，确保无论从哪个目录运行都能找到文件
    db_path = os.path.join(project_root, "data", "data.db")
    sql_path = os.path.join(project_root, "data", "database.sql")
    
    # 如果数据库文件不存在，创建新数据库
    if not os.path.exists(db_path):
        logger.info("检测到 data.db 不存在，正在初始化数据库...")
        try:
            with open(sql_path, "r", encoding="utf-8") as f:
                sql_script = f.read()
            conn = sqlite3.connect(db_path)
            with conn:
                conn.executescript(sql_script)
            conn.close()
            logger.info("数据库初始化完成！")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}", exc_info=True)
            raise RuntimeError(f"数据库初始化失败: {e}")
    
    # 使用新的表结构检查和迁移功能
    try:
        logger.info("开始检查和迁移数据库表结构...")
        migration_success = check_and_migrate_database_schema()
        
        if migration_success:
            logger.info("数据库表结构检查和迁移完成")
        else:
            logger.warning("数据库表结构迁移过程中出现问题，但数据库仍可使用")
            
    except Exception as e:
        logger.error(f"数据库表结构检查和迁移失败: {e}", exc_info=True)
        # 如果新的迁移功能失败，回退到原来的简单检查方式
        logger.info("回退到简单的表存在性检查...")
        try:
            _fallback_table_check(db_path, sql_path)
        except Exception as fallback_error:
            logger.error(f"回退检查也失败: {fallback_error}", exc_info=True)
            raise RuntimeError(f"数据库表结构检查失败: {e}")
    
    # 检查和创建索引
    try:
        logger.info("开始检查和创建数据库索引...")
        _check_and_create_indexes(db_path, sql_path)
        logger.info("数据库索引检查和创建完成")
    except Exception as e:
        logger.error(f"数据库索引检查和创建失败: {e}", exc_info=True)
        # 索引创建失败不应该阻止应用启动，只记录警告
        logger.warning("索引创建失败，但不影响基本功能")


def _fallback_table_check(db_path: str, sql_path: str):
    """
    回退的表存在性检查方法（原来的逻辑）
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取sql文件中的所有CREATE TABLE语句
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()
        create_table_statements = [stmt.strip() for stmt in sql_content.split(';') 
                                 if 'CREATE TABLE' in stmt.upper()]
    
    # 获取当前数据库中的所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = set(table[0] for table in cursor.fetchall())
    
    # 检查每个CREATE TABLE语句
    for stmt in create_table_statements:
        # 提取表名 - 使用大小写不敏感的方式
        stmt_upper = stmt.upper()
        if 'CREATE TABLE' in stmt_upper:
            # 找到CREATE TABLE的位置，然后提取表名
            create_table_pos = stmt_upper.find('CREATE TABLE')
            table_part = stmt[create_table_pos + len('CREATE TABLE'):].strip()
            table_name = table_part.split('(')[0].strip()
            
            if table_name not in existing_tables:
                logger.warning(f"检测到缺失表 {table_name}，正在创建...")
                try:
                    cursor.execute(stmt)
                    conn.commit()
                    logger.info(f"表 {table_name} 创建成功")
                except sqlite3.Error as e:
                    logger.error(f"创建表 {table_name} 失败: {e}")
                    raise
    
    conn.close()


def _check_and_create_indexes(db_path: str, sql_path: str):
    """
    检查和创建数据库索引
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 读取SQL文件内容
        with open(sql_path, "r", encoding="utf-8") as f:
            sql_content = f.read()
        
        # 提取所有CREATE INDEX语句
        import re
        index_statements = re.findall(
            r'create\s+index\s+[^;]+;', 
            sql_content, 
            re.IGNORECASE | re.DOTALL
        )
        
        # 获取当前数据库中的所有索引
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';")
        existing_indexes = set(index[0] for index in cursor.fetchall())
        
        # 检查每个索引语句
        for stmt in index_statements:
            stmt = stmt.strip()
            if not stmt:
                continue
                
            # 提取索引名
            index_match = re.search(r'create\s+index\s+(\w+)', stmt, re.IGNORECASE)
            if index_match:
                index_name = index_match.group(1)
                
                if index_name not in existing_indexes:
                    logger.info(f"检测到缺失索引 {index_name}，正在创建...")
                    try:
                        cursor.execute(stmt)
                        conn.commit()
                        logger.info(f"索引 {index_name} 创建成功")
                    except sqlite3.Error as e:
                        logger.error(f"创建索引 {index_name} 失败: {e}")
                        # 索引创建失败不应该中断整个过程
                        continue
                else:
                    logger.debug(f"索引 {index_name} 已存在，跳过创建")
    
    finally:
        conn.close()


class DatabaseConnectionPool:
    """
    数据库连接池，使用单例模式实现。

    提供数据库连接的获取、释放和管理功能，确保线程安全。
    """

    _instance: Optional["DatabaseConnectionPool"] = None
    _lock = threading.Lock()

    def __new__(
        cls, db_file: Optional[str] = None, max_connections: Optional[int] = None
    ) -> "DatabaseConnectionPool":
        """
        实现单例模式，确保全局只有一个连接池实例。

        Args:
            db_file: 数据库文件路径，如果为None则使用配置中的路径
            max_connections: 连接池中的最大连接数，如果为None则使用配置中的值

        Returns:
            DatabaseConnectionPool: 单例实例
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseConnectionPool, cls).__new__(cls)
                # 初始化实例属性
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_file: Optional[str] = None, max_connections: Optional[int] = None):
        """
        初始化数据库连接池。
        
        Args:
            db_file: 数据库文件路径，如果为None则使用配置中的路径
            max_connections: 连接池中的最大连接数，如果为None则使用配置中的值
        """
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        # 优先使用传入的参数，其次是环境变量，最后是配置文件
        if db_file is None:
            db_file = os.environ.get("DB_PATH", get_config("database.default_path"))

        # 确保数据库路径是绝对路径
        if not os.path.isabs(db_file):
            db_file = os.path.join(project_root, db_file.lstrip("./"))

        # 获取最大连接数
        if max_connections is None:
            max_connections = get_config("database.max_connections", 5)
            
        self.db_file = db_file
        self.max_connections = max_connections
        self.connections: List[sqlite3.Connection] = []
        self.connection_locks: List[threading.Lock] = []
        self._initialized = True
        self.initialize_pool()

    def initialize_pool(self):
        """
        根据 max_connections 初始化连接池中的数据库连接。
        """
        if self.max_connections is None:
            # 如果 max_connections 未设置，则提供一个默认值或记录错误
            logger.warning("max_connections 未在连接池初始化前设置，默认为 5")
            self.max_connections = 5

        for _ in range(self.max_connections):
            try:
                # 添加并发优化参数
                conn = sqlite3.connect(
                    self.db_file, 
                    check_same_thread=False,
                    timeout=30.0  # 30秒超时
                )
                # 启用 WAL 模式以支持并发读写
                conn.execute("PRAGMA journal_mode=WAL;")
                # 设置忙等待超时
                conn.execute("PRAGMA busy_timeout=30000;")
                # 优化同步模式
                conn.execute("PRAGMA synchronous=NORMAL;")
                # 启用外键约束
                conn.execute("PRAGMA foreign_keys=ON;")
                conn.commit()
                
                self.connections.append(conn)
                self.connection_locks.append(threading.Lock())
            except Error as e:
                print(f"初始化连接池时发生错误: {e}")
                print(f"数据库：{self.db_file}")

    def get_connection(self) -> Tuple[Optional[sqlite3.Connection], int]:
        """
        从连接池中获取一个可用的数据库连接及其索引。

        如果所有池中连接都在使用，则尝试创建一个临时连接。

        Returns:
            Tuple[Optional[sqlite3.Connection], int]: 一个元组 (connection, index)。
                如果成功获取连接，connection 是 sqlite3.Connection 对象，index 是连接在池中的索引（临时连接为 -1）。
                如果获取失败，connection 是 None，index 是 -1。
        """
        for i, lock in enumerate(self.connection_locks):
            if lock.acquire(blocking=False):
                return self.connections[i], i
        # 如果所有连接都在使用中，创建一个临时连接
        try:
            temp_conn = sqlite3.connect(
                self.db_file, 
                check_same_thread=False,
                timeout=30.0
            )
            # 为临时连接也设置相同的优化参数
            temp_conn.execute("PRAGMA journal_mode=WAL;")
            temp_conn.execute("PRAGMA busy_timeout=30000;")
            temp_conn.execute("PRAGMA synchronous=NORMAL;")
            temp_conn.execute("PRAGMA foreign_keys=ON;")
            temp_conn.commit()
            return temp_conn, -1  # -1 表示这是一个临时连接
        except Error as e:
            print(f"创建临时连接时发生错误: {e}")
            return None, -1

    def release_connection(self, index: int):
        """
        释放连接池中指定索引的连接锁，使其可被其他线程使用。

        此方法不关闭连接，仅释放锁。

        Args:
            index: 要释放的连接在池中的索引
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

    def trigger_wal_checkpoint(self) -> bool:
        """
        手动触发 WAL 检查点，将 WAL 文件中的数据合并到主数据库文件。

        Returns:
            bool: 操作是否成功
        """
        conn, conn_index = self.get_connection()
        if not conn:
            logger.error("无法获取数据库连接以触发 WAL 检查点")
            return False
        
        try:
            # 使用 TRUNCATE 模式可以最高效地回收 WAL 文件空间
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            logger.info("成功触发 WAL 检查点")
            return True
        except sqlite3.Error as e:
            logger.error(f"触发 WAL 检查点失败: {e}")
            return False
        finally:
            if conn_index >= 0:
                self.release_connection(conn_index)
            else:
                if conn:
                    conn.close()


# 创建全局连接池实例前，先确保数据库存在


def create_connection() -> Optional[sqlite3.Connection]:
    """
    获取一个数据库连接。

    Note:
        主要为兼容旧代码，推荐直接使用连接池。

    Returns:
        Optional[sqlite3.Connection]: 数据库连接对象
    """
    runtime = get_database_runtime()
    runtime.initialize()
    if not runtime.pool:
        return None
    conn, _ = runtime.pool.get_connection()
    return conn


def execute_db_operation(operation_type: str, command: str, params: Tuple = ()):
    """
    执行数据库操作的通用函数。

    Args:
        operation_type: 操作类型，可以是 "query" 或 "update"
        command: 要执行的 SQL 命令
        params: SQL 命令的参数

    Returns:
        Union[List[Any], int]: 如果是查询操作，返回结果列表；如果是更新操作，返回受影响的行数。
            发生错误时，查询返回空列表，更新返回0。
    """
    runtime = get_database_runtime()
    if operation_type == "query":
        return runtime.query(command, params)
    return runtime.execute(command, params)
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
            if conn:  # 确保临时连接存在才关闭
                conn.close()


def execute_raw_sql(command: str) -> Union[List[Any], int, str]:
    """
    直接执行原始SQL命令，不进行参数化。
    [高风险] 此函数直接执行SQL，可能容易受到SQL注入攻击。只能用于内部、受信任的SQL。

    Args:
        command: 要执行的原始SQL命令。

    Returns:
        Union[List[Any], int, str]: 查询返回结果列表，更新返回受影响行数，错误则返回错误信息字符串。
    """
    return get_database_runtime().execute_raw(command)
    conn, conn_index = db_pool.get_connection()
    if not conn:
        error_msg = f"数据库错误: 无法获取连接以执行原始SQL: {command}"
        print(error_msg)
        return error_msg

    try:
        cursor = conn.cursor()
        # 对于可能返回结果的非SELECT语句（如PRAGMA），使用executescript可能更健壮
        # 但executescript不支持fetchall，所以我们坚持使用execute
        cursor.execute(command)

        # 检查是否是查询操作
        is_query = command.strip().upper().startswith("SELECT")
        
        if not is_query:
            # 对于非查询操作（INSERT, UPDATE, DELETE, etc.）
            conn.commit()
            result = cursor.rowcount
        else:
            # 对于查询操作
            result = cursor.fetchall()
            # 如果是查询但没有返回列（例如，PRAGMA命令），fetchall会返回空列表，
            # 但我们可能需要一个成功的指示。
            if not result and cursor.description is None:
                return "Command executed successfully with no data returned."

        return result
    except sqlite3.Error as e:
        error_msg = f"数据库原始SQL操作失败: {command} 错误: {e}"
        print(error_msg)
        # 对于失败的事务，尝试回滚
        try:
            conn.rollback()
        except sqlite3.Error as rb_e:
            print(f"回滚失败: {rb_e}")
        return error_msg
    finally:
        if conn_index >= 0:  # 如果是连接池中的连接，释放它
            db_pool.release_connection(conn_index)
        else:  # 如果是临时连接，关闭它
            if conn:
                conn.close()

def revise_db(command: str, params: Tuple = ()) -> int:
    """
    执行数据库更新操作。

    Args:
        command: SQL 更新命令
        params: SQL 命令的参数

    Returns:
        int: 受影响的行数
    """
    from typing import cast
    return cast(int, execute_db_operation("update", command, params))


def query_db(command: str, params: Tuple = ()) -> List[Any]:
    """
    执行数据库查询操作。

    Args:
        command: SQL 查询命令
        params: SQL 命令的参数

    Returns:
        List[Any]: 查询结果列表
    """
    from typing import cast
    return cast(List[Any], execute_db_operation("query", command, params))

def user_profile_get(userid: int) -> Optional[list]:
    """
    获取用户的完整个人资料信息。

    Args:
        userid: 用户ID

    Returns:
        Optional[dict]: 包含用户画像的字典，如果未找到则返回None
    """
    command = "SELECT * FROM user_profiles WHERE user_id = ?"
    result = query_db(command, (userid,))
    
    if result:
        profiles = []
        for i in result:
            profiles.append({
                "group_id": i[1],
                "user_profile": str(i[2]),
            })
        return profiles
    else:
        return None


def user_has_profile(user_id: int) -> bool:
    """检查用户是否存在用户画像。"""
    command = "SELECT 1 FROM user_profiles WHERE user_id = ? LIMIT 1"
    result = query_db(command, (user_id,))
    return bool(result)


def group_has_profile(group_id: int) -> bool:
    """检查群组是否存在用户画像。"""
    command = "SELECT 1 FROM user_profiles WHERE group_id = ? LIMIT 1"
    result = query_db(command, (group_id,))
    return bool(result)


def group_profiles_get(group_id: int) -> List[dict]:
    """获取指定群组的所有用户画像。"""
    command = """
        SELECT up.user_id, up.profile_json, u.user_name, u.first_name, u.last_name
        FROM user_profiles up
        JOIN users u ON up.user_id = u.uid
        WHERE up.group_id = ?
    """
    results = query_db(command, (group_id,))
    profiles = []
    for row in results:
        profiles.append({
            "user_id": row[0],
            "profile_json": row[1],
            "user_name": row[2],
            "first_name": row[3],
            "last_name": row[4]
        })
    return profiles


def group_profile_update_or_create(group_id: int, user_id: int, profile_json: str) -> bool:
    """更新或创建群组中的用户画像。"""
    now = str(datetime.datetime.now())
    # 检查记录是否存在
    check_command = "SELECT 1 FROM user_profiles WHERE group_id = ? AND user_id = ?"
    exists = query_db(check_command, (group_id, user_id))

    if exists:
        # 更新
        command = "UPDATE user_profiles SET profile_json = ?, last_updated = ? WHERE group_id = ? AND user_id = ?"
        params = (profile_json, now, group_id, user_id)
    else:
        # 插入
        command = "INSERT INTO user_profiles (group_id, user_id, profile_json, last_updated) VALUES (?, ?, ?, ?)"
        params = (group_id, user_id, profile_json, now)
    
    result = revise_db(command, params)
    return result > 0


def user_config_get(userid: int) -> dict:
    """
    获取用户的完整配置信息。

    Args:
        userid: 用户ID

    Returns:
        dict: 包含 char, api, preset, conv_id, stream, nick, chat_mode 的配置字典
    """
    command = (
        "SELECT char, api, preset, conv_id,stream,nick,chat_mode FROM user_config WHERE uid = ?"
    )
    result = query_db(command, (userid,))
    return (
        {
            "char": result[0][0],
            "api": result[0][1],
            "preset": result[0][2],
            "conv_id": result[0][3],
            "stream": result[0][4],
            "nick": result[0][5],
            "chat_mode": result[0][6] or "v1",
        }
        if result
        else {}
    )




def user_stream_get(userid: int) -> Optional[bool]:
    """
    获取用户是否开启流式传输。

    Args:
        userid: 用户ID

    Returns:
        Optional[bool]: 是否开启流式传输，如果未找到配置则返回None
    """
    command = "SELECT stream FROM user_config WHERE uid = ?"
    result = query_db(command, (userid,))
    return True if result[0][0] == "yes" else False



def user_config_arg_update(user_id: int, field: str, value: Any) -> bool:
    """
    更新用户配置表中的指定字段。

    Args:
        user_id: 用户ID
        field: 要更新的字段名
        value: 新的字段值

    Returns:
        bool: 操作是否成功
    """
    command = f"UPDATE user_config SET {field} = ? WHERE uid = ?"
    result = revise_db(command, (value, user_id))
    return result > 0


def user_config_create(userid: int, nick: Optional[str] = None) -> bool:
    """
    为新用户创建默认配置。如果用户已存在，则不执行任何操作。

    Args:
        userid: 用户ID
        nick: 用户的昵称 (可选)

    Returns:
        bool: 操作是否成功
    """
    command = (
        "INSERT OR IGNORE INTO user_config (char, api, preset, uid, stream, nick, chat_mode) VALUES (?, ?, ?, ?, ?, ?, 'v1')"
    )
    params = (
        get_default_char(),
        get_default_api(),
        get_default_preset(),
        userid,
        get_default_stream(),
        nick,
    )
    result = revise_db(command, params)
    return result >= 0  # IGNORE 成功时返回0，所以用 >= 0 判断


def user_info_check(userid: int) -> bool:
    """检查用户是否在 `users` 表中存在（通常用于判断是否是已知用户）。返回True表示存在。"""
    command = "SELECT uid FROM users WHERE uid = ?"
    result = query_db(command, (userid,))
    return bool(result)




def user_all_conversations_get(userid: int) -> Optional[List[Tuple]]:
    """获取用户所有的私聊对话列表，包括已删除的。返回 (conv_id, character, summary) 元组的列表。"""
    command = "SELECT conv_id, character, summary,update_at,turns FROM conversations WHERE user_id = ?"
    result = query_db(command, (userid,))
    return result if result else None

def user_conversations_get_for_dialog(userid: int) -> Optional[List[Tuple]]:
    """获取用户未标记为删除的私聊对话列表，用于dialog命令。返回 (conv_id, character, turns, update_at, summary) 元组的列表。"""
    command = "SELECT conv_id, character, turns, update_at, summary FROM conversations WHERE user_id = ? AND delete_mark = 'no' ORDER BY update_at DESC"
    result = query_db(command, (userid,))
    return result if result else None


def user_conversations_count_update(user_id: int) -> bool:
    """
    重新计算并更新用户的私聊对话总数。

    Args:
        user_id: 用户ID

    Returns:
        bool: 操作是否成功
    """
    # 使用 user_all_conversations_get 获取所有对话列表
    conversations = user_all_conversations_get(user_id)
    count = len(conversations) if conversations else 0
    
    # 使用 user_info_update 更新 users 表中的 conversations 字段
    return user_info_update(user_id, 'conversations', count)

def user_info_get(userid: int) -> dict:
    """获取用户的基本信息。返回 (first_name, last_name, user_name, account_tier, remain_frequency, balance, uid)。"""
    command = "SELECT first_name, last_name, user_name, account_tier, remain_frequency, balance, uid FROM users WHERE uid = ?"
    result = query_db(command, (userid,))
    if result:
        return {
            "first_name": result[0][0],
            "last_name": result[0][1],
            "user_name": result[0][2],
            "account_tier": result[0][3],
            "remain_frequency": result[0][4],
            "balance": result[0][5],
            "uid": result[0][6]
        }
    else:
        return {}




def user_info_create(
    userid: int, first_name: str, last_name: str, user_name: str
) -> bool:
    """创建用户信息"""
    create_at = str(datetime.datetime.now())
    command = "INSERT INTO users(uid,first_name,last_name,user_name,create_at,update_at,input_tokens,output_tokens,account_tier,remain_frequency,balance) VALUES (?, ?, ?, ?, ?, ?,?,?,?,?,?)"
    result = revise_db(
        command,
        (
            userid,
            first_name,
            last_name,
            user_name,
            create_at,
            create_at,
            0,
            0,
            0,
            get_default_frequency(),
            get_default_balance(),
        ),
    )
    return result > 0


def user_info_update(userid, field: str, value: Any, increment: bool = False) -> bool:
    """
    更新用户信息
    :param userid: 用户ID
    :param field: 需要更新的字段名
    :param value: 更新值或增量值
    :param increment: 是否为增量更新，默认为 False（直接设置值）
    :return: 更新是否成功
    """
    try:
        # 尝试转换为整数，如果成功则按uid处理
        uid = int(userid)
        if increment:
            command = (
                f"UPDATE users SET {field} = COALESCE({field}, 0) + ? WHERE uid = ?"
            )
        else:
            command = f"UPDATE users SET {field} = ? WHERE uid = ?"
        userid = uid
    except ValueError:
        # 不是数字则按用户名处理，转换为小写并去除可能的前缀
        userid = str(userid).lower()[1:] if len(str(userid)) > 1 else ""
        if increment:
            command = f"UPDATE users SET {field} = COALESCE({field}, 0) + ? WHERE LOWER(user_name) = ?"
        else:
            command = f"UPDATE users SET {field} = ? WHERE LOWER(user_name) = ?"
    result = revise_db(command, (value, userid))
    return result > 0




def _update_conversation_timestamp(
    conv_id: int, create_at: str, table_name: str
) -> bool:
    """辅助函数：更新对话表的时间戳"""
    command = f"UPDATE {table_name} SET update_at = ? WHERE conv_id = ?"
    return revise_db(command, (create_at, conv_id)) > 0


def dialog_content_add(
    conv_id: int,
    role: str,
    turn_order: int,
    raw_content: str,
    processed_content: str,
    msg_id: Optional[int] = None,
    chat_type: str = "private",
) -> bool:
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

    if chat_type == "private":
        dialog_table = "dialogs"
        conversation_table = "conversations"
        if msg_id is None:
            print("错误: 私聊对话内容添加时 msg_id 不能为空。")
            return False
        insert_command = f"INSERT INTO {dialog_table} (conv_id, role, raw_content, turn_order, created_at, processed_content, msg_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
        params = (
            conv_id,
            role,
            raw_content,
            turn_order,
            create_at,
            processed_content,
            msg_id,
        )
    elif chat_type == "group":
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




def dialog_turn_get(conv_id: int, chat_type: str = "private") -> int:
    """
    获取指定会话的当前对话轮数。

    :param conv_id: 会话ID。
    :param chat_type: 对话类型，'private' 或 'group'。
    :return: 最大轮次数，如果不存在则返回 0。
    """
    if chat_type == "private":
        table_name = "dialogs"
    elif chat_type == "group":
        table_name = "group_user_dialogs"
    else:
        print(
            f"警告: 未知的 chat_type '{chat_type}' 在 dialog_turn_get 中，无法确定表名。"
        )
        return 0

    command = f"SELECT MAX(turn_order) FROM {table_name} WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result[0][0] if result and result[0][0] is not None else 0


def dialog_content_load(
    conv_id: int, chat_type: str = "private",raw:bool=False
) -> Optional[List[Tuple]]:
    """
    加载指定会话的对话内容。

    Args:
        conv_id: 会话ID
        chat_type: 对话类型，'private' 或 'group'，其他类型将默认查询私聊对话表
        raw: 是否返回原始内容，默认为False，返回处理后的内容
    Returns:
        Optional[List[Tuple]]: 对话内容列表 (role, turn_order, processed_content)，如果不存在则返回None
    """
    if chat_type == "group":
        table_name = "group_user_dialogs"
    else:  # 默认为 'private' 或其他未知类型也查私聊表
        table_name = "dialogs"
        if chat_type != "private":
            print(
                f"警告: 未知的 chat_type '{chat_type}' 在 dialog_content_load 中，默认查询 '{table_name}' 表。"
            )
    if raw:
        command = f"SELECT role, turn_order, raw_content FROM {table_name} WHERE conv_id = ?"
    else:
        command = f"SELECT role, turn_order, processed_content FROM {table_name} WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result if result else None




def dialog_summary_get(conv_id: int) -> Optional[list]:
    """
    获取指定会话的总结。

    Args:
        conv_id (int): 会话ID。

    Returns:
        Optional[list]: 总结内容的列表，每个元素为字典，包含 'summary_area' 和 'content' 字段。
                        如果没有找到总结，则返回 None。

    示例:
        >>> dialog_summary_get(123456)
        [
            {'summary_area': '1-30', 'content': '时间地点人物事件'},
            {'summary_area': '31-60', 'content': '时间地点人物事件'}
        ]
        >>> dialog_summary_get(999999)
        None
    """
    command = "SELECT summary_area,content FROM dialog_summary WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    if result:
        # 假设 summary_area, content 两个字段
        return [{"summary_area": row[0], "content": row[1]} for row in result]
    else:
        return None
        
def dialog_summary_location_get(conv_id: int) -> Optional[int]:
    """
    获取指定对话已总结到的最大轮数。

    Args:
        conv_id (int): 会话ID。

    Returns:
        Optional[int]: 已总结到的最大轮数。如果没有总结记录，返回None。
    """
    summaries = dialog_summary_get(conv_id)
    if not summaries:
        return None
        
    max_turn = 0
    for summary in summaries:
        # 解析summary_area字段,格式为"起始轮数-结束轮数"
        try:
            end_turn = int(summary['summary_area'].split('-')[1])
            max_turn = max(max_turn, end_turn)
        except (ValueError, IndexError):
            continue
            
    return max_turn if max_turn > 0 else None

def dialog_summary_add(conv_id: int, summary_area: str, content: str) -> bool:
    """
    向指定会话添加总结。

    Args:
        conv_id (int): 会话ID。
        summary_area (str): 总结区域标识，例如 '1-30' 表示第1到30轮对话的总结。
        content (str): 总结内容。

    Returns:
        bool: 如果插入成功返回 True，否则返回 False。
    """
    command = "INSERT INTO dialog_summary (conv_id, summary_area, content) VALUES (?, ?, ?)"
    result = revise_db(command, (conv_id, summary_area, content))
    return result > 0

def conversation_private_create(
    conv_id: int, userid: int, character: str, preset: str
) -> bool:
    """
    创建一条新的私聊对话记录，并更新用户的update_at时间。

    Args:
        conv_id: 会话ID
        userid: 用户ID
        character: 角色名称
        preset: 预设名称

    Returns:
        bool: 操作是否成功
    """
    create_at = str(datetime.datetime.now())
    user_info_update(userid, "update_at", create_at)
    command = "INSERT INTO conversations (conv_id, user_id, character, preset, create_at, update_at, delete_mark) VALUES (?, ?, ?, ?, ?, ?, 'yes')"
    result = revise_db(
        command, (conv_id, userid, character, preset, create_at, create_at)
    )
    return result > 0




def conversation_private_get(conv_id: int) -> Optional[Tuple[str, str]]:
    """
    获取指定私聊对话的角色和预设。

    Args:
        conv_id: 会话ID

    Returns:
        Optional[Tuple[str, str]]: (character, preset) 元组，如果未找到则返回None
    """
    command = "SELECT character, preset FROM conversations WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return result[0] if result else None








def conversation_private_arg_update(
    conv_id: int, field: str, value: Any, increment: bool = False
) -> bool:
    """
    更新私聊对话表(conversations)中的指定字段。

    Args:
        conv_id: 会话ID
        field: 要更新的字段名
        value: 新的字段值或增量值
        increment: 是否为增量更新，默认为False

    Returns:
        bool: 操作是否成功
    """
    if increment:
        command = f"UPDATE conversations SET {field} = COALESCE({field}, 0) + ? WHERE conv_id = ?"
    else:
        command = f"UPDATE conversations SET {field} = ? WHERE conv_id = ?"
    result = revise_db(command, (value, conv_id))
    return result > 0


def conversation_private_delete(conv_id: int) -> bool:
    """
    将指定私聊对话的delete_mark设置为'yes'，标记为删除。

    Args:
        conv_id: 会话ID

    Returns:
        bool: 操作是否成功
    """
    command = "UPDATE conversations SET delete_mark = ? WHERE conv_id = ?"
    result = revise_db(command, ("yes", conv_id))
    return result > 0


def conversation_private_check(conv_id: int) -> bool:
    """
    检查具有指定conv_id的私聊对话是否存在。

    Args:
        conv_id: 会话ID

    Returns:
        bool: True表示不存在，False表示存在
    """
    command = "SELECT conv_id FROM conversations WHERE conv_id = ?"
    result = query_db(command, (conv_id,))
    return not bool(result)






def conversation_group_get(group_id: int, user_id: int) -> Optional[int]:
    """
    获取指定用户在指定群组中未标记删除的群聊用户会话ID。

    Args:
        group_id: 群组ID
        user_id: 用户ID

    Returns:
        Optional[int]: 会话ID，如果未找到则返回None
    """
    command = "SELECT conv_id FROM group_user_conversations WHERE group_id = ? AND user_id = ? AND delete_mark = 'no'"
    result = query_db(command, (group_id, user_id))
    return result[0][0] if result else None


def conversation_group_update(
    group_id: int, user_id: int, field: str, value: Any
) -> bool:
    """
    更新指定用户在指定群组中未标记删除的群聊用户会话的指定字段。

    Args:
        group_id: 群组ID
        user_id: 用户ID
        field: 要更新的字段名
        value: 新的字段值

    Returns:
        bool: 操作是否成功
    """
    command = f"UPDATE group_user_conversations SET {field} = COALESCE({field}, 0) + ? WHERE group_id = ? AND user_id = ? AND delete_mark = 'no'"
    result = revise_db(command, (value, group_id, user_id))
    return result > 0





def group_check_update(group_id: int) -> bool:
    """
    检查群组信息是否需要更新（基于上次更新时间是否超过5分钟）。

    Args:
        group_id: 群组ID

    Returns:
        bool: True表示需要更新或群组不存在，False表示不需要更新
    """
    command = "SELECT update_time FROM groups WHERE group_id = ?"
    result = query_db(command, (group_id,))
    if result:
        # 尝试解析带微秒的时间格式，如果失败则尝试不带微秒的格式
        time_str = str(result[0][0])
        try:
            update_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            update_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        return update_time < datetime.datetime.now() - datetime.timedelta(minutes=5)
    return True


def group_config_get(group_id: int) -> Optional[Tuple[str, str, str, str]]:
    """
    获取指定群组的配置。

    Args:
        group_id: 群组ID

    Returns:
        Optional[Tuple[str, str, str, str]]: (api, char, preset, chat_mode) 元组，如果未找到则返回None
    """
    command = "SELECT api, char, preset, chat_mode FROM groups WHERE group_id = ?"
    result = query_db(command, (group_id,))
    return result[0] if result else None


def group_config_arg_update(group_id: int, field: str, value: Any) -> bool:
    """
    更新群组配置表中的指定字段。

    Args:
        group_id: 群组ID
        field: 要更新的字段名
        value: 新的字段值

    Returns:
        bool: 操作是否成功
    """
    command = f"UPDATE groups SET {field} = ? WHERE group_id = ?"
    result = revise_db(command, (value, group_id))
    return result > 0



def group_admin_list_get(group_id: int) -> List[str]:
    """
    获取指定群组的管理员列表（从JSON字符串解析）。

    Args:
        group_id: 群组ID

    Returns:
        List[str]: 管理员列表，如果解析失败或无数据则返回空列表
    """
    try:
        command = "SELECT members_list FROM groups WHERE group_id = ?"
        result = query_db(command, (group_id,))
        return json.loads(result[0][0]) if result and result[0][0] else []
    except Exception as e:
        print(f"获取群管理员错误: {e}")
        return []


def group_keyword_get(group_id: int) -> List[str]:
    """
    获取指定群组的关键词列表（从JSON字符串解析）。

    Args:
        group_id: 群组ID

    Returns:
        List[str]: 关键词列表，如果解析失败或无数据则返回空列表
    """
    try:
        command = "SELECT keywords FROM groups WHERE group_id = ?"
        result = query_db(command, (group_id,))
        return json.loads(result[0][0]) if result and result[0][0] else []
    except Exception as e:
        print(f"获取群组关键词错误: {e}")
        return []


def group_keyword_set(group_id: int, keywords: List[str]) -> bool:
    """
    设置指定群组的关键词列表（序列化为JSON字符串存储）。

    Args:
        group_id: 群组ID
        keywords: 关键词列表

    Returns:
        bool: 操作是否成功
    """
    try:
        keywords_str = json.dumps(keywords, ensure_ascii=False)
        command = "UPDATE groups SET keywords = ? WHERE group_id = ?"
        result = revise_db(command, (keywords_str, group_id))
        return result > 0
    except Exception as e:
        print(f"设置群组关键词错误: {e}")
        return False


def group_info_create(group_id: int) -> bool:
    """
    为指定group_id创建一条新的群组记录，使用默认API、角色和预设。

    Args:
        group_id: 群组ID

    Returns:
        bool: 操作是否成功
    """
    command = "INSERT INTO groups (group_id, api, char, preset, chat_mode) VALUES (?, ?, ?, ?, 'v1')"
    result = revise_db(
        command,
        (
            group_id,
            get_default_api(),
            get_default_char(),
            get_default_preset(),
        ),
    )
    return result > 0


def group_dialog_initial_add(
    group_id: int,
    msg_user_id: int,
    msg_user_name: str,
    msg_text: str,
    msg_id: int,
    group_name: str,
) -> bool:
    """
    向 group_dialogs 表中插入一条初始的用户消息记录。
    AI回复相关字段在此阶段留空。
    """
    create_at = str(datetime.datetime.now())
    command = """
        INSERT INTO group_dialogs
        (group_id, msg_user, msg_user_name, msg_text, msg_id, group_name, create_at, delete_mark)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'no')
    """
    params = (
        group_id,
        msg_user_id,
        msg_user_name,
        msg_text,
        msg_id,
        group_name,
        create_at,
    )
    # 使用 try-except 避免因为重复 msg_id 而崩溃
    try:
        result = revise_db(command, params)
        return result > 0
    except sqlite3.IntegrityError:
        logger.warning(f"尝试插入重复的 group_dialogs 记录失败: msg_id={msg_id}, group_id={group_id}")
        return False






def group_dialog_get(
    group_id: int, num: int
) -> List[Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]]:
    """
    获取指定group_id的最新num条群聊消息，按msg_id降序排序。

    Args:
        group_id: 群组ID
        num: 获取消息数量

    Returns:
        List[Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]]: 
            消息列表，每个元组包含(msg_text, msg_user_name, processed_response, create_at)
    """
    command = """
              SELECT msg_text, msg_user_name, processed_response, create_at
              FROM (SELECT msg_text, msg_user_name, processed_response, create_at, msg_id \
                    FROM group_dialogs \
                    WHERE group_id = ? \
                    ORDER BY msg_id DESC \
                    LIMIT ?) sub
              ORDER BY msg_id ASC \
              """
    result = query_db(command, (group_id, num))
    print(f"Querying with group_id={group_id}, num={num}, result={result}")  # 调试日志
    return result if result else []


def group_info_update(group_id: int, field: str, value: Any, increase=False) -> bool:
    """
    更新 `groups` 表中指定群组的指定字段。

    Args:
        group_id: 群组ID
        field: 要更新的字段名
        value: 新的字段值
        increase: 是否为增量更新，默认为False

    Returns:
        bool: 操作是否成功
    """
    # print(f"正在把{group_id}的{field}修改为{value}，递增{increase}")
    if not increase:
        command = f"UPDATE groups SET {field} = ? WHERE group_id = ?"
    else:
        command = (
            f"UPDATE groups SET {field} = COALESCE({field}, 0)+? WHERE group_id = ?"
        )
    result = revise_db(command, (value, group_id))
    return result > 0


def group_rate_get(group_id: int) -> float:
    """
    获取指定群组的回复频率(rate)。

    Args:
        group_id: 群组ID

    Returns:
        float: 回复频率，如果未设置或查询失败则返回配置中的默认值
    """
    command = "SELECT rate from groups where group_id = ?"
    result = query_db(command, (group_id,))
    default_rate = get_config("group.default_rate", 0.05)
    return (
        result[0][0]
        if result and result[0] and result[0][0] is not None
        else default_rate
    )


def group_disabled_topics_get(group_id: int) -> List[str]:
    """
    获取指定群组的禁用话题列表（从JSON字符串解析）。

    Args:
        group_id: 群组ID

    Returns:
        List[str]: 禁用话题列表，如果解析失败或无数据则返回空列表（表示没有禁用话题）
    """
    try:
        command = "SELECT disabled_topics FROM groups WHERE group_id = ?"
        result = query_db(command, (group_id,))
        return json.loads(result[0][0]) if result and result[0][0] else []
    except Exception as e:
        print(f"获取群组禁用话题错误: {e}")
        return []




def user_sign_info_get(user_id: int) -> dict:
    """
    获取指定用户的签到信息。

    Args:
        user_id: 用户ID

    Returns:
        dict: 用户签到信息字典，包含user_id、last_sign、sign_count、frequency字段
    """
    command = (
        "SELECT user_id,last_sign,sign_count,frequency from user_sign where user_id =?"
    )
    result = query_db(command, (user_id,))
    if result:
        return dict(zip(["user_id", "last_sign", "sign_count", "frequency"], result[0]))
    else:
        return {"user_id": user_id, "last_sign": 0, "sign_count": 0, "frequency": 0}






def user_sign_info_update(user_id: int, field: str, value: Any) -> bool:
    """
    更新用户签到信息的指定字段。

    Args:
        user_id: 用户ID
        field: 要更新的字段名
        value: 新的字段值

    Returns:
        bool: 操作是否成功
    """
    command = f"UPDATE user_sign SET {field} = COALESCE({field}, 0)+? WHERE user_id =?"
    result = revise_db(command, (value, user_id))
    return result > 0


def get_all_table_names() -> List[str]:
    """
    获取数据库中所有表的名称。

    Returns:
        List[str]: 表名列表。
    """
    command = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    result = query_db(command)
    return [row[0] for row in result] if result else []

def get_table_data(
    table_name: str,
    page: int,
    per_page: int,
    search_term: Optional[str] = None,
    sorters: Optional[List[dict]] = None,
) -> dict:
    """
    获取指定表的数据，支持分页、搜索和排序。

    Args:
        table_name: 表名
        page: 当前页码
        per_page: 每页记录数
        search_term: 搜索关键词
        sorters: 排序器列表 (e.g., [{'field': 'name', 'dir': 'asc'}])

    Returns:
        dict: 包含 headers, rows, total_rows, total_pages 的字典
    """
    conn, conn_index = db_pool.get_connection()
    if not conn:
        return {
            "headers": [],
            "rows": [],
            "total_rows": 0,
            "total_pages": 0,
            "error": "无法获取数据库连接",
        }

    try:
        cursor = conn.cursor()

        # 获取表头
        cursor.execute(f"PRAGMA table_info({table_name});")
        headers = [info[1] for info in cursor.fetchall()]

        # 构建查询
        base_query = f"FROM {table_name}"
        where_clauses = []
        params = []

        if search_term and headers:
            search_clauses = []
            for header in headers:
                search_clauses.append(f"CAST({header} AS TEXT) LIKE ?")
            where_clauses.append("(" + " OR ".join(search_clauses) + ")")
            params.extend([f"%{search_term}%"] * len(headers))

        # 获取总行数
        count_query = "SELECT COUNT(*) " + base_query
        if where_clauses:
            count_query += " WHERE " + " AND ".join(where_clauses)
        
        cursor.execute(count_query, tuple(params))
        total_rows = cursor.fetchone()[0]
        total_pages = (total_rows + per_page - 1) // per_page

        # 获取当前页数据
        offset = (page - 1) * per_page
        data_query = f"SELECT * {base_query}"
        if where_clauses:
            data_query += " WHERE " + " AND ".join(where_clauses)

        # 添加排序逻辑
        order_by_clause = ""
        if sorters:
            order_by_parts = []
            for sorter in sorters:
                field = sorter.get("field")
                direction = sorter.get("dir", "asc").upper()
                # 安全检查：确保列名和排序方向有效
                if field in headers and direction in ["ASC", "DESC"]:
                    # 为列名加上引号以处理特殊字符或关键字
                    order_by_parts.append(f'"{field}" {direction}')
            if order_by_parts:
                order_by_clause = " ORDER BY " + ", ".join(order_by_parts)
        
        data_query += order_by_clause
        data_query += " LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        cursor.execute(data_query, tuple(params))
        rows = cursor.fetchall()

        return {
            "headers": headers,
            "rows": rows,
            "total_rows": total_rows,
            "total_pages": total_pages,
        }

    except sqlite3.Error as e:
        return {
            "headers": [],
            "rows": [],
            "total_rows": 0,
            "total_pages": 0,
            "error": str(e),
        }
    finally:
        if conn_index >= 0:
            db_pool.release_connection(conn_index)
        else:
            if conn:
                conn.close()


# 应用退出时关闭所有数据库连接
def close_all_connections():
    """关闭连接池中的所有数据库连接。应在应用退出时调用。"""
    close_database_runtime()


def manual_wal_checkpoint():
    """手动触发 WAL 检查点。"""
    return runtime_manual_wal_checkpoint()
