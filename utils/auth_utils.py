"""
Shared authentication and authorization helpers for the Flask admin.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from flask import flash, redirect, request, session, url_for

from utils.config_utils import get_settings

logger = logging.getLogger(__name__)


class Permission:
    ADMIN = "admin"
    VIEWER = "viewer"

    LEVELS = {
        VIEWER: 1,
        ADMIN: 2,
    }

    @classmethod
    def has_permission(cls, user_permission: str, required_permission: str) -> bool:
        return cls.LEVELS.get(user_permission, 0) >= cls.LEVELS.get(required_permission, 0)


class AuthConfig:
    @staticmethod
    def get_passwords() -> Dict[str, str]:
        settings = get_settings()
        return {
            "admin": settings.web.admin_password,
            "viewer": settings.web.viewer_password,
        }

    @staticmethod
    def get_admin_ids() -> List[int]:
        return list(get_settings().admin_ids)

    @staticmethod
    def get_session_timeout() -> int:
        return get_settings().web.session_timeout

    @staticmethod
    def get_max_login_attempts() -> int:
        return get_settings().web.max_login_attempts

    @staticmethod
    def get_lockout_duration() -> int:
        return get_settings().web.lockout_duration


class SessionManager:
    @staticmethod
    def create_session(user_permission: str, user_data: Optional[Dict[str, Any]] = None) -> str:
        session_id = secrets.token_urlsafe(32)
        current_time = time.time()

        session["logged_in"] = True
        session["user_permission"] = user_permission
        session["user_role"] = user_permission
        session["session_id"] = session_id
        session["login_time"] = current_time
        session["last_activity"] = current_time
        session.permanent = True

        if user_data:
            session["user_data"] = user_data

        logger.info("Created session for role=%s session_id=%s", user_permission, session_id)
        return session_id

    @staticmethod
    def validate_session() -> bool:
        if "logged_in" not in session:
            return False

        current_time = time.time()
        last_activity = session.get("last_activity", 0)
        timeout = AuthConfig.get_session_timeout()

        if current_time - last_activity > timeout:
            SessionManager.destroy_session()
            logger.warning("Session expired and has been cleared")
            return False

        session["last_activity"] = current_time
        return True

    @staticmethod
    def destroy_session() -> None:
        session_id = session.get("session_id", "unknown")
        session.clear()
        logger.warning("Session destroyed session_id=%s", session_id)

    @staticmethod
    def get_user_permission() -> Optional[str]:
        if SessionManager.validate_session():
            return session.get("user_permission") or session.get("user_role")
        return None

    @staticmethod
    def get_session_info() -> Dict[str, Any]:
        if not SessionManager.validate_session():
            return {}

        permission = session.get("user_permission") or session.get("user_role")
        return {
            "user_permission": permission,
            "session_id": session.get("session_id"),
            "login_time": session.get("login_time"),
            "last_activity": session.get("last_activity"),
            "user_data": session.get("user_data", {}),
        }


class SecurityManager:
    _login_attempts: Dict[str, Dict[str, float | int]] = {}

    @classmethod
    def record_login_attempt(cls, ip_address: str, success: bool) -> None:
        current_time = time.time()

        if ip_address not in cls._login_attempts:
            cls._login_attempts[ip_address] = {
                "attempts": 0,
                "last_attempt": current_time,
                "locked_until": 0,
            }

        attempt_data = cls._login_attempts[ip_address]

        if success:
            attempt_data["attempts"] = 0
            attempt_data["locked_until"] = 0
            return

        attempt_data["attempts"] += 1
        attempt_data["last_attempt"] = current_time

        if attempt_data["attempts"] >= AuthConfig.get_max_login_attempts():
            attempt_data["locked_until"] = current_time + AuthConfig.get_lockout_duration()
            logger.warning("Locked login IP %s after repeated failures", ip_address)

    @classmethod
    def is_ip_locked(cls, ip_address: str) -> bool:
        attempt_data = cls._login_attempts.get(ip_address)
        if not attempt_data:
            return False
        return time.time() < float(attempt_data.get("locked_until", 0))

    @classmethod
    def get_remaining_lockout_time(cls, ip_address: str) -> int:
        attempt_data = cls._login_attempts.get(ip_address)
        if not attempt_data:
            return 0

        remaining = float(attempt_data.get("locked_until", 0)) - time.time()
        return int(remaining) if remaining > 0 else 0

    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        if salt is None:
            salt = secrets.token_hex(16)

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000,
        )
        return password_hash.hex(), salt

    @staticmethod
    def verify_password(password: str, password_hash: str, salt: str) -> bool:
        computed_hash, _ = SecurityManager.hash_password(password, salt)
        return secrets.compare_digest(computed_hash, password_hash)


class AuthManager:
    @staticmethod
    def authenticate(password: str, ip_address: str) -> Tuple[bool, Optional[str], Optional[str]]:
        if SecurityManager.is_ip_locked(ip_address):
            remaining_time = SecurityManager.get_remaining_lockout_time(ip_address)
            return False, None, f"登录失败次数过多，请在 {remaining_time} 秒后重试"

        passwords = AuthConfig.get_passwords()

        user_permission = None
        if password == passwords["admin"]:
            user_permission = Permission.ADMIN
        elif password == passwords["viewer"]:
            user_permission = Permission.VIEWER

        success = user_permission is not None
        SecurityManager.record_login_attempt(ip_address, success)

        if success:
            logger.info("Authenticated role=%s ip=%s", user_permission, ip_address)
            return True, user_permission, None

        logger.warning("Authentication failed ip=%s", ip_address)
        return False, None, "密码错误"

    @staticmethod
    def login(password: str, ip_address: str) -> Tuple[bool, Optional[str], Optional[str]]:
        success, user_permission, error_msg = AuthManager.authenticate(password, ip_address)
        if success and user_permission:
            SessionManager.create_session(user_permission)
            return True, user_permission, None
        return False, None, error_msg

    @staticmethod
    def logout() -> None:
        SessionManager.destroy_session()

    @staticmethod
    def get_current_user() -> Dict[str, Any]:
        session_info = SessionManager.get_session_info()
        if not session_info:
            return {}

        permission = session_info.get("user_permission")
        return {
            "permission": permission,
            "is_admin": permission == Permission.ADMIN,
            "is_viewer": permission == Permission.VIEWER,
            "login_time": session_info.get("login_time"),
            "session_id": session_info.get("session_id"),
        }


def permission_required(required_permission: str):
    def decorator(func):
        @wraps(func)
        def decorated_function(*args, **kwargs):
            if not SessionManager.validate_session():
                flash("请先登录", "warning")
                return redirect(url_for("auth.login", next=request.url))

            user_permission = SessionManager.get_user_permission()
            if not user_permission or not Permission.has_permission(
                user_permission, required_permission
            ):
                flash("您没有权限访问此页面", "error")
                return redirect(url_for("admin.index"))

            return func(*args, **kwargs)

        return decorated_function

    return decorator


def admin_required(func):
    return permission_required(Permission.ADMIN)(func)


def viewer_required(func):
    return permission_required(Permission.VIEWER)(func)


def viewer_or_admin_required(func):
    return permission_required(Permission.VIEWER)(func)


def get_admin_ids() -> List[int]:
    return AuthConfig.get_admin_ids()


def get_client_ip() -> str:
    if request.environ.get("HTTP_X_FORWARDED_FOR"):
        return request.environ["HTTP_X_FORWARDED_FOR"].split(",")[0].strip()
    if request.environ.get("HTTP_X_REAL_IP"):
        return request.environ["HTTP_X_REAL_IP"]
    return request.environ.get("REMOTE_ADDR", "127.0.0.1")
