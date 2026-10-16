"""Read-only company audit history for authorized administrators."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from company.store import DB_PATH, authorize_user, initialize_company_store


def list_audit_events(company_id: str, user_id: str, *, limit: int = 200,
                      action: str = "") -> list[dict[str, Any]]:
    authorize_user(company_id, user_id, allowed_roles=["company_admin"])
    limit = max(1, min(int(limit), 1000))
    query = """SELECT a.audit_id,a.user_id,u.name AS user_name,a.workflow_id,a.action,
                     a.resource_type,a.resource_id,a.details_json,a.created_at
              FROM audit_logs a LEFT JOIN company_users u
                ON u.company_id=a.company_id AND u.user_id=a.user_id
              WHERE a.company_id=?"""
    values: list[Any] = [company_id]
    if str(action or "").strip():
        query += " AND lower(a.action) LIKE ?"
        values.append(f"%{str(action).strip().lower()}%")
    query += " ORDER BY a.audit_id DESC LIMIT ?"
    values.append(limit)
    initialize_company_store()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(query, tuple(values)).fetchall()]
    for row in rows:
        try:
            row["details"] = json.loads(row.pop("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            row["details"] = {}
    return rows
