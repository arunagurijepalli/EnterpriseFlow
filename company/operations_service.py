"""Admin operations for tenant-owned IT support requests."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from company.store import DB_PATH, authorize_user, initialize_company_store

IT_OPERATORS = {"company_admin", "it_admin"}
IT_STATUSES = {"submitted", "open", "in_progress", "needs_information", "resolved", "closed"}
IT_PRIORITIES = {"low", "normal", "medium", "high", "urgent"}
PROCUREMENT_OPERATORS = {"company_admin", "procurement_admin"}


def list_procurement_queue(company_id: str, user_id: str, *, status: str = "All") -> list[dict[str, Any]]:
    authorize_user(company_id, user_id, allowed_roles=list(PROCUREMENT_OPERATORS))
    initialize_company_store()
    query = """SELECT r.request_id,r.user_id,u.name AS employee,u.department,r.title,
                     r.description,r.amount,r.currency,r.status,r.workflow_id,
                     r.decision_reason,r.details_json,r.created_at,r.updated_at
              FROM department_requests r LEFT JOIN company_users u
                ON u.company_id=r.company_id AND u.user_id=r.user_id
              WHERE r.company_id=? AND r.service_area='Procurement' AND r.request_type='purchase_request'"""
    params: list[Any] = [company_id]
    if status and status != "All":
        query += " AND lower(r.status)=lower(?)"
        params.append(status)
    query += " ORDER BY r.updated_at DESC"
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    for item in rows:
        try:
            item["details"] = json.loads(item.pop("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["details"] = {}
    return rows


def assign_purchase_vendor(company_id: str, user_id: str, request_id: str, vendor_name: str) -> dict[str, Any]:
    authorize_user(company_id, user_id, allowed_roles=list(PROCUREMENT_OPERATORS))
    vendor_name = str(vendor_name or "").strip()
    if not vendor_name:
        raise ValueError("Select an active company vendor.")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        vendor = conn.execute("SELECT name,rating,delivery_days FROM company_vendors WHERE company_id=? AND name=? AND status='active'", (company_id, vendor_name)).fetchone()
        if vendor is None:
            return {"status": "not_found", "message": "The selected vendor is not active in this company."}
        request = conn.execute("SELECT user_id,details_json,status,workflow_id FROM department_requests WHERE company_id=? AND request_id=? AND service_area='Procurement' AND request_type='purchase_request'", (company_id, request_id)).fetchone()
        if request is None:
            return {"status": "not_found", "message": "The purchase request was not found in this company."}
        if request["status"] not in {"approved", "submitted"}:
            return {"status": "invalid_state", "message": "Assign a vendor after the request is approved or eligible for processing."}
        details = json.loads(request["details_json"] or "{}")
        details["assigned_vendor"] = dict(vendor)
        conn.execute("UPDATE department_requests SET details_json=?,updated_at=? WHERE company_id=? AND request_id=?", (json.dumps(details, ensure_ascii=False), now, company_id, request_id))
        purchase_order_id = str(details.get("purchase_order_id") or "")
        if purchase_order_id:
            order = conn.execute("SELECT details_json FROM department_requests WHERE company_id=? AND request_id=? AND request_type='purchase_order'", (company_id, purchase_order_id)).fetchone()
            if order:
                order_details = json.loads(order["details_json"] or "{}")
                order_details["assigned_vendor"] = dict(vendor)
                conn.execute("UPDATE department_requests SET details_json=?,updated_at=? WHERE company_id=? AND request_id=?", (json.dumps(order_details, ensure_ascii=False), now, company_id, purchase_order_id))
        conn.execute("INSERT INTO audit_logs(company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (company_id, user_id, request["workflow_id"], "procurement_vendor_assigned", "department_request", request_id, json.dumps({"vendor": vendor_name}), now))
        conn.execute("INSERT INTO notifications(company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (company_id, request["user_id"], request["workflow_id"], "procurement_vendor_assigned", "Vendor assigned", f"{vendor_name} was assigned to purchase request {request_id}.", "department_request", request_id, now))
    return {"status": "success", "message": f"{vendor_name} was assigned to {request_id}."}


def list_it_tickets(company_id: str, user_id: str, *, status: str = "All",
                    search: str = "", limit: int = 300) -> list[dict[str, Any]]:
    authorize_user(company_id, user_id, allowed_roles=list(IT_OPERATORS))
    initialize_company_store()
    query = """SELECT r.request_id,r.user_id,u.name AS employee,u.department,
                     r.request_type,r.title,r.description,r.status,r.workflow_id,
                     r.decision_reason,r.details_json,r.created_at,r.updated_at
              FROM department_requests r LEFT JOIN company_users u
                ON u.company_id=r.company_id AND u.user_id=r.user_id
              WHERE r.company_id=? AND r.service_area='IT'"""
    params: list[Any] = [company_id]
    if status and status != "All":
        query += " AND lower(r.status)=lower(?)"
        params.append(status)
    if search.strip():
        query += " AND (r.request_id LIKE ? OR r.title LIKE ? OR r.description LIKE ? OR u.name LIKE ?)"
        match = f"%{search.strip()}%"
        params.extend([match, match, match, match])
    query += " ORDER BY r.updated_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 1000)))
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    for item in rows:
        try:
            item["details"] = json.loads(item.pop("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["details"] = {}
    return rows


def update_it_ticket(company_id: str, user_id: str, request_id: str, *,
                     status: str = "", priority: str = "", assignee_user_id: str = "",
                     comment: str = "") -> dict[str, Any]:
    authorize_user(company_id, user_id, allowed_roles=list(IT_OPERATORS))
    request_id = str(request_id or "").strip()
    status = str(status or "").strip().lower()
    priority = str(priority or "").strip().lower()
    assignee_user_id = str(assignee_user_id or "").strip()
    comment = str(comment or "").strip()
    if status and status not in IT_STATUSES:
        raise ValueError("Select a supported ticket status.")
    if priority and priority not in IT_PRIORITIES:
        raise ValueError("Select a supported ticket priority.")
    if not any((status, priority, assignee_user_id, comment)):
        raise ValueError("Change a ticket field or add a comment before saving.")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        ticket = conn.execute("SELECT * FROM department_requests WHERE company_id=? AND request_id=? AND service_area='IT'", (company_id, request_id)).fetchone()
        if ticket is None:
            return {"status": "not_found", "message": "The IT ticket was not found in this company."}
        current_status = str(ticket["status"] or "").casefold()
        if current_status in {"pending_approval", "needs_clarification"}:
            return {"status": "approval_required", "message": "This IT request is waiting for approval or clarification. Use the Pending Approvals controls before changing its processing status."}
        try:
            details = json.loads(ticket["details_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            details = {}
        if assignee_user_id:
            assignee = conn.execute("SELECT user_id,role,status FROM company_users WHERE company_id=? AND user_id=?", (company_id, assignee_user_id)).fetchone()
            if assignee is None or assignee["status"] != "active" or assignee["role"] not in IT_OPERATORS:
                raise ValueError("Assignee must be an active IT administrator in this company.")
            details["assigned_to"] = assignee_user_id
        if priority:
            details["priority"] = priority
        comments = details.get("comments") if isinstance(details.get("comments"), list) else []
        if comment:
            comments.append({"user_id": user_id, "comment": comment, "created_at": now})
            details["comments"] = comments[-100:]
        next_status = status or str(ticket["status"] or "open")
        conn.execute("UPDATE department_requests SET status=?,details_json=?,updated_at=? WHERE company_id=? AND request_id=?", (next_status, json.dumps(details, ensure_ascii=False), now, company_id, request_id))
        conn.execute("INSERT INTO audit_logs(company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (company_id, user_id, ticket["workflow_id"], "it_ticket_updated", "department_request", request_id, json.dumps({"status": next_status, "priority": details.get("priority"), "assigned_to": details.get("assigned_to"), "comment_added": bool(comment)}), now))
        conn.execute("INSERT INTO notifications(company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (company_id, ticket["user_id"], ticket["workflow_id"], "it_ticket_updated", "IT ticket updated", f"{request_id} is now {next_status.replace('_', ' ')}.", "department_request", request_id, now))
    return {"status": "success", "request_id": request_id, "ticket_status": next_status, "message": f"IT ticket {request_id} was updated."}
