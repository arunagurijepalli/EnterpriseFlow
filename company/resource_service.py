"""Tenant-scoped shared company links."""
from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from company.store import DB_PATH, authorize_user, initialize_company_store


def _connect() -> sqlite3.Connection:
    initialize_company_store()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("Link must be a valid HTTP or HTTPS URL.")
    return url


def create_resource(*, company_id: str, user_id: str, title: str, url: str,
                    description: str = "", category: str = "",
                    audience: str = "all", department: str = "",
                    priority: str = "medium", expires_at: str = "") -> dict[str, Any]:
    actor = authorize_user(company_id, user_id, allowed_roles=["company_admin"])
    title = str(title or "").strip()
    if not title:
        raise ValueError("A link title is required.")
    url = _clean_url(url)
    audience = str(audience or "all").strip().lower()
    if audience not in {"all", "employees", "department", "role"}:
        raise ValueError("Audience must be all, employees, department, or role.")
    department = str(department or "").strip()
    if audience == "department" and not department:
        raise ValueError("Select a department for a department-only link.")
    priority = str(priority or "medium").strip().lower()
    if priority not in {"high", "medium", "low"}:
        raise ValueError("Priority must be high, medium, or low.")
    now = _now()
    expires = str(expires_at or "").strip() or None
    if expires:
        try:
            parsed = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Expiry must be an ISO 8601 date or timestamp.") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        expires = parsed.astimezone(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO company_resources
               (company_id,title,url,description,category,keywords,posted_by,posted_by_role,
                audience,department,priority,published_at,expires_at,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,? ,?,'active',?,?)""",
            (company_id, title, url, str(description or "").strip(), str(category or "").strip(),
             "", user_id, str(actor.get("role") or ""), audience, department, priority,
             now, expires, now, now),
        )
        resource_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO audit_logs(company_id,user_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (company_id, user_id, "shared_link_created", "company_resource", str(resource_id),
             json.dumps({"title": title}), now),
        )
    return {"status": "success", "resource_id": resource_id, "message": "Company link saved."}


def list_resources(company_id: str, user_id: str, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    actor = authorize_user(company_id, user_id)
    query = "SELECT resource_id,title,url,description,category,audience,department,priority,published_at,expires_at,status,created_at FROM company_resources WHERE company_id=?"
    params: list[Any] = [company_id]
    if not include_inactive:
        query += " AND status='active' AND (expires_at IS NULL OR expires_at='' OR expires_at>?) AND (published_at IS NULL OR published_at='' OR published_at<=?)"
        now = _now()
        params.extend([now, now])
    query += " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, title"
    with _connect() as conn:
        rows = [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    role = str(actor.get("role") or "").casefold()
    department = str(actor.get("department") or "").casefold()
    if include_inactive and role == "company_admin":
        return rows
    visible = []
    for row in rows:
        audience = str(row.get("audience") or "all").casefold()
        if audience == "all" or (audience == "employees" and role != "company_admin"):
            visible.append(row)
        elif audience == "department" and department and str(row.get("department") or "").casefold() == department:
            visible.append(row)
        elif audience == "role" and str(row.get("department") or "").casefold() == role:
            visible.append(row)
    return visible


def archive_resource(company_id: str, user_id: str, resource_id: int) -> dict[str, Any]:
    authorize_user(company_id, user_id, allowed_roles=["company_admin"])
    now = _now()
    with _connect() as conn:
        cur = conn.execute("UPDATE company_resources SET status='archived',updated_at=? WHERE company_id=? AND resource_id=? AND status='active'", (now, company_id, int(resource_id)))
        if cur.rowcount:
            conn.execute("INSERT INTO audit_logs(company_id,user_id,action,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?)", (company_id, user_id, "shared_link_archived", "company_resource", str(resource_id), now))
    return {"status": "success", "message": "Company link archived."} if cur.rowcount else {"status": "not_found", "message": "Active company link was not found."}
