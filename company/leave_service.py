from __future__ import annotations
from contextlib import contextmanager

import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List

from company.store import DB_PATH, get_company_context, initialize_company_store, authorize_user
from company.employee_service import get_employee_id


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


def _leave_policy(company_id: str) -> Dict[str, Any]:
    context = get_company_context(company_id)
    policies = context.get("policies", {}) if isinstance(context, dict) else {}
    leave = policies.get("leave", {}) if isinstance(policies, dict) else {}
    return leave if isinstance(leave, dict) else {}


def get_leave_summary(company_id: str, user_id: str) -> Dict[str, Any]:
    authorize_user(company_id, user_id)
    employee_id = get_employee_id(company_id, user_id)
    if not employee_id:
        return {"status": "not_found", "message": "Your employee profile was not found."}
    with _connect() as conn:
        employee = conn.execute(
            "SELECT leave_entitlement_days, leave_balance_days FROM employee_profiles WHERE company_id=? AND employee_id=?",
            (company_id, employee_id),
        ).fetchone()

        
        rows = conn.execute(
    """
    SELECT
        lr.leave_request_id,
        lr.leave_type,
        lr.start_date,
        lr.end_date,
        lr.requested_days,
        lr.reason,
        lr.status,
        lr.approval_id,
        lr.approver_user_id,
        lr.decision_reason,
        lr.created_at,
        lr.updated_at
    FROM leave_requests lr
    WHERE lr.company_id = ?
      AND lr.user_id = ?
      AND NOT EXISTS (
          SELECT 1
          FROM leave_history_hidden h
          WHERE h.company_id = lr.company_id
            AND h.user_id = lr.user_id
            AND h.leave_request_id = lr.leave_request_id
      )
    ORDER BY lr.created_at DESC
    """,
    (company_id, user_id),
    ).fetchall()
    if employee is None:
        return {"status": "not_found", "message": "Your employee profile was not found."}
    policy = _leave_policy(company_id)
    leave_types = policy.get("leave_types") or ["Annual Leave"]
    if isinstance(leave_types, dict):
        leave_types = list(leave_types)
    return {
        "status": "success",
        "employee_id": employee_id,
        "leave_entitlement": float(employee["leave_entitlement_days"] or 0),
        "leave_balance": float(employee["leave_balance_days"] or 0),
        "leave_types": leave_types,
        "policy": policy,
        "requests": [dict(row) for row in rows],
    }


