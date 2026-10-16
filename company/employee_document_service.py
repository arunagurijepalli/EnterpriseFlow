"""Tenant-scoped document exchange between employees and authorized admins."""
from __future__ import annotations

from contextlib import contextmanager

import mimetypes
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from company.store import DB_PATH, authorize_user

ADMIN_ROLES = {"company_admin", "hr_admin"}
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".csv", ".json", ".docx", ".doc",
    ".xlsx", ".xls", ".pptx", ".ppt", ".png", ".jpg", ".jpeg",
    ".webp", ".zip",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def ensure_employee_document_table() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS employee_document_exchange (
                document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL,
                sender_user_id TEXT NOT NULL,
                recipient_user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                purpose TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                file_name TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                file_size INTEGER NOT NULL DEFAULT 0,
                file_data BLOB NOT NULL,
                status TEXT NOT NULL DEFAULT 'submitted',
                admin_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                read_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_employee_document_recipient "
            "ON employee_document_exchange(company_id, recipient_user_id, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_employee_document_sender "
            "ON employee_document_exchange(company_id, sender_user_id, created_at)"
        )
        conn.commit()


def _require_admin(company_id: str, actor_user_id: str) -> Dict[str, Any]:
    actor = authorize_user(company_id, actor_user_id)
    if str(actor.get("role") or "").casefold() not in ADMIN_ROLES:
        raise PermissionError("Only authorized company/HR administrators may manage all employee documents.")
    return actor


def _safe_file(file_name: str, file_data: bytes, content_type: str = ""):
    name = Path(str(file_name or "").replace("\\", "/")).name
    data = bytes(file_data or b"")
    ext = Path(name).suffix.casefold()
    if not name or not data:
        return None, None, None, "Choose a document to upload."
    if ext not in ALLOWED_EXTENSIONS:
        return None, None, None, "Unsupported document type. Upload a PDF, Office document, text file, image, or ZIP archive."
    if len(data) > MAX_DOCUMENT_BYTES:
        return None, None, None, "Documents must be 10 MB or smaller."
    guessed = mimetypes.guess_type(name)[0] or "application/octet-stream"
    supplied = str(content_type or "").strip()
    # Trust a filename-derived type over an untrusted browser MIME value.
    final_type = guessed if guessed != "application/octet-stream" else supplied or guessed
    return name, data, final_type, ""


def submit_employee_document(
    company_id: str,
    sender_user_id: str,
    recipient_user_id: str,
    *,
    title: str,
    file_name: str,
    file_data: bytes,
    purpose: str = "",
    message: str = "",
    content_type: str = "",
) -> Dict[str, Any]:
    sender = authorize_user(company_id, sender_user_id)
    recipient = authorize_user(company_id, recipient_user_id)
    sender_role = str(sender.get("role") or "").casefold()
    recipient_role = str(recipient.get("role") or "").casefold()
    if sender_user_id == recipient_user_id:
        return {"status": "invalid", "message": "Choose a different recipient."}
    if sender_role not in ADMIN_ROLES and recipient_role not in ADMIN_ROLES:
        return {"status": "forbidden", "message": "Employees may submit company documents only to an authorized HR/company administrator."}
    if sender_role in ADMIN_ROLES and recipient_role in ADMIN_ROLES:
        return {"status": "invalid", "message": "Choose an employee as the recipient for administrator-to-employee documents."}
    name, data, detected_type, error = _safe_file(file_name, file_data, content_type)
    if error:
        return {"status": "invalid", "message": error}
    title = str(title or "").strip() or name
    if len(title) > 180:
        return {"status": "invalid", "message": "Document title must be 180 characters or fewer."}
    ensure_employee_document_table()
    timestamp = _now()
    initial_status = "submitted" if sender_role not in ADMIN_ROLES else "sent"
    with _connect() as conn:
        cursor = conn.execute(
            """INSERT INTO employee_document_exchange
               (company_id,sender_user_id,recipient_user_id,title,purpose,message,
                file_name,content_type,file_size,file_data,status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (company_id, sender_user_id, recipient_user_id, title, str(purpose or "").strip(),
             str(message or "").strip(), name, detected_type, len(data), sqlite3.Binary(data),
             initial_status, timestamp, timestamp),
        )
        conn.commit()
        document_id = int(cursor.lastrowid)
    return {"status": "success", "document_id": document_id, "message": f"Document #{document_id} sent successfully."}


def list_user_documents(company_id: str, user_id: str) -> List[Dict[str, Any]]:
    authorize_user(company_id, user_id)
    ensure_employee_document_table()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT d.document_id,d.company_id,d.sender_user_id,d.recipient_user_id,
                      d.title,d.purpose,d.message,d.file_name,d.content_type,d.file_size,
                      d.status,d.admin_note,d.created_at,d.updated_at,d.read_at,
                      s.name AS sender_name,s.email AS sender_email,
                      r.name AS recipient_name,r.email AS recipient_email
               FROM employee_document_exchange d
               JOIN company_users s ON s.company_id=d.company_id AND s.user_id=d.sender_user_id
               JOIN company_users r ON r.company_id=d.company_id AND r.user_id=d.recipient_user_id
               WHERE d.company_id=? AND (d.sender_user_id=? OR d.recipient_user_id=?)
               ORDER BY d.created_at DESC""",
            (company_id, user_id, user_id),
        ).fetchall()
    return [dict(row) for row in rows]


