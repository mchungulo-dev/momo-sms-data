from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from typing import Any

import mysql.connector
from mysql.connector import Error, IntegrityError


USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
MAX_FAILED_ATTEMPTS = 5
BLOCK_SECONDS = 60
_failed_attempts: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


class AuthError(Exception):
    """Expected registration or authentication error."""


class DuplicateUserError(AuthError):
    """Username or email already exists."""


class InvalidRegistrationError(AuthError):
    """Registration data does not meet the security rules."""


def _db_config() -> dict[str, Any]:
    password = os.getenv("MOMO_DB_PASSWORD")
    if not password:
        raise AuthError("MOMO_DB_PASSWORD is not configured")
    return {
        "host": os.getenv("MOMO_DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("MOMO_DB_PORT", "3306")),
        "user": os.getenv("MOMO_DB_USER", "momo_app"),
        "password": password,
        "database": os.getenv("MOMO_DB_NAME", "momo"),
        "autocommit": False,
    }


def _connect():
    try:
        return mysql.connector.connect(**_db_config())
    except Error as error:
        raise AuthError(f"Could not connect to MySQL: {error}") from error


def initialize_user_database() -> None:
    """Create the users table if it does not already exist."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                username VARCHAR(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
                email VARCHAR(254) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
                password_salt VARBINARY(16) NOT NULL,
                password_hash VARBINARY(32) NOT NULL,
                role ENUM('viewer', 'operator', 'admin') NOT NULL DEFAULT 'viewer',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_users_username (username),
                UNIQUE KEY uq_users_email (email)
            ) ENGINE=InnoDB
            """
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def _validate_registration(username: Any, email: Any, password: Any) -> tuple[str, str, str]:
    username = username.strip() if isinstance(username, str) else username
    email = email.strip().lower() if isinstance(email, str) else email

    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
        raise InvalidRegistrationError(
            "username must be 3-30 characters using letters, numbers, _, ., or -"
        )
    if not isinstance(email, str) or len(email) > 254 or not EMAIL_RE.fullmatch(email):
        raise InvalidRegistrationError("email must be a valid email address")
    if not isinstance(password, str) or len(password) < 12 or len(password) > 128:
        raise InvalidRegistrationError("password must contain 12-128 characters")
    if any(character.isspace() for character in password):
        raise InvalidRegistrationError("password must not contain whitespace")
    if not re.search(r"[A-Z]", password):
        raise InvalidRegistrationError("password must contain an uppercase letter")
    if not re.search(r"[a-z]", password):
        raise InvalidRegistrationError("password must contain a lowercase letter")
    if not re.search(r"\d", password):
        raise InvalidRegistrationError("password must contain a number")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise InvalidRegistrationError("password must contain a special character")
    return username, email, password


def _hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 300_000)
    return salt, digest


def register_user(username: Any, email: Any, password: Any, invite_code: Any = None) -> dict[str, Any]:
    """Create a user with a hashed password and unique username/email."""
    username, email, password = _validate_registration(username, email, password)
    salt, password_hash = _hash_password(password)
    configured_invite = os.getenv("ADMIN_INVITE_CODE")
    role = (
        "admin"
        if configured_invite
        and isinstance(invite_code, str)
        and secrets.compare_digest(invite_code, configured_invite)
        else "viewer"
    )

    connection = _connect()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users (username, email, password_salt, password_hash, role)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (username, email, salt, password_hash, role),
        )
        connection.commit()
        return {
            "id": cursor.lastrowid,
            "username": username,
            "email": email,
            "role": role,
        }
    except IntegrityError as error:
        connection.rollback()
        raise DuplicateUserError("username or email is already registered") from error
    finally:
        cursor.close()
        connection.close()


def _client_ip(handler: Any) -> str:
    return str(handler.client_address[0]) if handler.client_address else "unknown"


def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        attempts = [stamp for stamp in _failed_attempts.get(ip, []) if now - stamp < BLOCK_SECONDS]
        _failed_attempts[ip] = attempts
        return len(attempts) >= MAX_FAILED_ATTEMPTS


def _record_failure(ip: str) -> None:
    with _rate_lock:
        _failed_attempts.setdefault(ip, []).append(time.monotonic())


def _clear_failures(ip: str) -> None:
    with _rate_lock:
        _failed_attempts.pop(ip, None)


def authenticate_request(handler: Any) -> bool:
    """Authenticate Basic Auth against the registered MySQL users."""
    ip = _client_ip(handler)
    if _is_rate_limited(ip):
        return False

    authorization = handler.headers.get("Authorization")
    if not authorization:
        return False

    try:
        scheme, encoded = authorization.split(" ", 1)
        if scheme.lower() != "basic":
            raise ValueError("unsupported scheme")
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        _record_failure(ip)
        return False

    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, username, email, password_salt, password_hash, role
            FROM users
            WHERE username = %s COLLATE utf8mb4_unicode_ci
            LIMIT 1
            """,
            (username.strip(),),
        )
        user = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()

    valid = False
    if user is not None:
        _, actual_hash = _hash_password(password, bytes(user["password_salt"]))
        valid = hmac.compare_digest(actual_hash, bytes(user["password_hash"]))

    if not valid:
        _record_failure(ip)
        return False

    _clear_failures(ip)
    handler.authenticated_user = {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
    }
    return True


def current_user(handler: Any) -> dict[str, Any] | None:
    return getattr(handler, "authenticated_user", None)


def role_allows(handler: Any, method: str) -> bool:
    user = current_user(handler)
    if user is None:
        return False
    permissions = {
        "viewer": {"GET", "OPTIONS"},
        "operator": {"GET", "POST", "PUT", "OPTIONS"},
        "admin": {"GET", "POST", "PUT", "DELETE", "OPTIONS"},
    }
    return method.upper() in permissions.get(user["role"], set())
