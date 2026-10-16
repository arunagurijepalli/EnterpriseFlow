from __future__ import annotations
from contextlib import contextmanager

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(
    os.getenv(
        "COMPANY_DB_PATH",
        str(DATA_DIR / "company.db"),
    )
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect():
    """Yield a configured connection and always close it."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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


def _json_dump(value: Any) -> str:
    if value is None:
        return "{}"

    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
    )


def _json_load(value: Optional[str]) -> Any:
    if not value:
        return {}

    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}


# ============================================================
# RESOLVE EMPLOYEE
# ============================================================

def get_employee_id(
    company_id: str,
    user_id: str,
) -> Optional[str]:
    """
    Resolve the stable employee_id from company_users.
    """

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT employee_id
            FROM company_users
            WHERE company_id = ?
              AND user_id = ?
            """,
            (
                str(company_id).strip(),
                str(user_id).strip(),
            ),
        ).fetchone()

    if not row:
        return None

    employee_id = str(
        row["employee_id"] or ""
    ).strip()

    return employee_id or None


# ============================================================
# EMPLOYEE PROFILE
# ============================================================

def get_employee_profile(
    employee_id: str,
    company_id: str,
) -> Dict[str, Any]:
    """
    Get one employee's complete master profile.
    """

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM employee_profiles
            WHERE employee_id = ?
              AND company_id = ?
            """,
            (
                str(employee_id).strip(),
                str(company_id).strip(),
            ),
        ).fetchone()

    return dict(row) if row else {}


def update_my_employee_profile(company_id: str, user_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Employees may update only their self-service contact/location fields."""
    from company.store import authorize_user
    authorize_user(company_id, user_id)
    employee_id = get_employee_id(company_id, user_id)
    if not employee_id:
        return {"status": "not_found", "message": "Your employee profile was not found."}
    allowed = {"phone", "location"}
    changes = {key: str(value or "").strip() for key, value in fields.items() if key in allowed}
    if not changes:
        return {"status": "invalid", "message": "No editable profile fields were supplied."}
    if "phone" in changes and len(changes["phone"]) > 40:
        return {"status": "invalid", "message": "Phone number is too long."}
    changes["updated_at"] = _utc_now()
    with _connect() as conn:
        cursor = conn.execute("UPDATE employee_profiles SET " + ",".join(f"{key}=?" for key in changes) + " WHERE company_id=? AND employee_id=? AND user_id=?", (*changes.values(), company_id, employee_id, user_id))
    if not cursor.rowcount:
        return {"status": "not_found", "message": "Your employee profile could not be updated."}
    return {"status": "success", "profile": get_employee_profile(employee_id, company_id), "message": "Your editable profile details were saved."}


# ============================================================
# RECORD ONE SERVICE EVENT
# ============================================================