def create_leave_request(
    *, company_id: str, user_id: str, workflow_id: str,
    start_date: str, end_date: str, leave_type: str = "",
    reason: str = "", requested_days: float | None = None,
) -> Dict[str, Any]:
    authorize_user(company_id, user_id)
    employee_id = get_employee_id(company_id, user_id)
    if not employee_id:
        return {"status": "not_found", "executed": False, "message": "Your employee profile was not found."}
    try:
        start = date.fromisoformat(str(start_date)[:10])
        end = date.fromisoformat(str(end_date)[:10])
    except (TypeError, ValueError):
        return {"status": "invalid", "executed": False, "message": "Please provide valid start and end dates in YYYY-MM-DD format."}
    if end < start:
        return {"status": "invalid", "executed": False, "message": "The end date must be on or after the start date."}
    if start < date.today():
        return {"status": "invalid", "executed": False, "message": "Leave cannot be requested for dates in the past."}
    
    if end < start:
        return {
            "status": "invalid",
            "executed": False,
            "message": "The end date must be on or after the start date."
        }

    if start < date.today():
        return {
            "status": "invalid",
            "executed": False,
            "message": "Leave cannot be requested for dates in the past."
        }

    # ADD THIS BLOCK: Validate leave purpose
    reason = str(reason or "").strip()

    if not reason:
        return {
            "status": "missing_information",
            "executed": False,
            "tool": "leave_management",
            "message": "Please provide the purpose of your leave before submitting the request."
        }

    # Existing code continues here
    policy = _leave_policy(company_id)

    policy = _leave_policy(company_id)
    configured_types = policy.get("leave_types") or ["Annual Leave"]
    if isinstance(configured_types, dict):
        configured_types = list(configured_types)
    if not isinstance(configured_types, list) or not configured_types:
        return {"status": "policy_unavailable", "executed": False, "message": "The company has not configured any leave types."}
    normalized_types = {str(value).strip().casefold(): str(value).strip() for value in configured_types if str(value).strip()}
    selected_type = str(leave_type or "").strip()
    if not selected_type and len(normalized_types) == 1:
        selected_type = next(iter(normalized_types.values()))
    if selected_type.casefold() not in normalized_types:
        return {"status": "missing_information", "executed": False, "message": "Please specify one of the company leave types: " + ", ".join(normalized_types.values()) + "."}
    selected_type = normalized_types[selected_type.casefold()]

    holidays = policy.get("holidays", [])
    if not isinstance(holidays, list):
        holidays = []
    holiday_dates = set()
    for holiday in holidays:
        value = holiday.get("date") if isinstance(holiday, dict) else holiday
        try:
            holiday_dates.add(date.fromisoformat(str(value)[:10]))
        except (TypeError, ValueError):
            continue
    count_weekends = bool(policy.get("count_weekends", False))
    days = sum(
        1 for offset in range((end - start).days + 1)
        if (count_weekends or (start.fromordinal(start.toordinal() + offset).weekday() < 5))
        and start.fromordinal(start.toordinal() + offset) not in holiday_dates
    )
    if requested_days is not None:
        try:
            supplied_days = float(requested_days)
        except (TypeError, ValueError):
            return {"status": "invalid", "executed": False, "message": "The requested leave duration is invalid."}
        if abs(supplied_days - days) > 0.001:
            return {"status": "invalid", "executed": False, "message": f"The dates calculate to {days} leave day(s) under company holiday and weekend rules; the supplied duration does not match."}
    if days <= 0:
        return {"status": "invalid", "executed": False, "message": "The selected date range contains no working days."}

    now = _now()
    request_id = f"LV-{start.year}-{uuid.uuid4().hex[:6].upper()}"
    needs_approval = bool(policy.get("manager_approval_required", True))
    initial_status = "pending_approval" if needs_approval else "approved"
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        employee = conn.execute(
            "SELECT leave_balance_days FROM employee_profiles WHERE company_id=? AND employee_id=?",
            (company_id, employee_id),
        ).fetchone()
        if employee is None:
            return {"status": "not_found", "executed": False, "message": "Your employee profile was not found."}
        balance = float(employee["leave_balance_days"] or 0)
        reserved = conn.execute(
            "SELECT COALESCE(SUM(requested_days),0) AS total FROM leave_requests WHERE company_id=? AND employee_id=? AND status='pending_approval'",
            (company_id, employee_id),
        ).fetchone()["total"]
        available = max(0.0, balance - float(reserved or 0))
        if days > available:
            return {"status": "insufficient_balance", "executed": False, "leave_balance": available, "requested_days": days, "message": f"You have {available:g} uncommitted leave day(s) available, but this request needs {days}."}
        conflict = conn.execute(
            "SELECT leave_request_id FROM leave_requests WHERE company_id=? AND employee_id=? AND status IN ('pending_approval','approved') AND start_date<=? AND end_date>=? LIMIT 1",
            (company_id, employee_id, end.isoformat(), start.isoformat()),
        ).fetchone()
        if conflict:
            return {"status": "conflict", "executed": False, "conflicting_request_id": conflict["leave_request_id"], "message": f"These dates overlap an existing leave request ({conflict['leave_request_id']})."}
        conn.execute(
            "INSERT INTO leave_requests (leave_request_id,company_id,user_id,employee_id,leave_type,start_date,end_date,requested_days,reason,status,workflow_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (request_id, company_id, user_id, employee_id, selected_type, start.isoformat(), end.isoformat(), days, str(reason or "").strip(), initial_status, workflow_id, now, now),
        )
        if not needs_approval:
            conn.execute("UPDATE employee_profiles SET leave_balance_days=leave_balance_days-? WHERE company_id=? AND employee_id=?", (days, company_id, employee_id))
        conn.execute(
            "INSERT INTO notifications (company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (company_id, user_id, workflow_id, "leave_submitted", "Leave request submitted", f"{request_id} is {initial_status.replace('_', ' ')}.", "leave_request", request_id, now),
        )
        conn.execute(
            "INSERT INTO audit_logs (company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (company_id, user_id, workflow_id, "leave_request_created", "leave_request", request_id, __import__("json").dumps({"status": initial_status, "days": days, "leave_type": selected_type}), now),
        )
    return {
        "status": "success", "executed": True, "tool": "leave_management",
        "action": "Leave request submitted", "request_id": request_id,
        "employee_id": employee_id, "requested_days": days,
        "leave_type": selected_type, "start_date": start.isoformat(),
        "end_date": end.isoformat(), "leave_balance": available,
        "status_label": initial_status, "approval_required": needs_approval,
        "message": f"Leave request {request_id} was created with status {initial_status.replace('_', ' ')}.",
    }


def attach_approval(company_id: str, workflow_id: str, approval_id: int, approver_user_id: str = "") -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            "UPDATE leave_requests SET approval_id=?, approver_user_id=?, updated_at=? WHERE company_id=? AND workflow_id=? AND status='pending_approval'",
            (approval_id, approver_user_id, now, company_id, workflow_id),
        )


