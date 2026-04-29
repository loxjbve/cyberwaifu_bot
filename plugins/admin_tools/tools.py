from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from agent.tools import DATABASE_SUPER_TOOLS


class DatabaseSuperToolRegistry:
    """一个为数据库超级工具提供的注册表，包含直接SQL访问、工具描述和全面的数据库模式信息，专为LLM交互设计。"""

    TOOLS: Dict[str, Dict[str, Any]] = {
        "query_db": {
            "description": "在数据库上安全地执行只读的SQL SELECT查询。重要使用须知：1. 这是一个只读工具，不会修改任何数据。2. 为了防止返回过多数据，请始终在查询中使用 'LIMIT' 子句。3. 建议使用带 '?' 的参数化查询以提高安全性。",
            "type": "query",
            "parameters": {
                "command": {
                    "type": "string",
                    "description": "要执行的SQL SELECT查询，强烈建议包含 'LIMIT' 子句。",
                },
                "params": {
                    "type": "string",
                    "description": "一个JSON格式的数组字符串，其元素将按顺序替换命令中的 '?' 占位符 (可选)。",
                }
            },
            "output_format": "一个包含逐行数据或错误信息的查询结果字符串。",
            "example": {
                "tool_name": "query_db",
                "parameters": {"command": "SELECT uid, user_name, account_tier FROM users LIMIT 5", "params": ""}
            },
            "return_value": "包含格式化行或错误信息的查询结果摘要。",
        },
        "revise_db": {
            "description": "在数据库上安全地执行SQL INSERT、UPDATE或DELETE操作。重要安全须知：1. 必须使用带 '?' 的参数化查询来防止SQL注入。2. 'params' JSON数组中的元素数量和顺序必须与 'command' 中的 '?' 完全匹配。3. 执行UPDATE或DELETE时，强烈建议使用WHERE子句以避免对整个表进行意外操作。4. 在执行修改前，建议先使用 'query_db' 确认目标数据。",
            "type": "update",
            "parameters": {
                "command": {
                    "type": "string",
                    "description": "要执行的SQL命令（INSERT、UPDATE、DELETE），必须使用 '?' 作为参数占位符。",
                },
                "params": {
                    "type": "string",
                    "description": "数组字符串，其元素将按顺序替换命令中的 '?' 占位符。例如：'[100.0, 123]'。",
                }
            },
            "output_format": "一个指示受影响行数或错误信息的字符串。",
            "example": {
                "tool_name": "revise_db",
                "parameters": {"command": "UPDATE users SET balance = ? WHERE uid = ?", "params": "[100.0, 123]"}
            },
            "return_value": "包含受影响行数或错误信息的操作结果。",
        },
        "analyze_group_user_profiles": {
            "description": "分析指定群组的聊天记录，为最活跃的用户生成用户画像。此工具会调用LLM进行深度分析，可能需要一些时间。分析结果将以JSON字符串的形式返回，其中包含一个用户画像对象的列表。",
            "type": "analysis",
            "parameters": {
                "group_id": {
                    "type": "integer",
                    "description": "需要分析的目标群组的ID。",
                }
            },
            "output_format": "字符串，包含了识别出的活跃用户的画像列表。",
            "example": {
                "tool_name": "analyze_group_user_profiles",
                "parameters": {"group_id": -100123456789}
            },
            "return_value": "一个包含用户画像对象列表或错误信息的字符串。",
        },
        "execute_sql": {
            "description": "[高风险] 直接执行任意原始SQL命令，不使用参数化查询。这是一个终极工具，应作为最后选择。除非 'query_db' 和 'revise_db' 无法满足需求，否则不要使用此工具。滥用可能导致数据损坏或丢失。请谨慎编写SQL，确保包含WHERE和LIMIT子句以避免意外操作。",
            "type": "execution",
            "parameters": {
                "command": {
                    "type": "string",
                    "description": "要执行的完整、原始的SQL命令。请务必三思而后行。",
                }
            },
            "output_format": "对于SELECT查询，返回格式化的结果。对于其他操作，返回受影响的行数或成功/错误消息。",
            "example": {
                "tool_name": "execute_sql",
                "parameters": {"command": "DELETE FROM users WHERE uid = 12345"}
            },
            "return_value": "包含SQL执行结果的字符串。",
        },
        "analyze_database": {
            "description": "分析数据库，接受sql语句和prompts，将sql语句查询到的数据，拼接prompts内容发送给llm获取返回，这个工具可以辅助你进行数据库分析，防止大量数据库内容返回污染上下文对话。请在prompts中提供清晰的分析指导，以及这条查询返回内容的数据定义。",
            "type": "analysis",
            "parameters": {
                "sql": {
                    "type": "string",
                    "description": "要执行的SQL SELECT查询。",
                },
                "prompts": {
                    "type": "string",
                    "description": "要发送给LLM的提示。",
                }
            },
            "output_format": "一个包含LLM分析结果的字符串。",
            "example": {
                "tool_name": "analyze_database",
                "parameters": {"sql": "SELECT * FROM users LIMIT 5", "prompts": "请分析这些用户的特征"}
            },
            "return_value": "一个包含LLM分析结果或错误信息的字符串。",
        }
    }

    @staticmethod
    def get_tool(tool_name: str) -> Optional[Callable]:
        """通过名称从DATABASE_SUPER_TOOLS获取工具函数。"""
        return DATABASE_SUPER_TOOLS.get(tool_name)

    @staticmethod
    def get_prompt_text() -> str:
        """为嵌入LLM提示生成工具描述和全面数据库模式的格式化文本。"""
        prompt_lines = [
            "你是一个与 CyberWaifu 机器人系统集成的助手，拥有直接数据库访问权限。你可以对数据库执行原始的 SQL 查询和更新。以下是完整的数据库模式和可用的超级工具。",
            "",
            "=== 数据库模式 ===",
            "",
            "表: conversations (私人对话)",
            "- id: INTEGER PRIMARY KEY (auto-increment)",
            "- conv_id: TEXT NOT NULL (conversation ID)",
            "- user_id: INTEGER NOT NULL (user ID)",
            "- character: TEXT NOT NULL (character name)",
            "- preset: TEXT NOT NULL (preset name)",
            "- summary: TEXT (conversation summary)",
            "- create_at: TEXT (creation time)",
            "- update_at: TEXT (last update time)",
            "- delete_mark: TEXT (deletion flag: 'yes' or 'no')",
            "- turns: INTEGER (number of conversation turns)",
            "",
            "表: dialog_summary (私人对话摘要)",
            "- conv_id: TEXT NOT NULL (对话ID)",
            "- summary_area: TEXT NOT NULL (已摘要的对话轮数)",
            "- content: TEXT NOT NULL (摘要文本)",
            "",
            "表: dialogs (私人对话消息)",
            "- id: INTEGER PRIMARY KEY (auto-increment)",
            "- conv_id: TEXT NOT NULL (conversation ID)",
            "- role: TEXT NOT NULL (role: 'assistant' or 'user')",
            "- raw_content: TEXT NOT NULL (original message content)",
            "- turn_order: INTEGER NOT NULL (turn number in conversation)",
            "- created_at: TEXT NOT NULL (creation time)",
            "- processed_content: TEXT (processed content)",
            "- msg_id: INTEGER (Telegram message ID)",
            "",
            "表: group_dialogs (群组对话消息)",
            "- group_id: INTEGER (群组ID)",
            "- msg_user: INTEGER (消息发送者用户ID)",
            "- trigger_type: TEXT (触发类型)",
            "- msg_text: TEXT (消息文本内容)",
            "- msg_user_name: TEXT (消息发送者用户名)",
            "- msg_id: INTEGER (Telegram消息ID)",
            "- raw_response: TEXT (原始AI响应)",
            "- processed_response: TEXT (处理后的AI响应)",
            "- delete_mark: TEXT (删除标记)",
            "- group_name: TEXT (群组名称)",
            "- create_at: TEXT (创建时间)",
            "",
            "表: group_user_conversations (群组用户对话跟踪)",
            "- user_id: INTEGER (user ID)",
            "- group_id: INTEGER (group ID)",
            "- user_name: TEXT (username)",
            "- conv_id: TEXT (conversation ID)",
            "- delete_mark: INTEGER (deletion flag)",
            "- create_at: TEXT (creation time)",
            "- update_at: TEXT (last update time)",
            "- turns: INTEGER (conversation turns)",
            "- group_name: TEXT (group name)",
            "",
            "表: group_user_dialogs (群组用户对话消息)",
            "- id: INTEGER PRIMARY KEY (自增)",
            "- conv_id: TEXT (对话ID)",
            "- role: TEXT (角色: 'assistant' 或 'user')",
            "- raw_content: TEXT (原始消息内容)",
            "- turn_order: INTEGER (轮次)",
            "- created_at: TEXT (创建时间)",
            "- processed_content: TEXT (处理后内容)",
            "",
            "表: groups (群组配置)",
            "- group_id: INTEGER PRIMARY KEY (group ID)",
            "- members_list: TEXT (admin list in JSON format)",
            "- call_count: INTEGER (LLM call count)",
            "- keywords: TEXT (trigger keywords in JSON format)",
            "- active: INTEGER (active status)",
            "- api: TEXT (API configuration)",
            "- char: TEXT (character configuration)",
            "- preset: TEXT (preset configuration)",
            "- input_token: INTEGER (input token count)",
            "- group_name: TEXT (group name)",
            "- update_time: TEXT (last update time)",
            "- rate: REAL (trigger probability)",
            "- output_token: INTEGER (output token count)",
            "- disabled_topics: TEXT (disabled topics in JSON format)",
            "",
            "表: user_config (用户配置)",
            "- uid: INTEGER (用户ID)",
            "- char: TEXT (角色配置)",
            "- api: TEXT (API配置)",
            "- preset: TEXT (预设配置)",
            "- conv_id: TEXT (对话ID)",
            "- stream: TEXT (流式模式: 'yes'/'no')",
            "- nick: TEXT (昵称)",
            "",
            "表: user_sign (用户签到跟踪)",
            "- user_id: INTEGER (user ID)",
            "- last_sign: TEXT (last sign-in time)",
            "- sign_count: INTEGER (total sign-in count)",
            "- frequency: INTEGER (temporary quota)",
            "",
            "表: users (用户信息)",
            "- uid: INTEGER (用户ID)",
            "- first_name: TEXT (名字)",
            "- last_name: TEXT (姓氏)",
            "- user_name: TEXT (用户名)",
            "- create_at: TEXT (创建时间)",
            "- conversations: INTEGER (总对话数)",
            "- dialog_turns: INTEGER (总对话轮数)",
            "- update_at: TEXT (最后更新时间)",
            "- input_tokens: INTEGER (输入令牌数)",
            "- output_tokens: INTEGER (输出令牌数)",
            "- account_tier: INTEGER (账户等级)",
            "- remain_frequency: INTEGER (剩余配额)",
            "- balance: REAL (账户余额)",
            "",
            "表: user_profiles (由AI生成的用户画像数据)",
            "- user_id: INTEGER NOT NULL (用户ID, 复合主键的一部分)",
            "- group_id: INTEGER NOT NULL (群组ID, 复合主键的一部分)",
            "- profile_json: TEXT (包含用户画像的json字符串)",
            "- last_updated: TEXT (最后更新时间戳)",
            "",
            "=== 模拟盘交易相关表 ===",
            "",
            "表: trading_accounts (用户模拟盘账户表)",
            "- user_id: INTEGER NOT NULL (用户ID, 复合主键的一部分)",
            "- group_id: INTEGER NOT NULL (群组ID, 复合主键的一部分)",
            "- balance: REAL DEFAULT 1000.0 (USDT余额)",
            "- total_pnl: REAL DEFAULT 0.0 (总盈亏)",
            "- trading_count: INTEGER DEFAULT 0 (交易次数)",
            "- winning_trades: INTEGER DEFAULT 0 (盈利次数)",
            "- losing_trades: INTEGER DEFAULT 0 (亏损次数)",
            "- total_profit: REAL DEFAULT 0.0 (总盈利额)",
            "- total_loss: REAL DEFAULT 0.0 (总亏损额)",
            "- loan_count: INTEGER DEFAULT 0 (贷款次数)",
            "- total_loan_amount: REAL DEFAULT 0.0 (贷款总额)",
            "- total_repayment_amount: REAL DEFAULT 0.0 (还款总额)",
            "- current_debt: REAL DEFAULT 0.0 (当前欠款额)",
            "- total_fees: REAL DEFAULT 0.0 (累计手续费)",
            "- frozen_margin: REAL DEFAULT 0.0 (冻结保证金)",
            "- created_at: TEXT (创建时间)",
            "- updated_at: TEXT (更新时间)",
            "",
            "表: trading_positions (用户仓位表)",
            "- id: INTEGER PRIMARY KEY AUTOINCREMENT (自增主键)",
            "- user_id: INTEGER NOT NULL (用户ID)",
            "- group_id: INTEGER NOT NULL (群组ID)",
            "- symbol: TEXT NOT NULL (交易对，如BTC/USDT)",
            "- side: TEXT NOT NULL (方向: 'long' 或 'short')",
            "- size: REAL NOT NULL (仓位大小，USDT价值)",
            "- entry_price: REAL NOT NULL (开仓价格)",
            "- current_price: REAL (当前价格)",
            "- pnl: REAL DEFAULT 0.0 (未实现盈亏)",
            "- liquidation_price: REAL (强平价格)",
            "- tp_price: REAL (止盈价格)",
            "- sl_price: REAL (止损价格)",
            "- created_at: TEXT NOT NULL (创建时间)",
            "- updated_at: TEXT (更新时间)",
            "",
            "表: trading_orders (交易订单表)",
            "- order_id: TEXT PRIMARY KEY (订单ID)",
            "- user_id: INTEGER NOT NULL (用户ID)",
            "- group_id: INTEGER NOT NULL (群组ID)",
            "- symbol: TEXT NOT NULL (交易对，如BTC/USDT)",
            "- direction: TEXT NOT NULL (方向: 'ask'(卖出) 或 'bid'(买入))",
            "- role: TEXT NOT NULL (角色: 'taker'(市价单) 或 'maker'(限价单))",
            "- order_type: TEXT NOT NULL (订单属性: 'open'(开仓), 'close'(平仓), 'tp'(止盈), 'sl'(止损))",
            "- operation: TEXT NOT NULL (操作类型: 'reduction'(减仓), 'addition'(加仓))",
            "- status: TEXT DEFAULT 'pending' (订单状态: 'pending'(待成交), 'executed'(已成交), 'cancelled'(已取消))",
            "- volume: REAL NOT NULL (订单数量(USDT价值))",
            "- price: REAL (委托价格，null表示市价单)",
            "- tp_price: REAL (止盈价格)",
            "- sl_price: REAL (止损价格)",
            "- margin_locked: REAL DEFAULT 0.0 (冻结保证金)",
            "- fee_rate: REAL DEFAULT 0.0035 (手续费率 (默认3.5%))",
            "- actual_fee: REAL DEFAULT 0.0 (实际手续费)",
            "- related_position_id: INTEGER (关联的仓位ID)",
            "- created_at: TEXT NOT NULL (创建时间)",
            "- executed_at: TEXT (成交时间)",
            "- cancelled_at: TEXT (取消时间)",
            "- expiry_time: TEXT (过期时间)",
            "- notes: TEXT (备注信息)",
            "",
            "表: trading_history (交易历史记录表)",
            "- id: INTEGER PRIMARY KEY AUTOINCREMENT (自增主键)",
            "- user_id: INTEGER NOT NULL (用户ID)",
            "- group_id: INTEGER NOT NULL (群组ID)",
            "- symbol: TEXT NOT NULL (交易对)",
            "- side: TEXT NOT NULL (方向: 'long' 或 'short')",
            "- action: TEXT NOT NULL (操作: 'open', 'close', 'liquidated')",
            "- size: REAL NOT NULL (仓位大小)",
            "- price: REAL NOT NULL (价格)",
            "- pnl: REAL DEFAULT 0.0 (实现盈亏，平仓时)",
            "- created_at: TEXT NOT NULL (创建时间)",
            "",
            "表: begging_records (救济金记录表)",
            "- user_id: INTEGER NOT NULL (用户ID, 复合主键的一部分)",
            "- group_id: INTEGER NOT NULL (群组ID, 复合主键的一部分)",
            "- last_begging: TEXT (最后一次领取救济金时间)",
            "- begging_count: INTEGER DEFAULT 0 (总领取次数)",
            "",
            "表: price_cache (价格缓存表)",
            "- symbol: TEXT PRIMARY KEY (交易对符号)",
            "- price: REAL NOT NULL (价格)",
            "- updated_at: TEXT NOT NULL (更新时间)",
            "",
            "表: loans (贷款记录表)",
            "- id: INTEGER PRIMARY KEY AUTOINCREMENT (自增主键)",
            "- user_id: INTEGER NOT NULL (用户ID)",
            "- group_id: INTEGER NOT NULL (群组ID)",
            "- principal: REAL NOT NULL (本金)",
            "- remaining_debt: REAL NOT NULL (剩余欠款(本金+利息))",
            "- interest_rate: REAL DEFAULT 0.002 (每6小时利率(0.2%))",
            "- initial_fee: REAL DEFAULT 0.1 (初始手续费(10%))",
            "- loan_time: TEXT NOT NULL (贷款时间)",
            "- last_interest_time: TEXT NOT NULL (最后一次计息时间)",
            "- status: TEXT DEFAULT 'active' (状态: 'active', 'paid_off')",
            "- created_at: TEXT NOT NULL (创建时间)",
            "- updated_at: TEXT (更新时间)",
            "",
            "表: loan_repayments (还款记录表)",
            "- id: INTEGER PRIMARY KEY AUTOINCREMENT (自增主键)",
            "- loan_id: INTEGER NOT NULL (贷款ID)",
            "- user_id: INTEGER NOT NULL (用户ID)",
            "- group_id: INTEGER NOT NULL (群组ID)",
            "- amount: REAL NOT NULL (还款金额)",
            "- repayment_time: TEXT NOT NULL (还款时间)",
            "- remaining_after: REAL NOT NULL (还款后剩余欠款)",
            "- created_at: TEXT NOT NULL (创建时间)",
            "",
            "=== 可用的超级工具 ===",
        ]
        
        for tool_name, tool_info in DatabaseSuperToolRegistry.TOOLS.items():
            params_str = "无"
            if tool_info["parameters"]:
                params_str = "\n    参数:"
                for param_name, param_info in tool_info["parameters"].items():
                    params_str += f"\n      - {param_name}: {param_info['type']} - {param_info['description']}"
            prompt_lines.append(f"- {tool_name}:")
            prompt_lines.append(f"  描述: {tool_info['description']}")
            prompt_lines.append(
                f"  类型: {tool_info['type'].capitalize()} (指示工具是查询数据还是执行更新)"
            )
            prompt_lines.append(f"  {params_str}")
            prompt_lines.append(f"  输出格式: {tool_info['output_format']}")
            prompt_lines.append(f"  返回值: {tool_info['return_value']}")
            prompt_lines.append(
                f"  调用示例: {json.dumps(tool_info['example'], ensure_ascii=False)}"
            )
        
        prompt_lines.extend([
            "",
            "=== 重要使用指南 ===",
            "1. 使用带 ? 占位符的参数化查询以防止SQL注入。",
            "2. 对于 params 字段，请提供一个JSON数​​组字符串，例如 '[123, \"value\"]'。",
            "3. 对于大的结果集，请始终使用LIMIT子句以避免输出过载。",
            "4. 小心使用UPDATE/DELETE操作 - 它们会直接修改数据库。",
            "5. 时间字段以各种格式的TEXT形式存储，请使用字符串比较。",
            "6. 如果要按内容筛选，需要解析JSON字段（如keywords, members_list）。",
            "7. dialogs中的'role'字段：'user' = 人类消息, 'assistant' = AI响应。",
            "8. 工具使用注意事项：关于对话记录的content详情，一次可以限制查询20条左右，如果有必要可以多次调用，防止一次性处理内容过多。",
            "9. 如果输入中提到了具体的用户或群组，请先在users表单中搜索到用户的具体信息，再执行下一步。优先尝试把所有用户的用户first_name和last_name的拼接起来组合成全名，然后在所有用户的全名中模糊搜索内容，如果失败再尝试搜索用户id(应为纯数字，若输入不是纯数字则无需搜索)和用户名。",
            "",
            "指令：如果用户的请求涉及多个步骤或依赖项，请返回一个JSON格式的工具调用列表，以便按顺序执行。使用以下格式：",
            "```json",
            "{",
            '  "tool_calls": [',
            '    {"tool_name": "query_db", "parameters": {"command": "SELECT ...", "params": ""}},',
            '    {"tool_name": "revise_db", "parameters": {"command": "UPDATE ...", "params": "[value1, value2]"}}',
            "  ]",
            "}",
            "```",
            "或者如果是单个工具调用：",
            "```json",
            "{",
            '  "tool_name": "query_db", "parameters": {"command": "SELECT * FROM users LIMIT 10", "params": ""}',
            "}",
            "```",
            "",
            "工具调用结果将反馈给您进行分析或采取进一步行动。如果不需要任何工具，请以纯文本形式回应。"
        ])
        
        return "\n".join(prompt_lines)