def record_employee_service(
    *,
    company_id: str,
    user_id: str,
    service_area: str,
    service_type: str,
    action_type: str,
    description: str = "",
    status: str = "",
    decision: str = "",
    workflow_id: str = "",
    approval_id: Optional[int] = None,
    agent_name: str = "",
    tool_name: str = "",
    request_data: Optional[Dict[str, Any]] = None,
    result_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Record any employee service usage.

    This is intentionally generic so the same function can record:

    HR
    IT
    Finance
    Procurement
    Recruitment
    Policy
    Knowledge
    """

    company_id = str(company_id).strip()
    user_id = str(user_id).strip()

    employee_id = get_employee_id(
        company_id,
        user_id,
    )

    if not employee_id:
        raise ValueError(
            "Employee ID was not found for this user"
        )

    now = _utc_now()

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO employee_service_records (
                employee_id,
                company_id,
                service_area,
                service_type,
                action_type,
                description,
                status,
                decision,
                workflow_id,
                approval_id,
                agent_name,
                tool_name,
                request_data_json,
                result_data_json,
                performed_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                employee_id,
                company_id,
                str(service_area).strip(),
                str(service_type).strip(),
                str(action_type).strip(),
                str(description or ""),
                str(status or ""),
                str(decision or ""),
                str(workflow_id or ""),
                approval_id,
                str(agent_name or ""),
                str(tool_name or ""),
                _json_dump(request_data),
                _json_dump(result_data),
                now,
                now,
            ),
        )

        conn.commit()

        record_id = cursor.lastrowid

    return {
        "record_id": record_id,
        "employee_id": employee_id,
        "company_id": company_id,
        "service_area": service_area,
        "service_type": service_type,
        "action_type": action_type,
        "description": description,
        "status": status,
        "decision": decision,
        "workflow_id": workflow_id,
        "approval_id": approval_id,
        "agent_name": agent_name,
        "tool_name": tool_name,
        "performed_at": now,
    }


# ============================================================
# EMPLOYEE SERVICE HISTORY
# ============================================================

def get_employee_service_history(
    employee_id: str,
    company_id: str,
    service_area: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Get an employee's service history.

    Employee can later use this for:
        My Activity
        My Requests
        My Service History
    """

    limit = max(1, min(int(limit), 500))

    query = """
        SELECT *
        FROM employee_service_records
        WHERE employee_id = ?
          AND company_id = ?
    """

    params: List[Any] = [
        str(employee_id).strip(),
        str(company_id).strip(),
    ]

    if service_area:
        query += """
            AND lower(service_area) = lower(?)
        """
        params.append(
            str(service_area).strip()
        )

    query += """
        ORDER BY performed_at DESC
        LIMIT ?
    """

    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(
            query,
            tuple(params),
        ).fetchall()

    result = []

    for row in rows:
        item = dict(row)

        item["request_data"] = _json_load(
            item.pop("request_data_json", "")
        )

        item["result_data"] = _json_load(
            item.pop("result_data_json", "")
        )

        result.append(item)

    return result


# ============================================================
# CURRENT USER HISTORY
# ============================================================

def get_user_service_history(
    company_id: str,
    user_id: str,
    service_area: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Get service history only for the currently logged-in user.
    """

    from company.store import authorize_user
    authorize_user(company_id, user_id)
    employee_id = get_employee_id(
        company_id,
        user_id,
    )

    if not employee_id:
        return []

    history = get_employee_service_history(
        employee_id=employee_id,
        company_id=company_id,
        service_area=service_area,
        limit=limit,
    )
    # Department operations are stored as first-class requests. Include them
    # alongside the older activity log so users can see their real status.
    from company.request_service import list_my_department_requests

    requests = list_my_department_requests(
        company_id, user_id, service_area or "", limit=limit
    )
    request_workflows = {str(item.get("workflow_id") or "") for item in requests if item.get("workflow_id")}
    # First-class request rows supersede the older per-tool activity entries.
    history = [row for row in history if str(row.get("workflow_id") or "") not in request_workflows]
    for request in requests:
        workflow_id = str(request.get("workflow_id") or "")
        history.append({
            "record_id": request.get("request_id"),
            "request_id": request.get("request_id"),
            "workflow_id": workflow_id,
            "service_type": request.get("title") or request.get("request_type"),
            "service_area": request.get("service_area"),
            "description": request.get("description"),
            "status": request.get("status"),
            "action_type": request.get("request_type"),
            "decision": request.get("decision_reason") or "",
            "performed_at": request.get("created_at"),
        })
    if not service_area or str(service_area).casefold() == "hr":
        from company.leave_service import list_my_leave_requests
        leaves = list_my_leave_requests(company_id, user_id)[:max(1, min(int(limit), 500))]
        leave_workflows = {str(item.get("workflow_id") or "") for item in leaves if item.get("workflow_id")}
        history = [row for row in history if str(row.get("workflow_id") or "") not in leave_workflows]
        for leave in leaves:
            workflow_id = str(leave.get("workflow_id") or "")
            history.append({
                "record_id": leave.get("leave_request_id"),
                "request_id": leave.get("leave_request_id"),
                "workflow_id": workflow_id,
                "service_type": f"{leave.get('leave_type', 'Leave')} request",
                "service_area": "HR",
                "description": f"{leave.get('start_date')} to {leave.get('end_date')} · {leave.get('requested_days')} day(s)",
                "status": leave.get("status"),
                "action_type": "leave_request",
                "decision": leave.get("decision_reason") or "",
                "performed_at": leave.get("created_at"),
            })
    history.sort(key=lambda row: str(row.get("performed_at") or ""), reverse=True)
    return history[:max(1, min(int(limit), 500))]


# ============================================================
# COUNT SERVICES
# ============================================================

def count_employee_services(
    employee_id: str,
    company_id: str,
) -> int:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM employee_service_records
            WHERE employee_id = ?
              AND company_id = ?
            """,
            (
                str(employee_id).strip(),
                str(company_id).strip(),
            ),
        ).fetchone()

    return int(row["total"] if row else 0)


# ============================================================
# SERVICE AREA SUMMARY
# ============================================================

def get_employee_service_summary(
    employee_id: str,
    company_id: str,
) -> List[Dict[str, Any]]:
    """
    Example output:

    HR          -> 5
    IT          -> 3
    Finance     -> 2
    Procurement -> 4
    """

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                service_area,
                COUNT(*) AS service_count
            FROM employee_service_records
            WHERE employee_id = ?
              AND company_id = ?
            GROUP BY service_area
            ORDER BY service_count DESC, service_area
            """,
            (
                str(employee_id).strip(),
                str(company_id).strip(),
            ),
        ).fetchall()

    return [dict(row) for row in rows]