def list_company_documents_for_admin(company_id: str, admin_user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    _require_admin(company_id, admin_user_id)
    ensure_employee_document_table()
    query = """SELECT d.document_id,d.company_id,d.sender_user_id,d.recipient_user_id,
                      d.title,d.purpose,d.message,d.file_name,d.content_type,d.file_size,
                      d.status,d.admin_note,d.created_at,d.updated_at,d.read_at,
                      s.name AS sender_name,s.email AS sender_email,s.role AS sender_role,
                      r.name AS recipient_name,r.email AS recipient_email,r.role AS recipient_role
               FROM employee_document_exchange d
               JOIN company_users s ON s.company_id=d.company_id AND s.user_id=d.sender_user_id
               JOIN company_users r ON r.company_id=d.company_id AND r.user_id=d.recipient_user_id
               WHERE d.company_id=?"""
    params: List[Any] = [company_id]
    if status and status.casefold() != "all":
        query += " AND d.status=?"
        params.append(status)
    query += " ORDER BY d.created_at DESC"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_employee_document(company_id: str, actor_user_id: str, document_id: int) -> Optional[Dict[str, Any]]:
    actor = authorize_user(company_id, actor_user_id)
    ensure_employee_document_table()
    role = str(actor.get("role") or "").casefold()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM employee_document_exchange WHERE company_id=? AND document_id=?",
            (company_id, int(document_id)),
        ).fetchone()
    if not row:
        return None
    record = dict(row)
    if actor_user_id not in {record["sender_user_id"], record["recipient_user_id"]} and role not in ADMIN_ROLES:
        raise PermissionError("You do not have access to this document.")
    return record


def mark_employee_document_read(company_id: str, actor_user_id: str, document_id: int) -> Dict[str, Any]:
    authorize_user(company_id, actor_user_id)
    ensure_employee_document_table()
    timestamp = _now()
    with _connect() as conn:
        cursor = conn.execute(
            """UPDATE employee_document_exchange SET status='read', read_at=?, updated_at=?
               WHERE company_id=? AND document_id=? AND recipient_user_id=?
                 AND status IN ('sent','submitted','read')""",
            (timestamp, timestamp, company_id, int(document_id), actor_user_id),
        )
        conn.commit()
    if not cursor.rowcount:
        return {"status": "no_change", "message": "Document was not available to mark as read."}
    return {"status": "success", "message": "Document marked as read."}


def update_employee_document_status(
    company_id: str,
    admin_user_id: str,
    document_id: int,
    *,
    status: str,
    admin_note: str = "",
) -> Dict[str, Any]:
    _require_admin(company_id, admin_user_id)
    allowed = {"submitted", "sent", "read", "reviewed", "needs_information", "archived"}
    status = str(status or "").casefold().strip()
    if status not in allowed:
        return {"status": "invalid", "message": "Unsupported document status."}
    ensure_employee_document_table()
    with _connect() as conn:
        cursor = conn.execute(
            """UPDATE employee_document_exchange SET status=?, admin_note=?, updated_at=?
               WHERE company_id=? AND document_id=?""",
            (status, str(admin_note or "").strip(), _now(), company_id, int(document_id)),
        )
        conn.commit()
    if not cursor.rowcount:
        return {"status": "not_found", "message": "Document was not found."}
    return {"status": "success", "message": f"Document #{document_id} updated to {status.replace('_',' ')}."}
