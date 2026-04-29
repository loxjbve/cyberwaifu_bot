from __future__ import annotations

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from web.factory import format_datetime, get_admin_ids, viewer_or_admin_required
from web.services.admin_query_service import AdminQueryService

admin_bp = Blueprint("admin", __name__)
admin_queries = AdminQueryService()


def format_tokens_m(value):
    if value is None:
        return "0"
    value = int(value)
    if value < 1_000_000:
        return f"{value:,}"
    return f"{value / 1_000_000:.2f}M"


@admin_bp.record_once
def on_load(state):
    state.app.jinja_env.filters["format_tokens_m"] = format_tokens_m

    def highlight_search_keyword(text, keyword):
        if not keyword:
            return text
        return text.replace(keyword, f'<span class="highlight">{keyword}</span>')

    state.app.jinja_env.filters["highlight_search_keyword"] = highlight_search_keyword


def _next_sort_order(sort_by: str, sort_order: str):
    def resolver(column: str) -> str:
        if column == sort_by:
            return "asc" if sort_order.lower() == "desc" else "desc"
        return "desc"

    return resolver


@admin_bp.route("/")
@viewer_or_admin_required
def index():
    user_role = session.get("user_role", "viewer")
    stats = admin_queries.dashboard_stats(
        user_role=user_role,
        admin_ids=get_admin_ids(),
        time_range=request.args.get("time_range", "7d"),
    )
    return render_template("index.html", stats=stats, user_role=user_role)


