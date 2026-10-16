"""Tenant-scoped user profile settings and profile photo storage."""
from __future__ import annotations

from contextlib import contextmanager

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from company.store import DB_PATH, authorize_user


@contextmanager
def _connect():
    """Yield a configured connection and always commit/close it."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_user_profile_table() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_user_profiles (
                company_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                avatar_data BLOB,
                avatar_filename TEXT NOT NULL DEFAULT '',
                avatar_mime TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (company_id, user_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_company_user_profiles_company "
            "ON company_user_profiles(company_id)"
        )
        conn.commit()


def get_user_profile_settings(company_id: str, user_id: str) -> Dict[str, Any]:
    authorize_user(company_id, user_id)
    ensure_user_profile_table()
    with _connect() as conn:
        row = conn.execute(
            "SELECT company_id, user_id, phone, location, avatar_data, "
            "avatar_filename, avatar_mime, updated_at FROM company_user_profiles "
            "WHERE company_id=? AND user_id=?",
            (company_id, user_id),
        ).fetchone()
    return dict(row) if row else {
        "company_id": company_id, "user_id": user_id, "phone": "",
        "location": "", "avatar_data": None, "avatar_filename": "",
        "avatar_mime": "", "updated_at": "",
    }


def save_user_profile_settings(
    company_id: str,
    user_id: str,
    *,
    phone: str = "",
    location: str = "",
) -> Dict[str, Any]:
    authorize_user(company_id, user_id)
    phone = str(phone or "").strip()
    location = str(location or "").strip()
    if len(phone) > 40:
        return {"status": "invalid", "message": "Phone number must be 40 characters or fewer."}
    if len(location) > 120:
        return {"status": "invalid", "message": "Location must be 120 characters or fewer."}
    ensure_user_profile_table()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO company_user_profiles
                (company_id,user_id,phone,location,updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(company_id,user_id) DO UPDATE SET
                phone=excluded.phone, location=excluded.location,
                updated_at=excluded.updated_at
            """,
            (company_id, user_id, phone, location, _now()),
        )
        conn.commit()
    return {"status": "success", "message": "Profile details saved successfully."}


def save_user_profile_photo(
    company_id: str,
    user_id: str,
    *,
    file_name: str,
    file_data: bytes,
    mime_type: str = "",
) -> Dict[str, Any]:
    """Save a validated raster image for the authenticated user's own profile."""
    authorize_user(company_id, user_id)
    name = Path(str(file_name or "").replace("\\", "/")).name
    data = bytes(file_data or b"")
    if not name or not data:
        return {"status": "invalid", "message": "Choose a profile photo first."}
    if len(data) > 2 * 1024 * 1024:
        return {"status": "invalid", "message": "Profile photos must be 2 MB or smaller."}
    ext = Path(name).suffix.casefold()
    detected = ""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        detected = "image/webp"
    allowed = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    if ext not in allowed or detected != allowed[ext]:
        return {"status": "invalid", "message": "Use a valid PNG, JPG, or WebP image."}
    if mime_type and mime_type not in {detected, "application/octet-stream"}:
        return {"status": "invalid", "message": "The selected image type does not match its content."}
    ensure_user_profile_table()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO company_user_profiles
                (company_id,user_id,avatar_data,avatar_filename,avatar_mime,updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(company_id,user_id) DO UPDATE SET
                avatar_data=excluded.avatar_data,
                avatar_filename=excluded.avatar_filename,
                avatar_mime=excluded.avatar_mime,
                updated_at=excluded.updated_at
            """,
            (company_id, user_id, sqlite3.Binary(data), name, detected, _now()),
        )
        conn.commit()
    return {"status": "success", "message": "Profile photo updated."}


def delete_user_profile_photo(company_id: str, user_id: str) -> Dict[str, Any]:
    authorize_user(company_id, user_id)
    ensure_user_profile_table()
    with _connect() as conn:
        conn.execute(
            "UPDATE company_user_profiles SET avatar_data=NULL, avatar_filename='', "
            "avatar_mime='', updated_at=? WHERE company_id=? AND user_id=?",
            (_now(), company_id, user_id),
        )
        conn.commit()
    return {"status": "success", "message": "Profile photo removed."}