def resolve_manager_user_id(company_id: str, employee_id: str) -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT manager.user_id FROM employee_profiles employee JOIN employee_profiles manager ON manager.company_id=employee.company_id AND manager.employee_id=employee.manager_employee_id JOIN company_users manager_user ON manager_user.company_id=manager.company_id AND manager_user.user_id=manager.user_id WHERE employee.company_id=? AND employee.employee_id=? AND manager_user.status='active'",
            (company_id, employee_id),
        ).fetchone()
    return str(row["user_id"] or "") if row else ""



def list_my_leave_requests(company_id: str, user_id: str) -> List[Dict[str, Any]]:
    authorize_user(company_id, user_id)

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                lr.leave_request_id,
                lr.leave_type,
                lr.start_date,
                lr.end_date,
                lr.requested_days,
                lr.reason,
                lr.status,
                lr.approval_id,
                lr.approver_user_id,
                lr.decision_reason,
                lr.created_at,
                lr.updated_at
            FROM leave_requests lr
            WHERE lr.company_id = ?
              AND lr.user_id = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM leave_history_hidden h
                  WHERE h.company_id = lr.company_id
                    AND h.user_id = lr.user_id
                    AND h.leave_request_id = lr.leave_request_id
              )
            ORDER BY lr.created_at DESC
            """,
            (company_id, user_id),
        ).fetchall()

    return [dict(row) for row in rows]


def hide_my_leave_history(
    company_id: str,
    user_id: str,
    request_id: str,
) -> Dict[str, Any]:
    authorize_user(company_id, user_id)
    now = _now()

    with _connect() as conn:
        request = conn.execute(
            """
            SELECT workflow_id
            FROM leave_requests
            WHERE company_id = ?
              AND user_id = ?
              AND leave_request_id = ?
            """,
            (company_id, user_id, request_id),
        ).fetchone()

        if request is None:
            return {
                "status": "not_found",
                "message": "Leave request was not found in your account.",
            }

        conn.execute(
            """
            INSERT OR IGNORE INTO leave_history_hidden
                (company_id, user_id, leave_request_id, hidden_at)
            VALUES (?, ?, ?, ?)
            """,
            (company_id, user_id, request_id, now),
        )

        conn.execute(
            """
            INSERT INTO audit_logs
                (company_id, user_id, workflow_id, action,
                 resource_type, resource_id, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                user_id,
                request["workflow_id"],
                "leave_history_hidden",
                "leave_request",
                request_id,
                "{}",
                now,
            ),
        )

    return {
        "status": "success",
        "message": "Leave request hidden from your history.",
    }


def get_my_leave_request(company_id: str, user_id: str, request_id: str) -> Dict[str, Any]:
    authorize_user(company_id, user_id)
    with _connect() as conn:
        row = conn.execute(
            "SELECT leave_request_id,leave_type,start_date,end_date,requested_days,reason,status,approval_id,approver_user_id,decision_reason,created_at,updated_at FROM leave_requests WHERE company_id=? AND user_id=? AND leave_request_id=?",
            (company_id, user_id, request_id),
        ).fetchone()
    return dict(row) if row else {}


def list_my_notifications(company_id: str, user_id: str) -> List[Dict[str, Any]]:
    authorize_user(company_id, user_id)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT notification_id,notification_type,title,body,resource_type,resource_id,read_at,created_at FROM notifications WHERE company_id=? AND user_id=? ORDER BY created_at DESC LIMIT 50",
            (company_id, user_id),
        ).fetchall()
    return [dict(row) for row in rows]


def cancel_leave_request(company_id: str, user_id: str, request_id: str) -> Dict[str, Any]:
    authorize_user(company_id, user_id)
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        request = conn.execute(
            "SELECT workflow_id,status FROM leave_requests WHERE company_id=? AND user_id=? AND leave_request_id=?",
            (company_id, user_id, request_id),
        ).fetchone()
        if request is None:
            return {"status": "not_found", "message": "That leave request was not found in your account."}
        if request["status"] != "pending_approval":
            return {"status": "not_cancellable", "message": "Only leave requests awaiting approval can be cancelled."}
        conn.execute(
            "UPDATE leave_requests SET status='cancelled',updated_at=? WHERE company_id=? AND user_id=? AND leave_request_id=? AND status='pending_approval'",
            (now, company_id, user_id, request_id),
        )
        conn.execute(
            "UPDATE approvals SET status='cancelled',reason='Cancelled by requester',decided_at=? WHERE company_id=? AND workflow_id=? AND status='pending'",
            (now, company_id, request["workflow_id"]),
        )
        conn.execute(
            "INSERT INTO audit_logs (company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (company_id, user_id, request["workflow_id"], "leave_request_cancelled", "leave_request", request_id, "{}", now),
        )
        conn.execute(
            "INSERT INTO notifications (company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (company_id, user_id, request["workflow_id"], "leave_cancelled", "Leave request cancelled", f"{request_id} was cancelled.", "leave_request", request_id, now),
        )
    return {"status": "success", "message": f"Leave request {request_id} was cancelled."}
