import os
import re
import sqlite3
import logging
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from utils.config_utils import project_root

logger = logging.getLogger(__name__)

@dataclass
class ColumnInfo:
    """表示数据库列的信息"""
    name: str
    data_type: str
    nullable: bool = True
    default_value: Optional[str] = None
    primary_key: bool = False
    autoincrement: bool = False
    unique: bool = False
    foreign_key: Optional[str] = None

@dataclass
class TableSchema:
    """表示数据库表的结构"""
    name: str
    columns: List[ColumnInfo]
    primary_keys: List[str]
    foreign_keys: List[Tuple[str, str]]  # (column, reference)
    unique_constraints: List[List[str]]

class SQLSchemaParser:
    """SQL表结构解析器"""
    
    def __init__(self, sql_file_path: str):
        self.sql_file_path = sql_file_path
        self.tables: Dict[str, TableSchema] = {}
    
    def parse_sql_file(self) -> Dict[str, TableSchema]:
        """解析SQL文件，返回所有表的结构信息"""
        try:
            with open(self.sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            # 移除注释
            sql_content = self._remove_comments(sql_content)
            
            # 分割CREATE TABLE语句
            create_statements = self._extract_create_table_statements(sql_content)
            
            # 解析每个CREATE TABLE语句
            for statement in create_statements:
                table_schema = self._parse_create_table_statement(statement)
                if table_schema:
                    self.tables[table_schema.name] = table_schema
            
            logger.info(f"成功解析了 {len(self.tables)} 个表的结构")
            return self.tables
            
        except Exception as e:
            logger.error(f"解析SQL文件失败: {e}")
            raise
    
    def _remove_comments(self, sql_content: str) -> str:
        """移除SQL注释"""
        # 移除单行注释 (--)
        sql_content = re.sub(r'--.*?\n', '\n', sql_content)
        # 移除多行注释 (/* */)
        sql_content = re.sub(r'/\*.*?\*/', '', sql_content, flags=re.DOTALL)
        return sql_content
    
    def _extract_create_table_statements(self, sql_content: str) -> List[str]:
        """提取所有CREATE TABLE语句"""
        statements = []
        
        # 使用正则表达式匹配CREATE TABLE语句
        pattern = r'create\s+table\s+([^;]+);'
        matches = re.finditer(pattern, sql_content, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            statement = 'CREATE TABLE ' + match.group(1).strip() + ';'
            statements.append(statement)
        
        return statements
    
    def _parse_create_table_statement(self, statement: str) -> Optional[TableSchema]:
        """解析单个CREATE TABLE语句"""
        try:
            # 提取表名
            table_name_match = re.search(r'create\s+table\s+(\w+)', statement, re.IGNORECASE)
            if not table_name_match:
                return None
            
            table_name = table_name_match.group(1)
            
            # 提取表定义部分（括号内的内容）
            table_def_match = re.search(r'\((.+)\)', statement, re.DOTALL)
            if not table_def_match:
                return None
            
            table_definition = table_def_match.group(1)
            
            # 解析列定义和约束
            columns = []
            primary_keys = []
            foreign_keys = []
            unique_constraints = []
            
            # 分割列定义和约束
            items = self._split_table_items(table_definition)
            
            for item in items:
                item = item.strip()
                if not item:
                    continue
                
                if item.upper().startswith('CONSTRAINT'):
                    # 处理约束
                    self._parse_constraint(item, primary_keys, foreign_keys, unique_constraints)
                elif item.upper().startswith('PRIMARY KEY'):
                    # 处理主键约束
                    pk_match = re.search(r'primary\s+key\s*\(([^)]+)\)', item, re.IGNORECASE)
                    if pk_match:
                        pk_columns = [col.strip() for col in pk_match.group(1).split(',')]
                        primary_keys.extend(pk_columns)
                elif item.upper().startswith('FOREIGN KEY'):
                    # 处理外键约束
                    self._parse_foreign_key(item, foreign_keys)
                else:
                    # 处理列定义
                    column = self._parse_column_definition(item)
                    if column:
                        columns.append(column)
                        if column.primary_key:
                            primary_keys.append(column.name)
            
            return TableSchema(
                name=table_name,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
                unique_constraints=unique_constraints
            )
            
        except Exception as e:
            logger.error(f"解析CREATE TABLE语句失败: {e}\n语句: {statement}")
            return None
    
    def _split_table_items(self, table_definition: str) -> List[str]:
        """分割表定义中的项目（列定义和约束）"""
        items = []
        current_item = ""
        paren_count = 0
        
        for char in table_definition:
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
            elif char == ',' and paren_count == 0:
                items.append(current_item.strip())
                current_item = ""
                continue
            
            current_item += char
        
        if current_item.strip():
            items.append(current_item.strip())
        
        return items
    
    def _parse_column_definition(self, column_def: str) -> Optional[ColumnInfo]:
        """解析列定义"""
        try:
            parts = column_def.strip().split()
            if len(parts) < 2:
                return None
            
            column_name = parts[0]
            data_type = parts[1]
            
            # 解析列属性
            nullable = True
            default_value = None
            primary_key = False
            autoincrement = False
            unique = False
            foreign_key = None
            
            column_def_upper = column_def.upper()
            
            if 'NOT NULL' in column_def_upper:
                nullable = False
            
            if 'PRIMARY KEY' in column_def_upper:
                primary_key = True
            
            if 'AUTOINCREMENT' in column_def_upper:
                autoincrement = True
            
            if 'UNIQUE' in column_def_upper:
                unique = True
            
            # 提取默认值
            default_match = re.search(r'default\s+([^\s,]+)', column_def, re.IGNORECASE)
            if default_match:
                default_value = default_match.group(1)
            
            return ColumnInfo(
                name=column_name,
                data_type=data_type,
                nullable=nullable,
                default_value=default_value,
                primary_key=primary_key,
                autoincrement=autoincrement,
                unique=unique,
                foreign_key=foreign_key
            )
            
        except Exception as e:
            logger.error(f"解析列定义失败: {e}\n定义: {column_def}")
            return None
    
    def _parse_constraint(self, constraint_def: str, primary_keys: List[str], 
                         foreign_keys: List[Tuple[str, str]], unique_constraints: List[List[str]]):
        """解析约束定义"""
        constraint_upper = constraint_def.upper()
        
        if 'PRIMARY KEY' in constraint_upper:
            pk_match = re.search(r'primary\s+key\s*\(([^)]+)\)', constraint_def, re.IGNORECASE)
            if pk_match:
                pk_columns = [col.strip() for col in pk_match.group(1).split(',')]
                primary_keys.extend(pk_columns)
        
        elif 'FOREIGN KEY' in constraint_upper:
            self._parse_foreign_key(constraint_def, foreign_keys)
    
    def _parse_foreign_key(self, fk_def: str, foreign_keys: List[Tuple[str, str]]):
        """解析外键定义"""
        fk_match = re.search(r'foreign\s+key\s*\(([^)]+)\)\s*references\s+(\w+)\s*\(([^)]+)\)', 
                            fk_def, re.IGNORECASE)
        if fk_match:
            local_column = fk_match.group(1).strip()
            ref_table = fk_match.group(2).strip()
            ref_column = fk_match.group(3).strip()
            foreign_keys.append((local_column, f"{ref_table}({ref_column})"))

class DatabaseSchemaComparator:
    """数据库表结构比较器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_current_table_schema(self, table_name: str) -> Optional[TableSchema]:
        """获取当前数据库中表的结构"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取表信息
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns_info = cursor.fetchall()
            
            if not columns_info:
                conn.close()
                return None
            
            columns = []
            primary_keys = []
            
            for col_info in columns_info:
                # col_info: (cid, name, type, notnull, dflt_value, pk)
                column = ColumnInfo(
                    name=col_info[1],
                    data_type=col_info[2],
                    nullable=not bool(col_info[3]),
                    default_value=col_info[4],
                    primary_key=bool(col_info[5]),
                    autoincrement=False,  # SQLite的PRAGMA table_info不直接提供这个信息
                    unique=False
                )
                columns.append(column)
                
                if column.primary_key:
                    primary_keys.append(column.name)
            
            # 获取外键信息
            cursor.execute(f"PRAGMA foreign_key_list({table_name});")
            fk_info = cursor.fetchall()
            foreign_keys = []
            
            for fk in fk_info:
                # fk: (id, seq, table, from, to, on_update, on_delete, match)
                foreign_keys.append((fk[3], f"{fk[2]}({fk[4]})"))
            
            conn.close()
            
            return TableSchema(
                name=table_name,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
                unique_constraints=[]  # 暂时不处理唯一约束
            )
            
        except Exception as e:
            logger.error(f"获取表结构失败: {e}")
            return None
    
    def compare_schemas(self, expected_schema: TableSchema, current_schema: Optional[TableSchema]) -> Dict[str, any]:
        """比较两个表结构，返回差异信息"""
        if current_schema is None:
            return {
                'table_exists': False,
                'needs_creation': True,
                'columns_to_add': expected_schema.columns,
                'columns_to_remove': [],
                'columns_to_modify': []
            }
        
        # 比较列
        expected_columns = {col.name: col for col in expected_schema.columns}
        current_columns = {col.name: col for col in current_schema.columns}
        
        columns_to_add = []
        columns_to_remove = []
        columns_to_modify = []
        
        # 找出需要添加的列
        for col_name, col_info in expected_columns.items():
            if col_name not in current_columns:
                columns_to_add.append(col_info)
            else:
                # 检查列是否需要修改
                current_col = current_columns[col_name]
                if self._columns_differ(col_info, current_col):
                    columns_to_modify.append((current_col, col_info))
        
        # 找出需要删除的列
        for col_name in current_columns:
            if col_name not in expected_columns:
                columns_to_remove.append(current_columns[col_name])
        
        return {
            'table_exists': True,
            'needs_creation': False,
            'columns_to_add': columns_to_add,
            'columns_to_remove': columns_to_remove,
            'columns_to_modify': columns_to_modify
        }
    
    def _columns_differ(self, expected: ColumnInfo, current: ColumnInfo) -> bool:
        """检查两个列定义是否不同"""
        # 比较数据类型、是否可空、主键、唯一约束等重要属性
        return (
            expected.data_type.upper() != current.data_type.upper() or
            expected.nullable != current.nullable or
            expected.primary_key != current.primary_key or
            expected.unique != current.unique or
            expected.autoincrement != current.autoincrement
        )

def get_schema_parser(sql_path: Optional[str] = None) -> SQLSchemaParser:
    """获取SQL结构解析器实例"""
    sql_file_path = sql_path or os.path.join(project_root, "data", "database.sql")
    return SQLSchemaParser(sql_file_path)

def get_schema_comparator(db_path: Optional[str] = None) -> DatabaseSchemaComparator:
    """获取数据库结构比较器实例"""
    db_path = db_path or os.path.join(project_root, "data", "data.db")
    return DatabaseSchemaComparator(db_path)

class DatabaseSchemaMigrator:
    """数据库表结构迁移器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def migrate_table_schema(self, table_name: str, expected_schema: TableSchema, 
                           current_schema: Optional[TableSchema]) -> bool:
        """迁移表结构到期望的状态"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys=OFF;")  # 临时关闭外键约束
            
            if current_schema is None:
                # 表不存在，创建新表
                success = self._create_table(conn, expected_schema)
            else:
                # 表存在，进行结构迁移
                success = self._migrate_existing_table(conn, table_name, expected_schema, current_schema)
            
            if success:
                conn.commit()
                logger.info(f"表 {table_name} 结构迁移成功")
            else:
                conn.rollback()
                logger.error(f"表 {table_name} 结构迁移失败")
            
            conn.execute("PRAGMA foreign_keys=ON;")  # 重新启用外键约束
            conn.close()
            return success
            
        except Exception as e:
            logger.error(f"迁移表 {table_name} 结构时发生错误: {e}")
            return False
    
    def _create_table(self, conn: sqlite3.Connection, schema: TableSchema) -> bool:
        """创建新表"""
        try:
            create_sql = self._generate_create_table_sql(schema)
            conn.execute(create_sql)
            logger.info(f"成功创建表 {schema.name}")
            return True
        except Exception as e:
            logger.error(f"创建表 {schema.name} 失败: {e}")
            return False
    
    def _migrate_existing_table(self, conn: sqlite3.Connection, table_name: str, 
                              expected_schema: TableSchema, current_schema: TableSchema) -> bool:
        """迁移现有表的结构"""
        try:
            # 获取差异信息
            comparator = DatabaseSchemaComparator(self.db_path)
            diff = comparator.compare_schemas(expected_schema, current_schema)
            
            # 如果没有差异，直接返回
            if (not diff['columns_to_add'] and 
                not diff['columns_to_remove'] and 
                not diff['columns_to_modify']):
                logger.info(f"表 {table_name} 结构已是最新，无需迁移")
                return True
            
            # SQLite不支持直接删除列，需要使用重建表的方式
            if diff['columns_to_remove'] or diff['columns_to_modify']:
                return self._rebuild_table(conn, table_name, expected_schema, current_schema)
            
            # 只有添加列的情况，可以直接ALTER TABLE
            if diff['columns_to_add']:
                return self._add_columns(conn, table_name, diff['columns_to_add'])
            
            return True
            
        except Exception as e:
            logger.error(f"迁移表 {table_name} 时发生错误: {e}")
            return False
    
    def _add_columns(self, conn: sqlite3.Connection, table_name: str, columns_to_add: List[ColumnInfo]) -> bool:
        """添加新列"""
        try:
            for column in columns_to_add:
                # 构建ALTER TABLE语句
                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {self._column_to_sql(column)}"
                conn.execute(alter_sql)
                logger.info(f"成功为表 {table_name} 添加列 {column.name}")
            return True
        except Exception as e:
            logger.error(f"添加列失败: {e}")
            return False
    
    def _rebuild_table(self, conn: sqlite3.Connection, table_name: str, 
                      expected_schema: TableSchema, current_schema: TableSchema) -> bool:
        """重建表（用于删除列或修改列）"""
        try:
            # 1. 创建临时表
            temp_table_name = f"{table_name}_temp_{int(os.urandom(4).hex(), 16)}"
            temp_schema = TableSchema(
                name=temp_table_name,
                columns=expected_schema.columns,
                primary_keys=expected_schema.primary_keys,
                foreign_keys=expected_schema.foreign_keys,
                unique_constraints=expected_schema.unique_constraints
            )
            
            create_temp_sql = self._generate_create_table_sql(temp_schema)
            conn.execute(create_temp_sql)
            logger.info(f"创建临时表 {temp_table_name}")
            
            # 2. 复制数据
            # 找出新旧表的共同列
            current_columns = {col.name for col in current_schema.columns}
            expected_columns = {col.name for col in expected_schema.columns}
            common_columns = current_columns.intersection(expected_columns)
            
            if common_columns:
                columns_str = ', '.join(common_columns)
                copy_sql = f"INSERT INTO {temp_table_name} ({columns_str}) SELECT {columns_str} FROM {table_name}"
                conn.execute(copy_sql)
                logger.info(f"复制数据到临时表，保留列: {', '.join(common_columns)}")
            
            # 3. 删除原表
            conn.execute(f"DROP TABLE {table_name}")
            logger.info(f"删除原表 {table_name}")
            
            # 4. 重命名临时表
            conn.execute(f"ALTER TABLE {temp_table_name} RENAME TO {table_name}")
            logger.info(f"重命名临时表为 {table_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"重建表 {table_name} 失败: {e}")
            # 尝试清理临时表
            try:
                conn.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            except:
                pass
            return False
    
    def _generate_create_table_sql(self, schema: TableSchema) -> str:
        """生成CREATE TABLE SQL语句"""
        columns_sql = []
        
        # 添加列定义
        for column in schema.columns:
            columns_sql.append(self._column_to_sql(column))
        
        # 添加主键约束（如果有多个主键列）
        if len(schema.primary_keys) > 1:
            pk_sql = f"PRIMARY KEY ({', '.join(schema.primary_keys)})"
            columns_sql.append(pk_sql)
        
        # 添加外键约束
        for local_col, reference in schema.foreign_keys:
            fk_sql = f"FOREIGN KEY ({local_col}) REFERENCES {reference}"
            columns_sql.append(fk_sql)
        
        # 组装完整的CREATE TABLE语句
        create_sql = f"CREATE TABLE {schema.name} (\n    {',\n    '.join(columns_sql)}\n)"
        return create_sql
    
    def _column_to_sql(self, column: ColumnInfo) -> str:
        """将列信息转换为SQL定义"""
        sql_parts = [column.name, column.data_type]
        
        if column.primary_key:
            sql_parts.append("PRIMARY KEY")
        
        if column.autoincrement:
            sql_parts.append("AUTOINCREMENT")
        
        if not column.nullable:
            sql_parts.append("NOT NULL")
        
        if column.unique and not column.primary_key:
            sql_parts.append("UNIQUE")
        
        if column.default_value is not None:
            sql_parts.append(f"DEFAULT {column.default_value}")
        
        return ' '.join(sql_parts)

def get_schema_migrator(db_path: Optional[str] = None) -> DatabaseSchemaMigrator:
    """获取数据库结构迁移器实例"""
    db_path = db_path or os.path.join(project_root, "data", "data.db")
    return DatabaseSchemaMigrator(db_path)

def check_and_migrate_database_schema(
    *,
    db_path: Optional[str] = None,
    sql_path: Optional[str] = None,
) -> bool:
    """检查并迁移数据库表结构"""
    try:
        logger.info("开始检查数据库表结构...")
        
        # 解析期望的表结构
        parser = get_schema_parser(sql_path)
        expected_schemas = parser.parse_sql_file()
        
        if not expected_schemas:
            logger.warning("未找到任何表结构定义")
            return True
        
        # 获取比较器和迁移器
        comparator = get_schema_comparator(db_path)
        migrator = get_schema_migrator(db_path)
        
        migration_success = True
        
        # 检查每个表
        for table_name, expected_schema in expected_schemas.items():
            logger.info(f"检查表 {table_name}...")
            
            # 获取当前表结构
            current_schema = comparator.get_current_table_schema(table_name)
            
            # 比较结构
            diff = comparator.compare_schemas(expected_schema, current_schema)
            
            if diff['needs_creation']:
                logger.info(f"表 {table_name} 不存在，需要创建")
            elif (diff['columns_to_add'] or diff['columns_to_remove'] or diff['columns_to_modify']):
                logger.info(f"表 {table_name} 结构需要更新")
                if diff['columns_to_add']:
                    logger.info(f"  需要添加列: {[col.name for col in diff['columns_to_add']]}")
                if diff['columns_to_remove']:
                    logger.info(f"  需要删除列: {[col.name for col in diff['columns_to_remove']]}")
                if diff['columns_to_modify']:
                    logger.info(f"  需要修改列: {[pair[0].name for pair in diff['columns_to_modify']]}")
            else:
                logger.info(f"表 {table_name} 结构正确，无需更新")
                continue
            
            # 执行迁移
            if not migrator.migrate_table_schema(table_name, expected_schema, current_schema):
                logger.error(f"表 {table_name} 迁移失败")
                migration_success = False
        
        if migration_success:
            logger.info("数据库表结构检查和迁移完成")
        else:
            logger.error("部分表结构迁移失败")
        
        return migration_success
        
    except Exception as e:
        logger.error(f"检查和迁移数据库表结构时发生错误: {e}")
        return False
