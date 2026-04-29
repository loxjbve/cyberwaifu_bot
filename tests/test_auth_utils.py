from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Flask
import pytest

from utils import auth_utils
from web.blueprints.auth import auth_bp

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def auth_app(monkeypatch, settings_factory):
    settings = settings_factory()
    monkeypatch.setattr(auth_utils, "get_settings", lambda force_reload=False: settings)
    auth_utils.SecurityManager._login_attempts.clear()

    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "web" / "templates"),
        static_folder=str(PROJECT_ROOT / "web" / "static"),
    )
    app.config["TESTING"] = True
    app.secret_key = settings.web.secret_key

    @app.context_processor
    def inject_globals():
        return {"moment": lambda: type("Moment", (), {"timestamp": lambda self: 0})()}

    admin_bp = Blueprint("admin", __name__)

    @admin_bp.route("/")
    def index():
        return "admin-index"

    @admin_bp.route("/viewer")
    @auth_utils.viewer_or_admin_required
    def viewer_page():
        return "viewer-ok"

    @admin_bp.route("/admin-only")
    @auth_utils.admin_required
    def admin_only():
        return "admin-ok"

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    return app


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


def test_viewer_login_can_access_viewer_route_but_not_admin(client):
    response = client.post("/login", data={"password": "viewer-pass"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")

    with client.session_transaction() as session:
        assert session["logged_in"] is True
        assert session["user_role"] == "viewer"

    viewer_response = client.get("/viewer")
    assert viewer_response.status_code == 200
    assert viewer_response.get_data(as_text=True) == "viewer-ok"

    admin_response = client.get("/admin-only")
    assert admin_response.status_code == 302
    assert admin_response.headers["Location"].endswith("/")


def test_expired_session_redirects_to_login(client, monkeypatch):
    client.post("/login", data={"password": "viewer-pass"})
    with client.session_transaction() as session:
        session["last_activity"] = 0

    monkeypatch.setattr(auth_utils.time, "time", lambda: 10_000)
    response = client.get("/viewer")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_page_renders_expected_shell(client):
    response = client.get("/login")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="login-shell"' in body
    assert 'class="login-brand"' in body
    assert 'class="btn-primary btn-login"' in body
    assert 'class="password-icon"' in body
