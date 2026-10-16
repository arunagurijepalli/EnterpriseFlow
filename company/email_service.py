from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from company.store import DB_PATH, authorize_user, initialize_company_store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    initialize_company_store()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _resolve_recipients(company_id: str, recipient: str) -> list[dict[str, Any]]:
    text = str(recipient or "").strip()
    if not text:
        return []
    with _connect() as conn:
        rows = conn.execute("SELECT user_id,name,email,role,department FROM company_users WHERE company_id=? AND status='active'", (company_id,)).fetchall()
    query = text.casefold()
    # Resolve one exact user/email first, then a requested department mailbox
    # to active employees assigned to that department or its admin role.
    exact = [dict(row) for row in rows if query in {str(row["user_id"]).casefold(), str(row["email"] or "").casefold()}]
    if exact:
        return exact
    aliases = {
        "hr": ("hr", "human resources"),
        "hr department": ("hr", "human resources"),
        "human resources": ("hr", "human resources"),
        "it": ("it", "information technology"),
        "it support": ("it", "information technology"),
        "it support team": ("it", "information technology"),
        "finance": ("finance",),
        "procurement": ("procurement",),
        "recruitment": ("recruitment",),
    }
    targets = aliases.get(query, (query,))
    matched = [
        dict(row) for row in rows
        if str(row["department"] or "").casefold() in targets
        or str(row["role"] or "").casefold() == f"{query}_admin"
    ]
    if matched:
        return matched

    # If no dedicated HR recipient exists, use an active company admin as fallback.
    if query in {"hr", "hr department", "human resources"}:
        return [
            dict(row) for row in rows
            if str(row["role"] or "").casefold() == "company_admin"
        ]
    return []