@admin_bp.route("/users")
@viewer_or_admin_required
def users():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search_term = request.args.get("search", "")
    sort_by = request.args.get("sort_by", "create_at")
    sort_order = request.args.get("sort_order", "desc")
    result = admin_queries.list_users(
        user_role=session.get("user_role", "viewer"),
        admin_ids=get_admin_ids(),
        page=page,
        per_page=per_page,
        search_term=search_term,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return render_template(
        "users.html",
        users=result["users"],
        page=page,
        total_pages=result["total_pages"],
        format_datetime=format_datetime,
        search_term=search_term,
        sort_by=result["sort_by"],
        sort_order=result["sort_order"],
        next_sort_order=_next_sort_order(result["sort_by"], result["sort_order"]),
        per_page=per_page,
        total_users=result["total_users"],
    )


@admin_bp.route("/conversations")
@viewer_or_admin_required
def conversations():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search_term = request.args.get("search", "", type=str).strip()
    sort_by = request.args.get("sort_by", "update_at")
    sort_order = request.args.get("sort_order", "desc")
    result = admin_queries.list_conversations(
        user_role=session.get("user_role", "viewer"),
        admin_ids=get_admin_ids(),
        page=page,
        per_page=per_page,
        search_term=search_term,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return render_template(
        "conversations.html",
        conversations=result["conversations"],
        page=page,
        total_pages=result["total_pages"],
        per_page=per_page,
        total_conversations=result["total_conversations"],
        search=search_term,
        sort_by=result["sort_by"],
        sort_order=result["sort_order"],
        next_sort_order=_next_sort_order(result["sort_by"], result["sort_order"]),
        format_datetime=format_datetime,
    )


@admin_bp.route("/dialogs/<string:conv_id>")
@viewer_or_admin_required
def dialogs(conv_id):
    page = request.args.get("page", 1, type=int)
    per_page = 50
    search_term = request.args.get("search", "", type=str).strip()
    try:
        result = admin_queries.get_conversation_detail(
            conv_id=conv_id,
            user_role=session.get("user_role", "viewer"),
            admin_ids=get_admin_ids(),
            page=page,
            per_page=per_page,
            search_term=search_term,
        )
    except PermissionError:
        flash("Conversation not accessible", "error")
        return redirect(url_for("admin.conversations"))
    except LookupError:
        flash("Conversation not found", "error")
        return redirect(url_for("admin.conversations"))

    return render_template(
        "dialogs.html",
        conversation=result["conversation"],
        dialogs=result["dialogs"],
        detailed_summary=result["detailed_summary"],
        page=page,
        total_pages=result["total_pages"],
        search_keyword=search_term,
        conv_id=conv_id,
        format_datetime=format_datetime,
    )


@admin_bp.route("/groups")
@viewer_or_admin_required
def groups():
    if session.get("user_role") == "viewer":
        abort(403)

    page = request.args.get("page", 1, type=int)
    per_page = 20
    search_term = request.args.get("search", "")
    sort_by = request.args.get("sort_by", "update_time")
    sort_order = request.args.get("sort_order", "desc")
    result = admin_queries.list_groups(
        page=page,
        per_page=per_page,
        search_term=search_term,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return render_template(
        "groups.html",
        groups=result["groups"],
        page=page,
        per_page=per_page,
        total_pages=result["total_pages"],
        total_groups=result["total_groups"],
        format_datetime=format_datetime,
        search_term=search_term,
        sort_by=result["sort_by"],
        sort_order=result["sort_order"],
        next_sort_order=_next_sort_order(result["sort_by"], result["sort_order"]),
    )


@admin_bp.route("/group_dialogs/<group_id>")
@viewer_or_admin_required
def group_dialogs(group_id):
    if session.get("user_role") == "viewer":
        abort(403)

    try:
        group_id_int = int(group_id)
    except ValueError:
        return "Invalid group ID", 400

    page = request.args.get("page", 1, type=int)
    per_page = 50
    search_term = request.args.get("search", "", type=str).strip()
    try:
        result = admin_queries.get_group_dialogs(
            group_id=group_id_int,
            page=page,
            per_page=per_page,
            search_term=search_term,
        )
    except LookupError:
        return "Group not found", 404

    return render_template(
        "group_dialogs.html",
        group=result["group"],
        dialogs=result["dialogs"],
        page=page,
        per_page=per_page,
        total_pages=result["total_pages"],
        total_dialogs=result["total_dialogs"],
        search=search_term or None,
        format_datetime=format_datetime,
    )


@admin_bp.route("/search")
@viewer_or_admin_required
def search():
    if session.get("user_role") == "viewer":
        abort(403)

    query = request.args.get("q", "")
    results = admin_queries.search_everywhere(query) if query else {}
    return render_template(
        "search.html",
        results=results,
        query=query,
        format_datetime=format_datetime,
    )


@admin_bp.route("/config")
@viewer_or_admin_required
def config_management():
    return render_template("config.html")


@admin_bp.route("/config/files")
@viewer_or_admin_required
def config_files_management():
    return render_template("config_files.html")


@admin_bp.route("/database")
@viewer_or_admin_required
def database_viewer():
    active_table = request.args.get("table_name")
    page = request.args.get("page", 1, type=int)
    per_page = 200
    search_data_term = request.args.get("search_data", "")
    search_table_term = request.args.get("search_table", "")

    try:
        result = admin_queries.database_view(
            active_table=active_table,
            page=page,
            per_page=per_page,
            search_term=search_data_term,
            search_table_term=search_table_term,
        )
    except LookupError:
        flash("Table not found", "error")
        return redirect(url_for("admin.database_viewer"))

    return render_template(
        "database.html",
        table_names=result["table_names"],
        active_table=active_table,
        table_data=result["table_data"],
        page=page,
        per_page=per_page,
        format_datetime=format_datetime,
    )


@admin_bp.route("/analysis_preview")
@viewer_or_admin_required
def analysis_preview():
    if session.get("user_role") == "viewer":
        abort(403)

    page = request.args.get("page", 1, type=int)
    per_page = 20
    result = admin_queries.analysis_items(page=page, per_page=per_page)
    items = [
        {
            "image_url": url_for("api.serve_pic", filename=item["file_name"]),
            "content": item["content"],
            "user_name": item["user_name"],
            "date_time": item["date_time"],
        }
        for item in result["items"]
    ]
    return render_template(
        "analysis_preview.html",
        items=items,
        page=page,
        total_pages=result["total_pages"],
    )


@admin_bp.route("/api/analysis_previews")
@viewer_or_admin_required
def api_analysis_previews():
    if session.get("user_role") == "viewer":
        abort(403)

    page = request.args.get("page", 1, type=int)
    per_page = 20
    result = admin_queries.analysis_items(page=page, per_page=per_page)
    items = [
        {
            "image_url": url_for("api.serve_pic", filename=item["file_name"]),
            "content": item["content"],
            "user_name": item["user_name"],
            "date_time": item["date_time"],
        }
        for item in result["items"]
    ]
    return jsonify(
        {
            "items": items,
            "has_next": page < result["total_pages"],
        }
    )
