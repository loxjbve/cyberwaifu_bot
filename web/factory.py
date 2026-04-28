import logging
import os
import sys
from datetime import datetime
from typing import Optional

from flask import Flask

from utils.auth_utils import (
    admin_required,
    get_admin_ids,
    viewer_or_admin_required,
    viewer_required,
)
from utils.config_utils import AppSettings, get_settings


def setup_app_logging() -> logging.Logger:
    app_logger = logging.getLogger(__name__)
    app_logger.setLevel(logging.DEBUG)
    app_logger.propagate = True
    return app_logger


app_logger = setup_app_logging()


def format_datetime(timestamp):
    if timestamp:
        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        return str(timestamp)
    return "未知"


def format_large_number(value):
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def highlight_search_keyword(text, keyword):
    import re

    if not keyword:
        return text
    return re.sub(f"(?i)({re.escape(keyword)})", r"<mark>\1</mark>", text)


def create_app(settings: Optional[AppSettings] = None) -> Flask:
    active_settings = settings or get_settings()
    project_root = active_settings.project_root
    if project_root not in sys.path:
        sys.path.append(project_root)

    os.environ["DB_PATH"] = active_settings.database.path

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = active_settings.web.secret_key
    app.config["PERMANENT_SESSION_LIFETIME"] = active_settings.web.session_timeout

    @app.context_processor
    def inject_globals():
        return dict(moment=lambda: datetime.now(), max=max, min=min, range=range)

    app.jinja_env.filters["format_datetime"] = format_datetime
    app.jinja_env.filters["format_large_number"] = format_large_number
    app.jinja_env.filters["highlight_search_keyword"] = highlight_search_keyword

    from .blueprints.auth import auth_bp
    from .blueprints.admin import admin_bp
    from .blueprints.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    return app