def create_email_draft(company_id: str, sender_user_id: str, recipient: str, subject: str, body: str) -> dict[str, Any]:
    authorize_user(company_id, sender_user_id)
    subject, body = str(subject or "").strip(), str(body or "").strip()
    if not subject or not body:
        return {"status": "missing_information", "executed": False, "message": "A subject and message body are required to save an email draft."}
    recipients = _resolve_recipients(company_id, recipient)
    recipients = [item for item in recipients if item["user_id"] != sender_user_id]

    # If the only HR match is the sender, fall back to another active
    # company admin instead of failing to create the draft.
    hr_aliases = {"hr", "hr department", "human resources"}
    if not recipients and str(recipient or "").strip().casefold() in hr_aliases:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT user_id, name, email, role, department
                   FROM company_users
                   WHERE company_id = ?
                     AND status = 'active'
                     AND lower(role) = 'company_admin'
                     AND user_id != ?""",
                (company_id, sender_user_id),
            ).fetchall()
        recipients = [dict(row) for row in rows]

    if not recipients:
        return {"status": "recipient_not_found", "executed": False, "message": "No active recipient matched that name, email, or department in your company. The draft was not created."}
    now = _now()
    with _connect() as conn:
        cur = conn.execute("INSERT INTO internal_emails(company_id,sender_user_id,subject,body,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (company_id, sender_user_id, subject, body, "draft", now, now))
        email_id = int(cur.lastrowid)
        for recipient_user in recipients:
            conn.execute("INSERT INTO internal_email_recipients(company_id,email_id,recipient_user_id) VALUES(?,?,?)", (company_id, email_id, recipient_user["user_id"]))
    return {"status": "success", "executed": True, "tool": "email_draft", "email_id": email_id, "subject": subject, "recipient_names": [item["name"] for item in recipients], "status_label": "draft", "message": f"Email draft {email_id} was saved for {', '.join(item['name'] for item in recipients)}. Review it in Emails and select Send when you are ready; it has not been sent."}


def send_email(company_id: str, sender_user_id: str, email_id: int) -> dict[str, Any]:
    authorize_user(company_id, sender_user_id)
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        message = conn.execute("SELECT subject,status FROM internal_emails WHERE company_id=? AND email_id=? AND sender_user_id=?", (company_id, int(email_id), sender_user_id)).fetchone()
        if not message:
            return {"status": "not_found", "executed": False, "message": "That email draft was not found in your account."}
        if message["status"] != "draft":
            return {"status": "invalid_state", "executed": False, "message": "Only a saved draft can be sent."}
        recipients = conn.execute("SELECT recipient_user_id FROM internal_email_recipients WHERE company_id=? AND email_id=?", (company_id, int(email_id))).fetchall()
        if not recipients:
            return {"status": "invalid_state", "executed": False, "message": "This draft has no recipients and was not sent."}
        conn.execute("UPDATE internal_emails SET status='sent',sent_at=?,updated_at=? WHERE company_id=? AND email_id=? AND sender_user_id=? AND status='draft'", (now, now, company_id, int(email_id), sender_user_id))
        for row in recipients:
            conn.execute("INSERT INTO notifications(company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (company_id, row["recipient_user_id"], "", "internal_email_received", f"New internal email: {message['subject']}", "You received an internal company message.", "internal_email", str(email_id), now))
        conn.execute("INSERT INTO audit_logs(company_id,user_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)", (company_id, sender_user_id, "internal_email_sent", "internal_email", str(email_id), json.dumps({"recipient_count": len(recipients)}), now))
    return {"status": "success", "executed": True, "email_id": int(email_id), "status_label": "sent", "message": "The internal company email was sent and persisted."}


def list_emails(company_id: str, user_id: str, folder: str = "inbox", limit: int = 100) -> list[dict[str, Any]]:
    authorize_user(company_id, user_id)
    limit = max(1, min(int(limit), 500))
    folder = str(folder or "inbox").lower()
    if folder == "sent":
        sql = "SELECT e.email_id,e.sender_user_id,e.subject,e.body,e.status,e.sent_at,e.created_at,e.updated_at,NULL AS read_at FROM internal_emails e WHERE e.company_id=? AND e.sender_user_id=? AND e.status='sent' ORDER BY e.sent_at DESC LIMIT ?"
    elif folder == "drafts":
        sql = "SELECT e.email_id,e.sender_user_id,e.subject,e.body,e.status,e.sent_at,e.created_at,e.updated_at,NULL AS read_at FROM internal_emails e WHERE e.company_id=? AND e.sender_user_id=? AND e.status='draft' ORDER BY e.updated_at DESC LIMIT ?"
    else:
        sql = "SELECT e.email_id,e.sender_user_id,e.subject,e.body,e.status,e.sent_at,e.created_at,e.updated_at,r.read_at FROM internal_emails e JOIN internal_email_recipients r ON r.company_id=e.company_id AND r.email_id=e.email_id WHERE e.company_id=? AND r.recipient_user_id=? AND e.status='sent' ORDER BY e.sent_at DESC LIMIT ?"
    with _connect() as conn:
        rows = [dict(row) for row in conn.execute(sql, (company_id, user_id, limit)).fetchall()]
        for item in rows:
            recipients = conn.execute("SELECT u.user_id,u.name,u.email FROM internal_email_recipients r JOIN company_users u ON u.company_id=r.company_id AND u.user_id=r.recipient_user_id WHERE r.company_id=? AND r.email_id=?", (company_id, item["email_id"])).fetchall()
            item["recipients"] = [dict(row) for row in recipients]
            sender = conn.execute("SELECT name,email FROM company_users WHERE company_id=? AND user_id=?", (company_id, item["sender_user_id"])).fetchone()
            item["sender"] = dict(sender) if sender else {}
    return rows


def mark_email_read(company_id: str, user_id: str, email_id: int) -> bool:
    authorize_user(company_id, user_id)
    with _connect() as conn:
        cur = conn.execute("UPDATE internal_email_recipients SET read_at=COALESCE(read_at,?) WHERE company_id=? AND email_id=? AND recipient_user_id=? AND EXISTS(SELECT 1 FROM internal_emails e WHERE e.company_id=? AND e.email_id=? AND e.status='sent')", (_now(), company_id, int(email_id), user_id, company_id, int(email_id)))
    return cur.rowcount == 1


def search_emails(company_id: str, user_id: str, query: str, folder: str = "inbox") -> list[dict[str, Any]]:
    term = str(query or "").strip().casefold()
    rows = list_emails(company_id, user_id, folder)
    return [row for row in rows if not term or term in str(row.get("subject", "")).casefold() or term in str(row.get("body", "")).casefold() or term in str(row.get("sender", {}).get("name", "")).casefold()]
