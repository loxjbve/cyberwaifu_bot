import asyncio
import json
import os
import time
from datetime import datetime
from flask import Blueprint, jsonify, request, Response, send_from_directory, current_app, session
from typing import Union
from agent.llm_functions import generate_summary
from bot_core.data_repository import GroupsRepository
from utils import db_utils as db
from web.factory import admin_required, viewer_required, get_admin_ids, app_logger
from web.factory import viewer_or_admin_required

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/message_page/<group_id>/<msg_id>")
@admin_required
def get_message_page(group_id, msg_id):
    """获取指定消息所在的页码"""
    try:
        group_id = int(group_id)
    except ValueError:
        return jsonify({"error": "Invalid group ID"}), 400
    per_page = 50
    msg_data = db.query_db(
        "SELECT create_at FROM group_dialogs WHERE group_id = ? AND msg_id = ?",
        (group_id, msg_id),
    )
    if not msg_data:
        return jsonify({"error": "Message not found"}), 404
    msg_create_at = msg_data[0][0]
    count_result = db.query_db(
        "SELECT COUNT(*) FROM group_dialogs WHERE group_id = ? AND create_at > ?",
        (group_id, msg_create_at),
    )
    messages_after = count_result[0][0] if count_result else 0
    page = (messages_after // per_page) + 1
    return jsonify({"page": page})


@api_bp.route("/export_group_dialogs/<group_id>")
@admin_required
def export_group_dialogs(group_id):
    """导出完整的群组对话数据"""
    try:
        group_id = int(group_id)
    except ValueError:
        return jsonify({"error": "Invalid group ID"}), 400

    export_result = GroupsRepository.group_dialog_export_data_get(group_id)
    if not export_result["success"] or not export_result.get("data"):
        return jsonify({"error": export_result.get("error", "导出失败")}), 404

    export_data = export_result["data"]
    group = export_data.get("group") or {}
    dialogs_data = export_data.get("dialogs") or []
    conversations = []
    for dialog_dict in dialogs_data:
        conversation = {
            "dialog_id": dialog_dict["msg_id"],
            "user_message": {
                "content": dialog_dict["msg_text"],
                "user_name": dialog_dict["msg_user_name"],
                "user_id": dialog_dict["msg_user"],
                "trigger_type": dialog_dict["trigger_type"],
                "time": dialog_dict["create_at"],
            },
            "ai_response": {
                "processed_response": dialog_dict["processed_response"],
                "raw_response": dialog_dict["raw_response"],
                "time": dialog_dict["create_at"],
            },
        }
        conversations.append(conversation)

    response_payload = {
        "success": True,
        **export_data,
        "group_info": {
            "group_id": group.get("group_id", group_id),
            "group_name": export_data["export_meta"].get("group_name") or "未命名群组",
            "character": group.get("char") or "未设置",
            "preset": group.get("preset") or "默认",
            "export_time": export_data["export_meta"]["exported_at"],
            "total_conversations": len(conversations),
        },
        "conversations": conversations,
    }
    return jsonify(response_payload)




@api_bp.route("/user/<int:user_id>", methods=["GET", "PUT"])
@viewer_or_admin_required
def api_user_detail(user_id) -> Union[Response, tuple[Response, int]]:
    """获取或更新用户详细信息API"""
    user_role = session.get("user_role")

    if user_role == "viewer":
        admin_ids = get_admin_ids()
        if user_id in admin_ids:
            return jsonify({"error": "无权限查看此用户信息"}), 403

    if request.method == "GET":
        user_data = db.query_db("SELECT * FROM users WHERE uid = ?", (user_id,))
        if not user_data:
            return jsonify({"error": "用户不存在"}), 404
        user_config_data = db.query_db(
            "SELECT * FROM user_config WHERE uid = ?", (user_id,)
        )
        conversations_count_data = db.query_db(
            "SELECT COUNT(*) FROM conversations WHERE user_id = ?", (user_id,)
        )
        conversations_count = (
            conversations_count_data[0][0] if conversations_count_data else 0
        )
        user_columns = [
            "uid", "first_name", "last_name", "user_name", "create_at",
            "conversations", "dialog_turns", "update_at", "input_tokens",
            "output_tokens", "account_tier", "remain_frequency", "balance",
        ]
        user_dict = {user_columns[i]: user_data[0][i] for i in range(len(user_columns))}
        user_config_dict = None
        if user_config_data:
            config_columns = ["uid", "char", "api", "preset", "conv_id", "stream", "nick"]
            user_config_dict = {
                config_columns[i]: user_config_data[0][i]
                for i in range(len(config_columns))
            }
        user_profiles = db.user_profile_get(user_id)
        return jsonify({
            "user": user_dict,
            "config": user_config_dict,
            "conversations_count": conversations_count,
            "profiles": user_profiles,
        })

    elif request.method == "PUT":
        if user_role != "admin":
            return jsonify({"error": "无权限执行此操作"}), 403
        try:
            data = request.get_json()
            
            # 更新 users 表
            user_updates = {}
            user_fields = ["user_name", "first_name", "last_name", "account_tier", "balance", "remain_frequency"]
            for field in user_fields:
                if field in data:
                    user_updates[field] = data[field]

            if user_updates:
                user_updates["update_at"] = datetime.now()
                set_clause = ", ".join([f"{key} = ?" for key in user_updates.keys()])
                params = list(user_updates.values()) + [user_id]
                user_sql = f"UPDATE users SET {set_clause} WHERE uid = ?"
                db.revise_db(user_sql, tuple(params))

            # 更新 user_config 表
            if "config" in data and isinstance(data["config"], dict):
                config_data = data["config"]
                config_updates = {}
                config_fields = ["char", "api", "preset", "stream", "nick"]
                for field in config_fields:
                    if field in config_data:
                        config_updates[field] = config_data[field]
                
                if config_updates:
                    existing_config = db.query_db("SELECT uid FROM user_config WHERE uid = ?", (user_id,))
                    if existing_config:
                        set_clause = ", ".join([f"{key} = ?" for key in config_updates.keys()])
                        params = list(config_updates.values()) + [user_id]
                        config_sql = f"UPDATE user_config SET {set_clause} WHERE uid = ?"
                        db.revise_db(config_sql, tuple(params))
                    else:
                        config_updates["uid"] = user_id
                        columns = ", ".join(config_updates.keys())
                        placeholders = ", ".join(["?"] * len(config_updates))
                        params = list(config_updates.values())
                        config_sql = f"INSERT INTO user_config ({columns}) VALUES ({placeholders})"
                        db.revise_db(config_sql, tuple(params))

            return jsonify({"success": True, "message": "用户信息更新成功"})
        except Exception as e:
            app_logger.error(f"更新用户 {user_id} 信息失败: {e}")
            return jsonify({"success": False, "message": str(e)}), 500
    return jsonify({"error": "未处理的请求方法"}), 405






@api_bp.route("/config/list")
@admin_required
def api_config_list():
    """获取配置文件列表"""
    try:
        import os
        import json
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_dirs = {
            "characters": "characters",
            "config": "config",
            "prompts": "prompts",
            "agent_docs": "agent/docs",
        }
        result = {}
        for category, rel_dir_path in config_dirs.items():
            files = []
            abs_dir_path = os.path.join(base_path, rel_dir_path)
            if os.path.exists(abs_dir_path):
                for filename in os.listdir(abs_dir_path):
                    if filename.endswith(".json"):
                        abs_file_path = os.path.join(abs_dir_path, filename)
                        rel_file_path = f"{rel_dir_path}/{filename}".replace('\\', '/')
                        try:
                            with open(abs_file_path, "r", encoding="utf-8") as f:
                                json.load(f)
                            files.append(
                                {
                                    "name": filename,
                                    "path": rel_file_path,
                                    "size": os.path.getsize(abs_file_path),
                                    "modified": os.path.getmtime(abs_file_path),
                                }
                            )
                        except Exception as e:
                            files.append(
                                {"name": filename, "path": rel_file_path, "error": str(e)}
                            )
            result[category] = files
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/config/read")
@admin_required
def api_config_read():
    """读取配置文件内容"""
    try:
        rel_path = request.args.get("path")
        if not rel_path:
            return jsonify({"error": "缺少文件路径参数"}), 400

        # 规范化路径以防止目录遍历
        rel_path = os.path.normpath(rel_path).replace('\\', '/')
        if rel_path.startswith(('../', './', '/')):
            return jsonify({"error": "不允许的路径格式"}), 403

        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        allowed_dirs = ["characters/", "config/", "prompts/", "agent/docs/"]
        if not any(rel_path.startswith(d) for d in allowed_dirs):
            return jsonify({"error": "不允许访问此路径"}), 403

        file_path = os.path.join(base_path, rel_path)
        
        # 再次检查最终路径是否在预期基本路径下
        if not os.path.abspath(file_path).startswith(os.path.abspath(base_path)):
            return jsonify({"error": "不允许访问此路径"}), 403

        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return jsonify({"error": "文件不存在"}), 404
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        return jsonify(
            {"content": content, "path": rel_path, "name": os.path.basename(file_path)}
        )
    except json.JSONDecodeError as e:
        return jsonify({"error": f"JSON格式错误: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/config/save", methods=["POST"])
@admin_required
def api_config_save():
    """保存配置文件"""
    try:
        data = request.get_json()
        rel_path = data.get("path")
        content = data.get("content")
        if not rel_path or content is None:
            return jsonify({"error": "缺少必要参数"}), 400

        rel_path = os.path.normpath(rel_path).replace('\\', '/')
        if rel_path.startswith(('../', './', '/')):
            return jsonify({"error": "不允许的路径格式"}), 403

        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        allowed_dirs = ["characters/", "config/", "prompts/", "agent/docs/"]
        if not any(rel_path.startswith(d) for d in allowed_dirs):
            return jsonify({"error": "不允许访问此路径"}), 403

        file_path = os.path.join(base_path, rel_path)
        
        if not os.path.abspath(file_path).startswith(os.path.abspath(base_path)):
            return jsonify({"error": "不允许访问此路径"}), 403

        try:
            json.dumps(content)
        except Exception as e:
            return jsonify({"error": f"JSON格式无效: {str(e)}"}), 400
        if os.path.exists(file_path):
            backup_path = file_path + ".backup"
            import shutil
            shutil.copy2(file_path, backup_path)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True, "message": "文件保存成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/config/create", methods=["POST"])
@admin_required
def api_config_create():
    """创建新配置文件"""
    try:
        data = request.get_json()
        category = data.get("category")
        filename = data.get("filename")
        content = data.get("content", {})
        if not category or not filename:
            return jsonify({"error": "缺少必要参数"}), 400
        if not filename.endswith(".json"):
            filename += ".json"
        
        # 净化文件名
        import re
        filename = re.sub(r'[\\/*?:"<>|]', "", filename)

        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        allowed_categories = ["characters", "config", "prompts", "agent_docs"]
        if category not in allowed_categories:
            return jsonify({"error": "无效的分类"}), 400
        
        # 处理agent_docs特殊路径
        if category == "agent_docs":
            dir_path = os.path.join(base_path, "agent", "docs")
        else:
            dir_path = os.path.join(base_path, category)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        file_path = os.path.join(dir_path, filename)

        if not os.path.abspath(file_path).startswith(os.path.abspath(dir_path)):
            return jsonify({"error": "不允许的文件名"}), 403

        if os.path.exists(file_path):
            return jsonify({"error": "文件已存在"}), 409
        try:
            json.dumps(content)
        except Exception as e:
            return jsonify({"error": f"JSON格式无效: {str(e)}"}), 400
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        
        # 生成正确的相对路径
        if category == "agent_docs":
            rel_path = f"agent/docs/{filename}".replace('\\', '/')
        else:
            rel_path = f"{category}/{filename}".replace('\\', '/')
        return jsonify({"success": True, "message": "文件创建成功", "path": rel_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/config/delete", methods=["POST"])
@admin_required
def api_config_delete():
    """删除配置文件"""
    try:
        data = request.get_json()
        rel_path = data.get("path")
        if not rel_path:
            return jsonify({"error": "缺少文件路径参数"}), 400

        rel_path = os.path.normpath(rel_path).replace('\\', '/')
        if rel_path.startswith(('../', './', '/')):
            return jsonify({"error": "不允许的路径格式"}), 403

        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        allowed_dirs = ["characters/", "config/", "prompts/", "agent/docs/"]
        if not any(rel_path.startswith(d) for d in allowed_dirs):
            return jsonify({"error": "不允许访问此路径"}), 403

        file_path = os.path.join(base_path, rel_path)
        
        if not os.path.abspath(file_path).startswith(os.path.abspath(base_path)):
            return jsonify({"error": "不允许访问此路径"}), 403

        if not os.path.exists(file_path):
            return jsonify({"error": "文件不存在"}), 404
        backup_path = file_path + ".deleted." + str(int(time.time()))
        import shutil
        shutil.move(file_path, backup_path)
        return jsonify(
            {"success": True, "message": "文件删除成功", "backup": backup_path}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/generate_summary", methods=["POST"])
@admin_required
def api_generate_summary():
    """生成对话摘要"""
    try:
        app_logger.info(f"收到生成摘要请求，Content-Type: {request.content_type}")
        app_logger.info(f"请求数据: {request.get_data(as_text=True)}")
        if not request.is_json:
            app_logger.error(f"请求不是JSON格式，Content-Type: {request.content_type}")
            return jsonify({"error": "请求必须是JSON格式"}), 400
        data = request.get_json()
        if data is None:
            app_logger.error("无法解析JSON数据")
            return jsonify({"error": "无法解析JSON数据"}), 400
        conversation_id = data.get("conversation_id")
        app_logger.info(f"解析到的conversation_id: {conversation_id}")
        if not conversation_id:
            return jsonify({"error": "缺少对话ID参数"}), 400
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            summary = loop.run_until_complete(generate_summary(conversation_id))
        finally:
            loop.close()
        if summary:
            db.revise_db(
                "UPDATE conversations SET summary = ? WHERE conv_id = ?",
                (summary, conversation_id),
            )
            return jsonify({"success": True, "summary": summary})
        else:
            return jsonify({"error": "生成摘要失败"}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app_logger.error(f"生成摘要时发生错误: {str(e)}")
        return jsonify({"error": f"生成摘要时发生错误: {str(e)}"}), 500


@api_bp.route("/export_dialogs/<int:conv_id>")
@viewer_or_admin_required
def export_dialogs(conv_id):
    """导出完整的私聊对话数据"""
    try:
        # 权限检查
        user_role = session.get("user_role")
        if user_role == "viewer":
            admin_ids = get_admin_ids()
            if admin_ids:
                admin_ids_str = ",".join(map(str, admin_ids))
                conv_check = db.query_db(
                    f"SELECT user_id FROM conversations WHERE conv_id = ? AND user_id NOT IN ({admin_ids_str})",
                    (conv_id,),
                )
                if not conv_check:
                    return jsonify({"error": "对话不存在或您没有权限查看"}), 403
        
        # 获取对话信息
        conversation_data = db.query_db(
            """
            SELECT c.*, u.first_name, u.last_name, u.user_name
            FROM conversations c
            LEFT JOIN users u ON c.user_id = u.uid
            WHERE c.conv_id = ?
            """,
            (conv_id,),
        )
        if not conversation_data:
            return jsonify({"error": "对话不存在"}), 404

        conv_columns = [
            "id",
            "conv_id",
            "user_id",
            "character",
            "preset",
            "summary",
            "create_at",
            "update_at",
            "delete_mark",
            "turns",
            "first_name",
            "last_name",
            "user_name",
        ]
        conversation = {
            conv_columns[i]: conversation_data[0][i] for i in range(len(conv_columns))
        }

        # 获取完整的对话数据（不分页）
        dialogs_data = db.query_db(
            "SELECT * FROM dialogs WHERE conv_id = ? AND turn_order != 0 ORDER BY turn_order ASC",
            (conv_id,),
        )

        dialogs_list = []
        if dialogs_data:
            dialog_columns = [
                "id",
                "conv_id",
                "role",
                "raw_content",
                "turn_order",
                "created_at",
                "processed_content",
                "msg_id",
            ]
            for row in dialogs_data:
                dialog_dict = {
                    dialog_columns[i]: row[i] for i in range(len(dialog_columns))
                }
                dialogs_list.append(dialog_dict)

        return jsonify({
            "success": True,
            "conversation": conversation,
            "dialogs": dialogs_list
        })
    except Exception as e:
        app_logger.error(f"导出对话数据失败: {str(e)}")
        return jsonify({"error": f"导出对话数据失败: {str(e)}"}), 500


@api_bp.route("/conversation/<int:conv_id>/summary", methods=["GET"])
@admin_required
def get_conversation_summary(conv_id):
    """获取对话摘要"""
    try:
        conversation_data = db.query_db(
            "SELECT summary FROM conversations WHERE conv_id = ?", (conv_id,)
        )
        if not conversation_data:
            return jsonify({"error": "对话不存在"}), 404
        summary = conversation_data[0][0] if conversation_data[0][0] else "暂无摘要"
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        app_logger.error(f"获取对话摘要失败: {str(e)}")
        return jsonify({"error": f"获取对话摘要失败: {str(e)}"}), 500


@api_bp.route("/edit_message", methods=["POST"])
@admin_required
def edit_message():
    """编辑消息的processed_content"""
    try:
        data = request.get_json()
        dialog_id = data.get("dialog_id")
        new_content = data.get("content", "").strip()
        if not dialog_id:
            return jsonify({"error": "缺少消息ID"}), 400
        db.revise_db(
            "UPDATE dialogs SET processed_content = ? WHERE id = ?",
            (new_content, dialog_id),
        )
        return jsonify({"success": True, "message": "消息内容已更新"})
    except Exception as e:
        app_logger.error(f"编辑消息失败: {str(e)}")
        return jsonify({"error": f"编辑消息失败: {str(e)}"}), 500


@api_bp.route("/groups/<group_id>", methods=["GET", "PUT"])
@admin_required
def api_group_detail(group_id) -> Union[Response, tuple[Response, int]]:
    """获取或更新群组详细信息API"""
    try:
        group_id = int(group_id)
    except ValueError:
        return jsonify({"error": "Invalid group ID"}), 400

    if request.method == "GET":
        group_data = db.query_db("SELECT * FROM groups WHERE group_id = ?", (group_id,))
        if not group_data:
            return jsonify({"error": "群组不存在"}), 404
        
        group_columns = [
            "group_id", "members_list", "call_count", "keywords", "active",
            "api", "char", "preset", "input_token", "group_name",
            "update_time", "rate", "output_token", "disabled_topics"
        ]
        group_dict = {group_columns[i]: group_data[0][i] for i in range(len(group_columns))}
        return jsonify(group_dict)

    elif request.method == "PUT":
        try:
            data = request.get_json()
            
            # 更新 groups 表
            updates = {}
            allowed_fields = [
                "group_name", "active", "rate", "char", "api", "preset",
                "keywords", "disabled_topics"
            ]
            
            for field in allowed_fields:
                if field in data:
                    updates[field] = data[field]

            if updates:
                updates["update_time"] = datetime.now()
                set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
                params = list(updates.values()) + [group_id]
                sql = f"UPDATE groups SET {set_clause} WHERE group_id = ?"
                db.revise_db(sql, tuple(params))

            return jsonify({"success": True, "message": "群组信息更新成功"})
        except Exception as e:
            app_logger.error(f"更新群组 {group_id} 信息失败: {e}")
            return jsonify({"success": False, "message": str(e)}), 500
    return jsonify({"error": "未处理的请求方法"}), 405



@api_bp.route("/groups/<group_id>/profiles", methods=["GET"])
@admin_required
def api_group_profiles_get(group_id):
    """获取群组的用户画像列表"""
    try:
        group_id = int(group_id)
        profiles = db.group_profiles_get(group_id)
        return jsonify(profiles)
    except Exception as e:
        app_logger.error(f"获取群组 {group_id} 用户画像失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@api_bp.route("/groups/<group_id>/profiles", methods=["POST"])
@admin_required
def api_group_profile_save(group_id):
    """创建或更新群组中的用户画像"""
    try:
        group_id = int(group_id)
        data = request.get_json()
        user_id = data.get("user_id")
        profile_json = data.get("profile_json")

        if not user_id or not profile_json:
            return jsonify({"success": False, "message": "缺少 user_id 或 profile_json"}), 400

        success = db.group_profile_update_or_create(group_id, user_id, profile_json)
        
        if success:
            return jsonify({"success": True, "message": "用户画像保存成功"})
        else:
            return jsonify({"success": False, "message": "保存用户画像失败"}), 500
    except Exception as e:
        app_logger.error(f"保存群组 {group_id} 用户画像失败: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@api_bp.route("/pics/<filename>")
@viewer_or_admin_required
def serve_pic(filename):
    """提供 data/pics 目录下的图片"""
    pics_dir = os.path.join(current_app.root_path, '..', 'data', 'pics')
    return send_from_directory(pics_dir, filename)
