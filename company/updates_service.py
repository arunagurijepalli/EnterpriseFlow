from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from company.store import DB_PATH, authorize_user, initialize_company_store

_DEPARTMENT_ALIASES = {
    "hr": {"hr", "human resources"},
    "it": {"it", "information technology", "it support"},
    "finance": {"finance", "accounting"},
    "procurement": {"procurement", "purchasing"},
    "recruitment": {"recruitment", "talent acquisition"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    initialize_company_store()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    # Migrate databases created before targeting, scheduling, and read tracking.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(company_updates)")}
    if "department" not in columns:
        conn.execute("ALTER TABLE company_updates ADD COLUMN department TEXT NOT NULL DEFAULT ''")
    conn.commit()
    return conn


def ensure_updates_table() -> None:
    with _connect():
        pass


def _parse_date(value: Optional[str], field: str) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO date or date/time.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _validate_audience(audience: str, department: str) -> tuple[str, str]:
    audience = str(audience or "company").strip().lower()
    department = str(department or "").strip()
    allowed = {"company", "all", "employees", "hr", "it", "finance", "procurement", "recruitment", "department"}
    if audience not in allowed:
        raise ValueError("Choose a supported company or department audience.")
    if audience == "department" and not department:
        raise ValueError("A department is required for a department-only announcement.")
    return audience, department


def _notify_audience(conn: sqlite3.Connection, company_id: str, update_id: int, audience: str, department: str, title: str, created_at: str) -> None:
    query = "SELECT user_id,role,department FROM company_users WHERE company_id=? AND status='active'"
    users = conn.execute(query, (company_id,)).fetchall()
    for user in users:
        role = str(user["role"] or "").lower()
        dept = str(user["department"] or "").lower()
        department_target = department.lower() or audience
        department_targets = _DEPARTMENT_ALIASES.get(department_target, {department_target})
        if audience in {"company", "all", "employees"} or audience == role or ((department or audience in _DEPARTMENT_ALIASES) and dept in department_targets):
            conn.execute(
                "INSERT INTO notifications (company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (company_id, user["user_id"], "", "company_announcement", title, "A company announcement is available.", "company_update", str(update_id), created_at),
            )


def create_update(*, company_id: str, posted_by: str, title: str, description: str = "", link_url: str = "", category: str = "", priority: str = "normal", audience: str = "company", expires_at: Optional[str] = None, published_at: Optional[str] = None, department: str = "", status: str = "active") -> Dict[str, Any]:
    actor = authorize_user(company_id, posted_by, allowed_roles=["company_admin"])
    del actor
    title = str(title or "").strip()
    if not title:
        raise ValueError("Title is required.")
    priority = str(priority or "normal").lower()
    if priority not in {"high", "normal", "low"}:
        raise ValueError("Priority must be high, normal, or low.")
    audience, department = _validate_audience(audience, department)
    status = str(status or "active").lower()
    if status not in {"draft", "scheduled", "active"}:
        raise ValueError("New announcements can be draft, scheduled, or active.")
    now = _now()
    published = _parse_date(published_at, "Effective date") or now
    expires = _parse_date(expires_at, "Expiry date")
    if expires and expires <= published:
        raise ValueError("Expiry date must be later than the effective date.")
    if status == "active" and published > now:
        status = "scheduled"
    if status == "scheduled" and not published_at:
        raise ValueError("A scheduled announcement requires an effective date/time.")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO company_updates(company_id,title,description,link_url,posted_by,category,priority,audience,department,published_at,expires_at,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (company_id, title, str(description or "").strip(), str(link_url or "").strip(), posted_by, str(category or "").strip(), priority, audience, department, published, expires, status, now, now),
        )
        update_id = int(cur.lastrowid)
        conn.execute("INSERT INTO audit_logs(company_id,user_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)", (company_id, posted_by, "company_update_created", "company_update", str(update_id), "{}", now))
        if status == "active":
            _notify_audience(conn, company_id, update_id, audience, department, title, now)
    return {"status": "success", "update_id": update_id, "message": f"Announcement {update_id} was saved as {status}.", "publication_status": status}


def update_company_update(*, company_id: str, user_id: str, update_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    authorize_user(company_id, user_id, allowed_roles=["company_admin"])
    allowed = {"title", "description", "link_url", "category", "priority", "audience", "department", "published_at", "expires_at", "status"}
    changes = {key: value for key, value in fields.items() if key in allowed}
    if not changes:
        return {"status": "invalid", "message": "No editable announcement fields were provided."}
    if "priority" in changes and str(changes["priority"]).lower() not in {"high", "normal", "low"}:
        return {"status": "invalid", "message": "Priority must be high, normal, or low."}
    if "status" in changes and str(changes["status"]).lower() not in {"draft", "scheduled", "active"}:
        return {"status": "invalid", "message": "Publication must be draft, scheduled, or active."}
    if "audience" in changes:
        try:
            changes["audience"], changes["department"] = _validate_audience(str(changes["audience"]), str(changes.get("department", "")))
        except ValueError as exc:
            return {"status": "invalid", "message": str(exc)}
    for key in ("published_at", "expires_at"):
        if key in changes:
            changes[key] = _parse_date(changes[key], key.replace("_", " ").title())
    if "title" in changes:
        changes["title"] = str(changes["title"] or "").strip()
        if not changes["title"]:
            return {"status": "invalid", "message": "Title cannot be empty."}
    changes["updated_at"] = _now()
    with _connect() as conn:
        current = conn.execute("SELECT published_at,expires_at,status FROM company_updates WHERE company_id=? AND update_id=? AND status!='archived'", (company_id, int(update_id))).fetchone()
        if current is None:
            return {"status": "not_found", "message": "Announcement was not found or is archived."}
        effective = changes.get("published_at", current["published_at"])
        expiry = changes.get("expires_at", current["expires_at"])
        if expiry and effective and expiry <= effective:
            return {"status": "invalid", "message": "Expiry date must be later than the effective date."}
        if str(changes.get("status", current["status"])).lower() == "scheduled" and not effective:
            return {"status": "invalid", "message": "A scheduled announcement requires an effective date/time."}
        if str(changes.get("status", current["status"])).lower() == "active" and effective and effective > _now():
            changes["status"] = "scheduled"
        cur = conn.execute("UPDATE company_updates SET " + ",".join(f"{key}=?" for key in changes) + " WHERE company_id=? AND update_id=? AND status!='archived'", (*changes.values(), company_id, int(update_id)))
        if cur.rowcount != 1:
            return {"status": "not_found", "message": "Announcement was not found or is archived."}
        conn.execute("INSERT INTO audit_logs(company_id,user_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)", (company_id, user_id, "company_update_edited", "company_update", str(update_id), "{}", changes["updated_at"]))
    return {"status": "success", "update_id": int(update_id), "message": "Announcement updated."}


def archive_update(*, company_id: str, user_id: str, update_id: int) -> Dict[str, Any]:
    authorize_user(company_id, user_id, allowed_roles=["company_admin"])
    with _connect() as conn:
        cur = conn.execute("UPDATE company_updates SET status='archived',updated_at=? WHERE company_id=? AND update_id=? AND status!='archived'", (_now(), company_id, int(update_id)))
        if cur.rowcount:
            conn.execute("INSERT INTO audit_logs(company_id,user_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)", (company_id, user_id, "company_update_archived", "company_update", str(update_id), "{}", _now()))
    return {"status": "success", "message": "Announcement archived."} if cur.rowcount else {"status": "not_found", "message": "Announcement was not found."}


def list_updates(company_id: str, *, user_id: Optional[str] = None, include_expired: bool = False, include_inactive: bool = False) -> List[Dict[str, Any]]:
    if user_id:
        user = authorize_user(company_id, user_id)
        if include_inactive and user.get("role") != "company_admin":
            raise PermissionError("Only company admins can view unpublished announcements.")
    else:
        raise PermissionError("An authenticated user is required to view company announcements.")
    now = _now()
    # Activate due scheduled updates exactly once and create their inbox notices.
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        due = conn.execute("SELECT update_id,audience,department,title FROM company_updates WHERE company_id=? AND status='scheduled' AND published_at<=? AND (expires_at IS NULL OR expires_at>?)", (company_id, now, now)).fetchall()
        for item in due:
            conn.execute("UPDATE company_updates SET status='active',updated_at=? WHERE company_id=? AND update_id=? AND status='scheduled'", (now, company_id, item["update_id"]))
            _notify_audience(conn, company_id, int(item["update_id"]), str(item["audience"]), str(item["department"]), str(item["title"]), now)
    query = "SELECT u.*,r.read_at FROM company_updates u LEFT JOIN company_update_reads r ON r.company_id=u.company_id AND r.update_id=u.update_id AND r.user_id=? WHERE u.company_id=?"
    params: list[Any] = [user_id, company_id]
    if include_inactive:
        query += " AND u.status IN ('active','scheduled','draft','archived')"
    else:
        query += " AND u.status='active' AND (u.published_at IS NULL OR u.published_at<=?)"
        params.append(now)
    if not include_expired:
        query += " AND (u.expires_at IS NULL OR u.expires_at>?)"
        params.append(now)
    query += " ORDER BY CASE u.priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,u.published_at DESC"
    with _connect() as conn:
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    user = authorize_user(company_id, user_id)
    result = []
    for row in rows:
        audience = str(row.get("audience") or "company").lower()
        audience_department = str(row.get("department") or audience).lower()
        target_departments = _DEPARTMENT_ALIASES.get(audience_department, {audience_department})
        if audience in {"company", "all", "employees"} or audience == str(user.get("role") or "").lower() or ((audience == "department" or audience in _DEPARTMENT_ALIASES) and str(user.get("department") or "").lower() in target_departments):
            result.append(row)
    return result


def mark_update_read(company_id: str, user_id: str, update_id: int) -> bool:
    authorize_user(company_id, user_id)
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM company_updates WHERE company_id=? AND update_id=? AND status='active'", (company_id, int(update_id))).fetchone()
        if not exists:
            return False
        conn.execute("INSERT OR IGNORE INTO company_update_reads(company_id,update_id,user_id,read_at) VALUES(?,?,?,?)", (company_id, int(update_id), user_id, _now()))
    return True


def search_updates(company_id: str, query: str, limit: int = 8, *, user_id: str) -> List[Dict[str, Any]]:
    query = str(query or "").strip().lower()
    if not query:
        return []
    terms = [term for term in query.split() if len(term) >= 2]
    results = []
    for row in list_updates(company_id, user_id=user_id):
        searchable = " ".join(str(row.get(key) or "") for key in ("title", "description", "category", "department")).lower()
        score = sum(searchable.count(term) for term in terms)
        if score:
            row["score"] = score
            results.append(row)
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:max(1, min(int(limit), 50))]
