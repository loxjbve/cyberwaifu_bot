from flask import Blueprint, redirect, render_template, request, url_for

from utils.auth_utils import AuthManager, SessionManager, get_client_ip

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if SessionManager.validate_session():
        return redirect(url_for("admin.index"))

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        success, _, error = AuthManager.login(password, get_client_ip())
        if success:
            next_page = request.args.get("next")
            if next_page and next_page.startswith("/"):
                return redirect(next_page)
            return redirect(url_for("admin.index"))

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    AuthManager.logout()
    return redirect(url_for("auth.login"))
