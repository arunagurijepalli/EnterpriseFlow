"""One-time hashed account activation and password reset tokens."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from company.auth import hash_password
from company.store import DB_PATH, initialize_company_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_account_token(company_id: str, user_id: str, token_type: str, lifetime_minutes: int = 60) -> str:
    if token_type not in {"activation", "password_reset"}:
        raise ValueError("Unsupported account token type")
    initialize_company_store()
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = _now()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("UPDATE account_tokens SET used_at=? WHERE company_id=? AND user_id=? AND token_type=? AND used_at=''", (now.isoformat(), company_id, user_id, token_type))
        conn.execute("INSERT INTO account_tokens(company_id,user_id,token_hash,token_type,expires_at,created_at) VALUES(?,?,?,?,?,?)",
                     (company_id, user_id, token_hash, token_type, (now + timedelta(minutes=lifetime_minutes)).isoformat(), now.isoformat()))
    return raw_token


def consume_account_token(token: str, new_password: str = "") -> dict:
    raw_token = str(token or "").strip()
    if not raw_token:
        raise ValueError("This account link is invalid or has expired.")
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    initialize_company_store()
    now = _now()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM account_tokens WHERE token_hash=? AND used_at=''", (token_hash,)).fetchone()
        if not row or datetime.fromisoformat(row["expires_at"]) <= now:
            if row:
                conn.execute("UPDATE account_tokens SET used_at=? WHERE token_id=?", (now.isoformat(), row["token_id"]))
            raise ValueError("This account link is invalid or has expired.")
        if row["token_type"] == "password_reset" or row["token_type"] == "activation":
            salt, password_hash = hash_password(new_password)
            conn.execute("UPDATE company_users SET password_hash=?,password_salt=?,account_status='active',failed_attempts=0,locked_until='',updated_at=? WHERE company_id=? AND user_id=?",
                         (password_hash, salt, now.isoformat(), row["company_id"], row["user_id"]))
        conn.execute("UPDATE account_tokens SET used_at=? WHERE token_id=? AND used_at=''", (now.isoformat(), row["token_id"]))
        user = conn.execute("SELECT user_id,company_id,email FROM company_users WHERE company_id=? AND user_id=?", (row["company_id"], row["user_id"])).fetchone()
    return dict(user) if user else {}
