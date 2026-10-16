from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

from company.store import (
    DB_PATH,
    get_user_by_email,
    initialize_company_store,
    set_user_auth_state,
)

ITERATIONS = 210_000
SALT_BYTES = 16
LOCK_AFTER_FAILURES = 5
LOCK_MINUTES = 5

GENERIC_LOGIN_ERROR = "Invalid email or password."


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def hash_password(password: str) -> Tuple[str, str]:
    password = str(password)

    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")

    salt = os.urandom(SALT_BYTES)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERATIONS,
    )

    return _encode(salt), _encode(digest)


def verify_password(
    password: str,
    salt: str,
    expected_hash: str,
) -> bool:

    if not password or not salt or not expected_hash:
        return False

    try:
        salt_bytes = _decode(salt)
        expected = _decode(expected_hash)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt_bytes,
        ITERATIONS,
    )

    return hmac.compare_digest(actual, expected)


def set_password(
    user_id: str,
    password: str,
) -> Dict[str, Any]:

    salt, password_hash = hash_password(password)

    return set_user_auth_state(
        user_id,
        password_hash=password_hash,
        password_salt=salt,
        failed_attempts=0,
        locked_until="",
    )


def _check_lock(user: Dict[str, Any]) -> None:

    locked_until_raw = str(
        user.get("locked_until") or ""
    ).strip()

    if not locked_until_raw:
        return

    try:
        locked_until = datetime.fromisoformat(
            locked_until_raw
        )
    except ValueError:
        return

    if locked_until > _utc_now():
        raise PermissionError(
            "Too many failed attempts. Please try again in a few minutes."
        )


def _verify_user_password(
    user: Dict[str, Any],
    password: str,
    generic_error: str,
) -> Dict[str, Any]:

    if not user:
        raise PermissionError(generic_error)

    if str(user.get("status", "")).lower() != "active":
        raise PermissionError(generic_error)

    if str(user.get("account_status", "active")).lower() != "active":
        raise PermissionError("This account is not activated yet. Use the activation link sent to your work email.")

    _check_lock(user)

    valid = verify_password(
        password,
        str(user.get("password_salt") or ""),
        str(user.get("password_hash") or ""),
    )

    if not valid:

        failures = int(
            user.get("failed_attempts") or 0
        ) + 1

        updates: Dict[str, Any] = {
            "failed_attempts": failures
        }

        if failures >= LOCK_AFTER_FAILURES:

            updates["locked_until"] = (
                _utc_now()
                + timedelta(minutes=LOCK_MINUTES)
            ).isoformat()

            updates["failed_attempts"] = 0

        set_user_auth_state(
            user["user_id"],
            **updates,
        )

        raise PermissionError(generic_error)

    set_user_auth_state(
        user["user_id"],
        failed_attempts=0,
        locked_until="",
        last_login_at=_utc_now().isoformat(),
    )

    return user


def _find_unique_user_by_email(
    email: str,
) -> Optional[Dict[str, Any]]:

    initialize_company_store()

    normalized_email = str(email or "").strip().lower()

    if not normalized_email:
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(
            """
            SELECT
                user_id,
                company_id,
                name,
                email,
                role,
                department,
                status,
                password_hash,
                password_salt,
                failed_attempts,
                locked_until,
                last_login_at,
                created_at,
                updated_at
            FROM company_users
            WHERE lower(trim(email)) = ?
            ORDER BY user_id
            """,
            (normalized_email,),
        ).fetchall()
    finally:
        conn.close()

    # A login email should resolve to exactly one account.
    if len(rows) != 1:
        return None

    return dict(rows[0])


def _role_is_allowed(
    role: str,
    allowed_roles: Optional[Iterable[str]],
) -> bool:

    if allowed_roles is None:
        return True

    allowed = {
        str(item).strip().lower()
        for item in allowed_roles
    }

    return str(role).strip().lower() in allowed


def authenticate_user(
    company_id: str,
    email: str,
    password: str,
) -> Dict[str, Any]:
    """
    Backward-compatible tenant-aware authentication.
    """

    user = get_user_by_email(
        company_id,
        email,
    )

    result = _verify_user_password(
        user,
        password,
        "Invalid company ID, email, or password.",
    )

    return get_user_by_email(
        result["company_id"],
        result["email"],
    )


def authenticate_user_by_email(
    email: str,
    password: str,
    allowed_roles: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """
    Authenticate without exposing company ID to the user.

    The backend resolves the user's company, role and department
    from the authenticated account.
    """

    user = _find_unique_user_by_email(email)

    result = _verify_user_password(
        user,
        password,
        GENERIC_LOGIN_ERROR,
    )

    if not _role_is_allowed(
        result.get("role", ""),
        allowed_roles,
    ):
        raise PermissionError(
            GENERIC_LOGIN_ERROR
        )

    return get_user_by_email(
        result["company_id"],
        result["email"],
    )
