from __future__ import annotations

import asyncio
import json
import os
from typing import Union

from flask import Blueprint, Response, current_app, jsonify, request, send_from_directory, session

from agent.llm_functions import generate_summary
from utils.config_utils import get_settings
from web.factory import admin_required, app_logger, get_admin_ids, viewer_or_admin_required
from web.services.config_file_service import ConfigFileService
from web.services.user_admin_service import UserAdminService

api_bp = Blueprint("api", __name__, url_prefix="/api")
admin_service = UserAdminService()


def _project_root() -> str:
    return get_settings().project_root


def _config_service() -> ConfigFileService:
    return ConfigFileService(_project_root())


@api_bp.route("/message_page/<group_id>/<msg_id>")
@admin_required
def get_message_page(group_id, msg_id):
    try:
        payload = admin_service.get_message_page(int(group_id), int(msg_id))
    except ValueError:
        return jsonify({"error": "Invalid group ID"}), 400
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    return jsonify(payload)


@api_bp.route("/export_group_dialogs/<group_id>")
@admin_required
def export_group_dialogs(group_id):
    try:
        payload = admin_service.export_group_dialogs(int(group_id))
    except ValueError:
        return jsonify({"error": "Invalid group ID"}), 400
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    return jsonify(payload)


@api_bp.route("/user/<int:user_id>", methods=["GET", "PUT"])
@viewer_or_admin_required
def api_user_detail(user_id) -> Union[Response, tuple[Response, int]]:
    user_role = session.get("user_role", "viewer")
    admin_ids = get_admin_ids()

    if request.method == "GET":
        try:
            payload = admin_service.get_user_detail(
                user_id,
                user_role=user_role,
                admin_ids=admin_ids,
            )
        except PermissionError as error:
            return jsonify({"error": str(error)}), 403
        except LookupError as error:
            return jsonify({"error": str(error)}), 404
        return jsonify(payload)

    if user_role != "admin":
        return jsonify({"error": "Admin permission required"}), 403

    try:
        payload = request.get_json() or {}
        result = admin_service.update_user(user_id, payload)
    except Exception as error:
        app_logger.error("Failed to update user %s: %s", user_id, error)
        return jsonify({"success": False, "message": str(error)}), 500
    return jsonify(result)


@api_bp.route("/config/list")
@admin_required
def api_config_list():
    try:
        return jsonify(_config_service().list_files())
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@api_bp.route("/config/read")
@admin_required
def api_config_read():
    try:
        rel_path = request.args.get("path")
        if not rel_path:
            return jsonify({"error": "Missing path"}), 400
        return jsonify(_config_service().read_file(rel_path))
    except json.JSONDecodeError as error:
        return jsonify({"error": f"Invalid JSON: {error}"}), 400
    except PermissionError as error:
        return jsonify({"error": str(error)}), 403
    except FileNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@api_bp.route("/config/save", methods=["POST"])
@admin_required
def api_config_save():
    try:
        payload = request.get_json() or {}
        rel_path = payload.get("path")
        content = payload.get("content")
        if not rel_path or content is None:
            return jsonify({"error": "Missing path or content"}), 400
        return jsonify(_config_service().save_file(rel_path, content))
    except PermissionError as error:
        return jsonify({"error": str(error)}), 403
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@api_bp.route("/config/create", methods=["POST"])
@admin_required
def api_config_create():
    try:
        payload = request.get_json() or {}
        category = payload.get("category")
        filename = payload.get("filename")
        content = payload.get("content", {})
        if not category or not filename:
            return jsonify({"error": "Missing category or filename"}), 400
        return jsonify(_config_service().create_file(category, filename, content))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except PermissionError as error:
        return jsonify({"error": str(error)}), 403
    except FileExistsError as error:
        return jsonify({"error": str(error)}), 409
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@api_bp.route("/config/delete", methods=["POST"])
@admin_required
def api_config_delete():
    try:
        payload = request.get_json() or {}
        rel_path = payload.get("path")
        if not rel_path:
            return jsonify({"error": "Missing path"}), 400
        return jsonify(_config_service().delete_file(rel_path))
    except PermissionError as error:
        return jsonify({"error": str(error)}), 403
    except FileNotFoundError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@api_bp.route("/generate_summary", methods=["POST"])
