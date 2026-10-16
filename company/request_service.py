from __future__ import annotations
from contextlib import contextmanager

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from company.employee_service import get_employee_id
from company.store import DB_PATH, authorize_user, initialize_company_store


PREFIXES = {"IT": "IT", "Finance": "FIN", "Procurement": "PR", "Recruitment": "REC", "HR": "HR"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect():
    """Yield a configured connection and always close it."""
    initialize_company_store()
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


def create_department_request(
    *, company_id: str, user_id: str, workflow_id: str,
    service_area: str, request_type: str, title: str,
    description: str = "", amount: float | None = None,
    currency: str = "", details: Dict[str, Any] | None = None,
    requires_approval: bool = False,
) -> Dict[str, Any]:
    authorize_user(company_id, user_id)
    if not get_employee_id(company_id, user_id):
        return {"status": "not_found", "executed": False, "message": "Your employee profile was not found."}
    raw_service_area = str(service_area or "").strip()
    service_area = next(
        (area for area in PREFIXES if area.casefold() == raw_service_area.casefold()),
        raw_service_area,
    )
    if service_area not in PREFIXES:
        return {"status": "invalid", "executed": False, "message": "The requested department is not supported."}
    title = str(title or "").strip()
    if not title:
        return {"status": "missing_information", "executed": False, "message": "A short description is required before submitting this request."}
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        return {"status": "invalid", "executed": False, "message": "The request amount is invalid."}
    if amount is not None and amount <= 0:
        return {"status": "invalid", "executed": False, "message": "The request amount must be greater than zero."}
    request_id = f"{PREFIXES[service_area]}-{uuid.uuid4().hex[:8].upper()}"
    status = "pending_approval" if requires_approval else "submitted"
    now = _now()
    details_json = json.dumps(details or {}, ensure_ascii=False, default=str)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO department_requests (request_id,company_id,user_id,service_area,request_type,title,description,amount,currency,status,workflow_id,details_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (request_id, company_id, user_id, service_area, request_type, title, str(description or ""), amount, currency, status, workflow_id, details_json, now, now),
        )
        conn.execute(
            "INSERT INTO notifications (company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (company_id, user_id, workflow_id, f"{service_area.lower()}_request_submitted", f"{service_area} request submitted", f"{request_id} was created with status {status.replace('_', ' ')}.", "department_request", request_id, now),
        )
        conn.execute(
            "INSERT INTO audit_logs (company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (company_id, user_id, workflow_id, "department_request_created", "department_request", request_id, json.dumps({"service_area": service_area, "request_type": request_type, "status": status}), now),
        )
    return {"status": "success", "executed": True, "tool": "", "request_id": request_id, "service_area": service_area, "request_type": request_type, "title": title, "amount": amount, "currency": currency, "status_label": status, "approval_required": requires_approval, "workflow_id": workflow_id, "message": f"{service_area} request {request_id} was created with status {status.replace('_', ' ')}."}


def list_my_department_requests(company_id: str, user_id: str, service_area: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    authorize_user(company_id, user_id)
    query = "SELECT request_id,service_area,request_type,title,description,amount,currency,status,workflow_id,approval_id,approver_user_id,decision_reason,created_at,updated_at,details_json FROM department_requests WHERE company_id=? AND user_id=?"
    params: list[Any] = [company_id, user_id]
    if service_area:
        query += " AND lower(service_area)=lower(?)"
        params.append(service_area)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with _connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item.pop("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["details"] = {}
        result.append(item)
    return result


def _looks_like_nonbusiness_workflow_request(text: str, request_category: str = "") -> bool:
    """Exclude legacy false-positive workflow-only items without deleting history."""
    import re
    raw = str(text or "").strip()
    if str(request_category or "").casefold() in {"information_request", "general_information", "read_only"}:
        return True
    lowered = raw.casefold()
    if re.match(r"^(?:\.{1,2}[^\s]*[\\/]scripts[\\/]|[a-z]:[\\/]|(?:python(?:\.exe)?|pip(?:3)?|streamlit(?:\.exe)?|git|npm|node|powershell|cmd)(?:\s|$))", lowered):
        return True
    if re.search(r"\\scripts\\streamlit(?:\.exe)?\s+run\s+.*\bapp\.py\b", lowered):
        return True
    # Legacy versions sometimes persisted read-only lookups as generic HR/IT
    # actions. Hide those false positives in the pending list without deleting
    # the underlying historical rows. Do not hide text that asks for a write.
    starts_as_lookup = bool(re.match(
        r"^\s*(?:show|list|display|view|retrieve|get|check|find|what|which|where|when|why|how|tell me)\b",
        lowered,
    )) or bool(re.match(
        r"^\s*my\s+(?:latest\s+|previous\s+|past\s+)?"
        r"(?:performance(?:\s+review)?|leave\s+(?:requests?|history|balance)|"
        r"attendance(?:\s+(?:record|history|status))?|tickets?|ticket\s+status|"
        r"profile|payslip|pay\s+slip)\b", lowered,
    ))
    is_write_action = bool(re.search(
        r"\b(?:create|raise|open|submit|apply|file|report|draft|send|reimburse|"
        r"correct|update|change|schedule|enroll|enrol|book|cancel|transfer|"
        r"reset|install|grant|remove|disable|revoke)\b", lowered,
    )) or bool(re.match(r"^\s*(?:please\s+)?request\b", lowered))
    known_lookup_target = bool(re.search(
        r"\b(?:performance(?:\s+review|\s+record)?|leave\s+(?:requests?|history|balance|records?)|"
        r"attendance|ticket\s+status|my\s+(?:it\s+)?tickets?|request\s+history|"
        r"payslip|pay\s+slip|employee\s+profile|company\s+policy|approval\s+status)\b", lowered,
    ))
    if starts_as_lookup and known_lookup_target and not is_write_action:
        return True
    # A historical read-only/search tool never represents an approval item.
    return False


def list_my_pending_requests(company_id: str, user_id: str, limit: int = 250) -> List[Dict[str, Any]]:
    """Return the employee's own requests awaiting approval/clarification.

    This is intentionally distinct from list_pending_approvals(), which is an
    approver queue. All queries are scoped to both tenant and requesting user.
    """
    authorize_user(company_id, user_id)
    limit = max(1, min(int(limit), 500))
    items: List[Dict[str, Any]] = []
    allowed = {"pending_approval", "needs_clarification", "pending", "awaiting_approval"}
    with _connect() as conn:
        dept_rows = conn.execute(
            "SELECT request_id,service_area,request_type,title,description,status,workflow_id,approval_id,decision_reason,created_at,updated_at,details_json "
            "FROM department_requests WHERE company_id=? AND user_id=? AND lower(status) IN ('pending_approval','needs_clarification','pending','awaiting_approval') "
            "ORDER BY created_at DESC LIMIT ?",
            (company_id, user_id, limit),
        ).fetchall()
        for row in dept_rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item.pop("details_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                item["details"] = {}
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            # Descriptions contain the original employee prompt; avoid joining
            # in a generic title such as "General HR request", which would
            # make a read-only sentence look like a write action.
            lookup_text = str(item.get("description") or "").strip()
            if not lookup_text:
                lookup_text = str(item.get("title") or item.get("request_type") or "").strip()
            if _looks_like_nonbusiness_workflow_request(lookup_text, str(details.get("request_category") or "")):
                continue
            item["source"] = "department_request"
            item["display_title"] = item.get("title") or item.get("request_type") or "Company request"
            items.append(item)

        leave_rows = conn.execute(
            "SELECT leave_request_id AS request_id, 'HR' AS service_area, 'leave_management' AS request_type, "
            "'Leave request' AS title, reason AS description, status, workflow_id, approval_id, decision_reason, created_at, updated_at, "
            "start_date,end_date,requested_days,leave_type "
            "FROM leave_requests WHERE company_id=? AND user_id=? AND lower(status) IN ('pending_approval','needs_clarification','pending','awaiting_approval') "
            "ORDER BY created_at DESC LIMIT ?",
            (company_id, user_id, limit),
        ).fetchall()
        for row in leave_rows:
            item = dict(row)
            item["source"] = "leave_request"
            item["display_title"] = f"{item.get('leave_type') or 'Leave'} · {item.get('start_date') or ''} to {item.get('end_date') or ''}".strip()
            item["details"] = {"requested_days": item.get("requested_days"), "start_date": item.get("start_date"), "end_date": item.get("end_date")}
            items.append(item)

        # Include saved workflow-only records that have no department_requests
        # or leave_requests row yet. This is important for legacy approvals and
        # requests routed through a generic workflow tool; otherwise employees
        # could have many pending workflows but see an empty pending list.
        already_covered_workflows = {
            str(item.get("workflow_id") or "").strip()
            for item in items
            if str(item.get("workflow_id") or "").strip()
        }
        workflow_rows = conn.execute(
            "SELECT workflow_id,request_text,request_category,intent,status,decision,"
            "assigned_agents_json,selected_tools_json,context_json,created_at,updated_at "
            "FROM workflow_requests WHERE company_id=? AND user_id=? "
            "AND lower(status) IN ('pending_approval','awaiting_approval','pending',"
            "'awaiting_clarification','needs_clarification','awaiting_confirmation') "
            "ORDER BY updated_at DESC LIMIT ?",
            (company_id, user_id, limit),
        ).fetchall()
        for row in workflow_rows:
            item = dict(row)
            workflow_id = str(item.get("workflow_id") or "").strip()
            if not workflow_id or workflow_id in already_covered_workflows:
                continue
            try:
                details = json.loads(item.pop("context_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                details = {}
            if not isinstance(details, dict):
                details = {}
            try:
                item["decision"] = json.loads(item.get("decision") or "{}")
            except (TypeError, json.JSONDecodeError):
                item["decision"] = {}
            try:
                agents = json.loads(item.pop("assigned_agents_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                agents = []
            try:
                tools = json.loads(item.pop("selected_tools_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                tools = []
            if not isinstance(agents, list):
                agents = []
            if not isinstance(tools, list):
                tools = []
            if _looks_like_nonbusiness_workflow_request(
                str(item.get("request_text") or ""),
                str(item.get("request_category") or ""),
            ):
                continue
            request_id = ""
            tool_results = details.get("tool_results") if isinstance(details.get("tool_results"), list) else []
            for tool_result in tool_results:
                if isinstance(tool_result, dict):
                    request_id = str(tool_result.get("request_id") or "").strip()
                    if request_id:
                        break
            departments = details.get("departments") if isinstance(details.get("departments"), list) else []
            service_area = str(departments[0] if departments else "").strip()
            if not service_area:
                tool_lower = str(tools[0] if tools else "").casefold()
                intent_lower = str(item.get("intent") or "").casefold()
                if tool_lower in {"create_ticket", "device_service", "password_access_service", "software_service", "knowledge_base_service"} or intent_lower.startswith("it_"):
                    service_area = "IT"
                elif tool_lower.startswith("hr_") or tool_lower in {"leave_management", "benefits_service", "hr_training_service"} or intent_lower.startswith(("hr_", "leave", "employee_", "professional_", "payroll_")):
                    service_area = "HR"
                else:
                    service_area = "Company"
            item["details"] = details
            item["request_id"] = request_id or workflow_id
            item["service_area"] = service_area
            item["request_type"] = item.get("intent") or item.get("request_category") or "workflow_request"
            item["title"] = item.get("request_text") or "Company workflow request"
            item["display_title"] = str(item["title"]).strip()[:160]
            item["description"] = str(item.get("request_text") or "")
            item["status"] = str(item.get("status") or "pending")
            item["workflow_id"] = workflow_id
            item["created_at"] = item.get("created_at") or ""
            item["updated_at"] = item.get("updated_at") or item["created_at"]
            item["assigned_agents"] = agents
            item["selected_tools"] = tools
            item["source"] = "workflow_request"
            items.append(item)

        # Include approvals that do not have an associated service row (legacy
        # or custom workflows) without duplicating the rows above.
        covered_workflows = {
            str(item.get("workflow_id") or "").strip()
            for item in items
            if str(item.get("workflow_id") or "").strip()
        }
        approval_rows = conn.execute(
            "SELECT approval_id,workflow_id,approval_type,status,reason,requested_at,metadata_json "
            "FROM approvals WHERE company_id=? AND requested_by=? AND status IN ('pending','needs_clarification') "
            "ORDER BY requested_at DESC LIMIT ?",
            (company_id, user_id, limit),
        ).fetchall()
        for row in approval_rows:
            item = dict(row)
            workflow_id = str(item.get("workflow_id") or "")
            if workflow_id in covered_workflows:
                continue
            try:
                metadata = json.loads(item.pop("metadata_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            item["details"] = metadata
            item["request_id"] = metadata.get("request_id") or f"Approval #{item.get('approval_id')}"
            item["service_area"] = metadata.get("service_area") or metadata.get("department") or "Company"
            item["request_type"] = item.get("approval_type") or "approval"
            item["display_title"] = metadata.get("title") or item.get("approval_type", "Pending approval").replace("_", " ").title()
            item["description"] = item.get("reason") or "Waiting for company review."
            item["status"] = item.get("status") or "pending"
            item["created_at"] = item.get("requested_at") or ""
            item["source"] = "approval_record"
            items.append(item)

    # De-duplicate by request identifier, prefer most detailed service rows.
    deduped: Dict[str, Dict[str, Any]] = {}
    for item in items:
        key = str(item.get("request_id") or item.get("workflow_id") or id(item))
        deduped[key] = item
    result = list(deduped.values())
    result.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return result[:limit]


def get_my_department_request(company_id: str, user_id: str, request_id: str) -> Dict[str, Any]:
    for item in list_my_department_requests(company_id, user_id):
        if str(item.get("request_id", "")).casefold() == str(request_id or "").casefold():
            return item
    return {}


def attach_department_approval(company_id: str, workflow_id: str, approval_id: int, approver_user_id: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE department_requests SET approval_id=?,approver_user_id=?,updated_at=? WHERE company_id=? AND workflow_id=? AND status='pending_approval'",
            (approval_id, approver_user_id, _now(), company_id, workflow_id),
        )


def create_purchase_order_from_request(company_id: str, user_id: str, workflow_id: str, source_request_id: str) -> Dict[str, Any]:
    """Create a procurement order and reserve stock in one database transaction."""
    actor = authorize_user(company_id, user_id)
    is_procurement_operator = str(actor.get("role") or "").casefold() in {"company_admin", "procurement_admin"}
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        source = conn.execute("SELECT * FROM department_requests WHERE company_id=? AND request_id=? AND service_area='Procurement' AND request_type='purchase_request'", (company_id, source_request_id)).fetchone()
        if source is None:
            return {"status": "not_found", "executed": False, "message": "The purchase request was not found in your account."}
        if source["user_id"] != user_id and not is_procurement_operator:
            return {"status": "permission_denied", "executed": False, "message": "You are not authorized to process another employee's purchase request."}
        if source["status"] not in {"submitted", "approved"}:
            return {"status": "invalid_state", "executed": False, "message": f"A purchase order cannot be created while request {source_request_id} is {str(source['status']).replace('_',' ')}."}
        description = f"Created from approved request {source_request_id}."
        existing = conn.execute("SELECT request_id,status FROM department_requests WHERE company_id=? AND request_type='purchase_order' AND description=? ORDER BY created_at DESC LIMIT 1", (company_id, description)).fetchone()
        if existing:
            return {"status": "success", "executed": False, "request_id": existing["request_id"], "status_label": existing["status"], "message": f"Purchase order {existing['request_id']} already exists for this request."}
        try:
            detail = json.loads(source["details_json"] or "{}")
            inventory_id = int(detail.get("inventory_id"))
            quantity = int(detail.get("quantity", 1))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"status": "invalid", "executed": False, "message": "The purchase request has invalid inventory details."}
        if quantity <= 0:
            return {"status": "invalid", "executed": False, "message": "The requested quantity is invalid."}
        if source["status"] == "submitted":
            stock = conn.execute("SELECT quantity_available FROM company_inventory WHERE company_id=? AND inventory_id=? AND status='active'", (company_id, inventory_id)).fetchone()
            if stock is None or int(stock["quantity_available"] or 0) < quantity:
                return {"status": "out_of_stock", "executed": False, "message": "The requested inventory is no longer available; no purchase order was created."}
            conn.execute("UPDATE company_inventory SET quantity_available=quantity_available-?,updated_at=? WHERE company_id=? AND inventory_id=?", (quantity, now, company_id, inventory_id))
            conn.execute("UPDATE department_requests SET status='approved',decision_reason='No approval required under company policy',updated_at=? WHERE company_id=? AND request_id=? AND status='submitted'", (now, company_id, source_request_id))
        order_id = f"PR-{uuid.uuid4().hex[:8].upper()}"
        title = f"Order for {detail.get('model') or source['title']}"
        order_details = {"source_request_id": source_request_id, **detail}
        conn.execute("INSERT INTO department_requests(request_id,company_id,user_id,service_area,request_type,title,description,amount,currency,status,workflow_id,details_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (order_id, company_id, source["user_id"], "Procurement", "purchase_order", title, description, source["amount"], source["currency"], "submitted", workflow_id or source["workflow_id"], json.dumps(order_details, ensure_ascii=False, default=str), now, now))
        conn.execute("INSERT INTO notifications(company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (company_id, source["user_id"], workflow_id or source["workflow_id"], "procurement_order_created", "Purchase order created", f"Purchase order {order_id} was created from {source_request_id}.", "department_request", order_id, now))
        conn.execute("INSERT INTO audit_logs(company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (company_id, user_id, workflow_id or source["workflow_id"], "purchase_order_created", "department_request", order_id, json.dumps({"source_request_id": source_request_id, "quantity": quantity}), now))
    return {"status": "success", "executed": True, "request_id": order_id, "service_area": "Procurement", "request_type": "purchase_order", "status_label": "submitted", "message": f"Purchase order {order_id} was created and inventory was reserved."}


def list_service_requests_for_admin(
    company_id: str,
    user_id: str,
    *,
    service_area: str = "HR",
    status: str = "All",
    search: str = "",
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """List tenant-scoped HR/IT requests for authorized department operators."""
    area = str(service_area or "").strip().upper()
    if area not in {"HR", "IT"}:
        raise ValueError("Only HR and IT request queues are supported here.")
    roles = ["company_admin", "hr_admin"] if area == "HR" else ["company_admin", "it_admin"]
    authorize_user(company_id, user_id, allowed_roles=roles)
    query = """SELECT r.request_id,r.user_id,u.name AS employee,u.department,
                      r.service_area,r.request_type,r.title,r.description,r.amount,r.currency,
                      r.status,r.workflow_id,r.approval_id,r.approver_user_id,r.decision_reason,
                      r.details_json,r.created_at,r.updated_at
               FROM department_requests r LEFT JOIN company_users u
                 ON u.company_id=r.company_id AND u.user_id=r.user_id
               WHERE r.company_id=? AND upper(r.service_area)=?"""
    params: list[Any] = [company_id, area]
    if status and status.casefold() != "all":
        query += " AND lower(r.status)=lower(?)"
        params.append(status)
    if str(search or "").strip():
        query += " AND (r.request_id LIKE ? OR r.title LIKE ? OR r.request_type LIKE ? OR r.description LIKE ? OR u.name LIKE ?)"
        match = f"%{str(search).strip()}%"
        params.extend([match] * 5)
    query += " ORDER BY r.updated_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 1000)))
    with _connect() as conn:
        rows = [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    for item in rows:
        try:
            item["details"] = json.loads(item.pop("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["details"] = {}
    return rows


def update_service_request_status_as_admin(
    company_id: str,
    user_id: str,
    request_id: str,
    *,
    status: str,
    comment: str = "",
) -> Dict[str, Any]:
    """Update a service request after its approval gate, with audit/notification."""
    request_id = str(request_id or "").strip()
    status = str(status or "").strip().casefold()
    comment = str(comment or "").strip()[:2000]
    allowed_statuses = {"submitted", "open", "in_progress", "needs_information", "resolved", "completed", "closed", "cancelled"}
    if status not in allowed_statuses:
        raise ValueError("Use the approval controls for approve/reject decisions; select a processing status here.")
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT request_id,user_id,service_area,status,workflow_id,details_json FROM department_requests WHERE company_id=? AND request_id=?",
            (company_id, request_id),
        ).fetchone()
        if row is None:
            return {"status": "not_found", "message": "The service request was not found in this company."}
        area = str(row["service_area"] or "").upper()
        roles = ["company_admin", "hr_admin"] if area == "HR" else ["company_admin", "it_admin"] if area == "IT" else []
        if not roles:
            return {"status": "invalid", "message": "Only HR and IT requests can be processed in this desk."}
        actor = authorize_user(company_id, user_id, allowed_roles=roles)
        current_status = str(row["status"] or "").casefold()
        if current_status in {"pending_approval", "needs_clarification"}:
            return {"status": "approval_required", "message": "This request is waiting for approval/clarification. Use the Pending Approvals controls before changing its processing status."}
        if status in {"completed", "resolved", "closed"} and current_status not in {"approved", "in_progress", "open", "submitted", "resolved", "completed"}:
            return {"status": "invalid_state", "message": f"The request cannot be completed from status {current_status or 'unknown'}."}
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            details = {}
        comments = details.get("processing_comments") if isinstance(details.get("processing_comments"), list) else []
        if comment:
            comments.append({"user_id": user_id, "comment": comment, "created_at": _now()})
            details["processing_comments"] = comments[-100:]
        now = _now()
        conn.execute(
            "UPDATE department_requests SET status=?,decision_reason=?,details_json=?,updated_at=? WHERE company_id=? AND request_id=?",
            (status, comment or f"Updated by authorized {area} operator {actor.get('user_id', user_id)}", json.dumps(details, ensure_ascii=False, default=str), now, company_id, request_id),
        )
        conn.execute(
            "INSERT INTO audit_logs(company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (company_id, user_id, row["workflow_id"], f"{area.lower()}_service_request_status_updated", "department_request", request_id, json.dumps({"old_status": current_status, "new_status": status, "comment_added": bool(comment)}, ensure_ascii=False), now),
        )
        conn.execute(
            "INSERT INTO notifications(company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (company_id, row["user_id"], row["workflow_id"], f"{area.lower()}_request_status_updated", f"{area} request status updated", f"{request_id} is now {status.replace('_', ' ')}.", "department_request", request_id, now),
        )
    return {"status": "success", "request_id": request_id, "request_status": status, "message": f"{area} request {request_id} was updated to {status.replace('_', ' ')}."}