@admin_required
def api_generate_summary():
    try:
        if not request.is_json:
            return jsonify({"error": "JSON body required"}), 400

        payload = request.get_json()
        if payload is None:
            return jsonify({"error": "Invalid JSON body"}), 400

        conversation_id = payload.get("conversation_id")
        if not conversation_id:
            return jsonify({"error": "Missing conversation_id"}), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            summary = loop.run_until_complete(generate_summary(conversation_id))
        finally:
            loop.close()

        if not summary:
            return jsonify({"error": "Failed to generate summary"}), 500

        admin_service.update_conversation_summary(int(conversation_id), summary)
        return jsonify({"success": True, "summary": summary})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app_logger.error("Failed to generate summary: %s", error)
        return jsonify({"error": str(error)}), 500


@api_bp.route("/export_dialogs/<int:conv_id>")
@viewer_or_admin_required
def export_dialogs(conv_id):
    try:
        payload = admin_service.export_private_dialogs(
            conv_id,
            user_role=session.get("user_role", "viewer"),
            admin_ids=get_admin_ids(),
        )
    except PermissionError as error:
        return jsonify({"error": str(error)}), 403
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        app_logger.error("Failed to export conversation %s: %s", conv_id, error)
        return jsonify({"error": str(error)}), 500
    return jsonify(payload)


@api_bp.route("/conversation/<int:conv_id>/summary", methods=["GET"])
@admin_required
def get_conversation_summary(conv_id):
    try:
        payload = admin_service.get_conversation_summary(conv_id)
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        app_logger.error("Failed to get conversation summary %s: %s", conv_id, error)
        return jsonify({"error": str(error)}), 500
    return jsonify(payload)


@api_bp.route("/edit_message", methods=["POST"])
@admin_required
def edit_message():
    try:
        payload = request.get_json() or {}
        dialog_id = payload.get("dialog_id")
        if not dialog_id:
            return jsonify({"error": "Missing dialog_id"}), 400
        result = admin_service.edit_message(int(dialog_id), (payload.get("content") or "").strip())
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        app_logger.error("Failed to edit message: %s", error)
        return jsonify({"error": str(error)}), 500
    return jsonify(result)


@api_bp.route("/groups/<group_id>", methods=["GET", "PUT"])
@admin_required
def api_group_detail(group_id) -> Union[Response, tuple[Response, int]]:
    try:
        group_id_int = int(group_id)
    except ValueError:
        return jsonify({"error": "Invalid group ID"}), 400

    if request.method == "GET":
        try:
            payload = admin_service.get_group_detail(group_id_int)
        except LookupError as error:
            return jsonify({"error": str(error)}), 404
        return jsonify(payload)

    try:
        result = admin_service.update_group(group_id_int, request.get_json() or {})
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        app_logger.error("Failed to update group %s: %s", group_id, error)
        return jsonify({"success": False, "message": str(error)}), 500
    return jsonify(result)


@api_bp.route("/groups/<group_id>/profiles", methods=["GET"])
@admin_required
def api_group_profiles_get(group_id):
    try:
        payload = admin_service.get_group_profiles(int(group_id))
    except ValueError:
        return jsonify({"error": "Invalid group ID"}), 400
    except Exception as error:
        app_logger.error("Failed to load group profiles %s: %s", group_id, error)
        return jsonify({"success": False, "message": str(error)}), 500
    return jsonify(payload)


@api_bp.route("/groups/<group_id>/profiles", methods=["POST"])
@admin_required
def api_group_profile_save(group_id):
    try:
        payload = request.get_json() or {}
        user_id = payload.get("user_id")
        profile_json = payload.get("profile_json")
        if not user_id or not profile_json:
            return jsonify({"success": False, "message": "Missing user_id or profile_json"}), 400

        result = admin_service.save_group_profile(
            int(group_id),
            int(user_id),
            profile_json,
        )
    except ValueError:
        return jsonify({"error": "Invalid group ID or user ID"}), 400
    except Exception as error:
        app_logger.error("Failed to save group profile %s: %s", group_id, error)
        return jsonify({"success": False, "message": str(error)}), 500
    return jsonify(result)


@api_bp.route("/pics/<filename>")
@viewer_or_admin_required
def serve_pic(filename):
    pics_dir = os.path.join(current_app.root_path, "..", "data", "pics")
    return send_from_directory(pics_dir, filename)
