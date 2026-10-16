from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from company.store import DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect():
    """Yield a database connection and always close it.

    ``sqlite3.Connection`` used directly in a ``with`` statement commits or
    rolls back, but does not close the file handle. That caused Windows tests
    to fail deleting their temporary databases and could retain locks longer
    than necessary. Keep transaction handling explicit and close deterministically.
    """
    from company.store import initialize_company_store
    initialize_company_store()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_approval(
    company_id: str,
    workflow_id: str,
    requested_by: str,
    approval_type: str,
    reason: str = "",
    approver_user_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    metadata = metadata or {}
    requested_at = _now()

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO approvals (
                company_id,
                workflow_id,
                requested_by,
                approver_user_id,
                approval_type,
                status,
                reason,
                requested_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                company_id,
                workflow_id,
                requested_by,
                approver_user_id,
                approval_type,
                reason,
                requested_at,
                json.dumps(metadata),
            ),
        )

        approval_id = cursor.lastrowid
        area = str(metadata.get("service_area") or metadata.get("department") or "").strip().lower()
        area_role = {"it": "it_admin", "finance": "finance_admin", "procurement": "procurement_admin", "recruitment": "recruitment_admin", "hr": "hr_admin"}.get(area)
        if approver_user_id:
            recipients = [approver_user_id]
        else:
            # Route notifications to the company admin and the matching
            # department admin, rather than notifying unrelated departments.
            roles = {"company_admin", area_role} if area_role else {"company_admin", "hr_admin"}
            placeholders = ",".join("?" for _ in roles)
            recipients = [row[0] for row in conn.execute(f"SELECT user_id FROM company_users WHERE company_id=? AND status='active' AND role IN ({placeholders}) ORDER BY CASE WHEN role='company_admin' THEN 0 ELSE 1 END", (company_id, *sorted(roles))).fetchall()]
        request_id = str(metadata.get("request_id") or "").strip()
        for recipient in recipients:
            if recipient == requested_by:
                continue
            conn.execute("INSERT INTO notifications(company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (company_id, recipient, workflow_id, "approval_required", "Approval required", f"{approval_type.replace('_', ' ').title()} request {request_id or workflow_id} is waiting for your review.", "approval", str(approval_id), requested_at))
        conn.execute("INSERT INTO audit_logs(company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (company_id, requested_by, workflow_id, "approval_created", "approval", str(approval_id), json.dumps({"approval_type": approval_type, "approver_user_id": approver_user_id, "request_id": request_id}), requested_at))

    approval = get_approval(
        company_id=company_id,
        approval_id=approval_id,
    )

    return get_approval(
        company_id=company_id,
        approval_id=approval_id,
    )


def get_approval(
    company_id: str,
    approval_id: int,
) -> Optional[Dict[str, Any]]:

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                approval_id,
                company_id,
                workflow_id,
                requested_by,
                approver_user_id,
                approval_type,
                status,
                reason,
                requested_at,
                decided_at,
                metadata_json
            FROM approvals
            WHERE company_id = ?
              AND approval_id = ?
            """,
            (
                company_id,
                approval_id,
            ),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    try:
        result["metadata"] = json.loads(
            result.get("metadata_json") or "{}"
        )
    except (TypeError, json.JSONDecodeError):
        result["metadata"] = {}

    return result


def list_pending_approvals(
    company_id: str,
    approver_user_id: Optional[str] = None,
    approval_type: Optional[str] = None,
) -> List[Dict[str, Any]]:

    query = """
        SELECT
            a.approval_id,
            a.company_id,
            a.workflow_id,
            a.requested_by,
            a.approver_user_id,
            a.approval_type,
            a.status,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM leave_requests lr
                    WHERE lr.company_id = a.company_id
                      AND lr.workflow_id = a.workflow_id
                      AND a.approval_type LIKE '%leave%'
                )
                THEN COALESCE((
                    SELECT NULLIF(lr.reason, '')
                    FROM leave_requests lr
                    WHERE lr.company_id = a.company_id
                      AND lr.workflow_id = a.workflow_id
                    LIMIT 1
                ), a.reason)
                ELSE a.reason
            END AS reason,
            a.requested_at,
            a.decided_at,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM leave_requests lr
                    WHERE lr.company_id = a.company_id
                      AND lr.workflow_id = a.workflow_id
                )
                THEN json_set(
                    a.metadata_json,
                    '$.tool', 'leave_management',
                    '$.request_id', (
                        SELECT lr.leave_request_id FROM leave_requests lr
                        WHERE lr.company_id = a.company_id
                          AND lr.workflow_id = a.workflow_id LIMIT 1
                    ),
                    '$.start_date', (
                        SELECT lr.start_date FROM leave_requests lr
                        WHERE lr.company_id = a.company_id
                          AND lr.workflow_id = a.workflow_id LIMIT 1
                    ),
                    '$.end_date', (
                        SELECT lr.end_date FROM leave_requests lr
                        WHERE lr.company_id = a.company_id
                          AND lr.workflow_id = a.workflow_id LIMIT 1
                    ),
                    '$.requested_days', (
                        SELECT lr.requested_days FROM leave_requests lr
                        WHERE lr.company_id = a.company_id
                          AND lr.workflow_id = a.workflow_id LIMIT 1
                    ),
                    '$.employee_purpose', (
                        SELECT lr.reason FROM leave_requests lr
                        WHERE lr.company_id = a.company_id
                          AND lr.workflow_id = a.workflow_id LIMIT 1
                    )
                )
                WHEN EXISTS (
                    SELECT 1 FROM department_requests dr
                    WHERE dr.company_id = a.company_id
                      AND dr.workflow_id = a.workflow_id
                )
                THEN json_set(
                    a.metadata_json,
                    '$.request_id', (
                        SELECT dr.request_id FROM department_requests dr
                        WHERE dr.company_id = a.company_id
                          AND dr.workflow_id = a.workflow_id LIMIT 1
                    ),
                    '$.service_area', (
                        SELECT dr.service_area FROM department_requests dr
                        WHERE dr.company_id = a.company_id
                          AND dr.workflow_id = a.workflow_id LIMIT 1
                    ),
                    '$.title', (
                        SELECT dr.title FROM department_requests dr
                        WHERE dr.company_id = a.company_id
                          AND dr.workflow_id = a.workflow_id LIMIT 1
                    )
                )
                ELSE a.metadata_json
            END AS metadata_json
        FROM approvals a
        WHERE a.company_id = ?
          AND a.status = 'pending'
    """

    params: List[Any] = [company_id]

    if approver_user_id:
        query += """
            AND (
                approver_user_id = ?
                OR approver_user_id = ''
                OR approver_user_id IS NULL
            )
        """
        params.append(approver_user_id)

    if approval_type:
        query += " AND approval_type = ?"
        params.append(approval_type)

    query += " ORDER BY requested_at ASC"

    with _connect() as conn:
        rows = conn.execute(
            query,
            tuple(params),
        ).fetchall()

    results = []

    for row in rows:
        item = dict(row)

        try:
            item["metadata"] = json.loads(
                item.get("metadata_json") or "{}"
            )
        except (TypeError, json.JSONDecodeError):
            item["metadata"] = {}

        results.append(item)

    return results



def reconcile_pending_approval_records(company_id: Optional[str] = None) -> int:
    """Backfill missing approval rows for legacy requests already marked pending.

    Idempotent: reuses an existing pending approval for the workflow and only
    creates a new approval when no matching approval record exists.
    """
    from company.store import initialize_company_store
    from company.request_service import attach_department_approval
    from company.leave_service import attach_approval

    initialize_company_store()
    scope_sql = " AND company_id = ?" if company_id else ""
    params = (company_id,) if company_id else ()
    with _connect() as conn:
        dept_rows = conn.execute(
            "SELECT company_id,user_id,workflow_id,request_id,service_area,request_type,title,description,status,approval_id,approver_user_id,created_at "
            "FROM department_requests WHERE status='pending_approval'" + scope_sql + " ORDER BY created_at",
            params,
        ).fetchall()
        leave_rows = conn.execute(
            "SELECT company_id,user_id,workflow_id,leave_request_id,leave_type,reason,status,approval_id,approver_user_id,created_at,start_date,end_date,requested_days "
            "FROM leave_requests WHERE status='pending_approval'" + scope_sql + " ORDER BY created_at",
            params,
        ).fetchall()
        workflow_rows = conn.execute(
            "SELECT company_id,user_id,workflow_id,request_text,request_category,intent,"
            "status,selected_tools_json,context_json,created_at,updated_at "
            "FROM workflow_requests WHERE lower(status)='pending_approval'" + scope_sql + " ORDER BY created_at",
            params,
        ).fetchall()

    created_or_attached = 0
    for row_obj in dept_rows:
        row = dict(row_obj)
        current_id = row.get("approval_id")
        with _connect() as conn:
            existing = None
            if current_id:
                existing = conn.execute(
                    "SELECT approval_id,status FROM approvals WHERE company_id=? AND approval_id=?",
                    (row["company_id"], current_id),
                ).fetchone()
            if not existing:
                workflow_id = str(row.get("workflow_id") or "").strip()
                if workflow_id:
                    existing = conn.execute(
                        "SELECT approval_id,status FROM approvals WHERE company_id=? AND workflow_id=? AND requested_by=? ORDER BY approval_id DESC LIMIT 1",
                        (row["company_id"], workflow_id, row["user_id"]),
                    ).fetchone()
                else:
                    # Legacy rows with blank workflow IDs must match via the
                    # stable request ID in approval metadata, never via the
                    # empty workflow ID (which can belong to other requests).
                    existing = conn.execute(
                        "SELECT approval_id,status FROM approvals WHERE company_id=? AND requested_by=? AND json_extract(metadata_json, '$.request_id')=? ORDER BY approval_id DESC LIMIT 1",
                        (row["company_id"], row["user_id"], row["request_id"]),
                    ).fetchone()
        if existing:
            approval_id = int(existing["approval_id"])
            workflow_id = str(row.get("workflow_id") or "").strip()
            if str(existing["status"]).casefold() == "pending" and (not current_id or int(current_id) != approval_id):
                approver = str(row.get("approver_user_id") or "")
                if workflow_id:
                    attach_department_approval(row["company_id"], workflow_id, approval_id, approver)
                else:
                    with _connect() as conn:
                        conn.execute(
                            "UPDATE department_requests SET approval_id=?,approver_user_id=?,updated_at=? WHERE company_id=? AND request_id=? AND status='pending_approval'",
                            (approval_id, approver, _now(), row["company_id"], row["request_id"]),
                        )
                created_or_attached += 1
            continue
        approval_type = f"{str(row.get('service_area') or 'company').lower()}_request"
        result = create_approval(
            company_id=row["company_id"],
            workflow_id=str(row.get("workflow_id") or f"legacy-{row['request_id']}"),
            requested_by=row["user_id"],
            approval_type=approval_type,
            reason=str(row.get("description") or row.get("title") or row.get("request_type") or "Request pending review"),
            approver_user_id=str(row.get("approver_user_id") or ""),
            metadata={"request_id": row["request_id"], "service_area": row.get("service_area"), "request_type": row.get("request_type"), "title": row.get("title"), "legacy_backfill": True},
        )
        if str(row.get("workflow_id") or "").strip():
            attach_department_approval(row["company_id"], str(row["workflow_id"]), int(result["approval_id"]), str(row.get("approver_user_id") or ""))
        else:
            with _connect() as conn:
                conn.execute("UPDATE department_requests SET approval_id=?,approver_user_id=?,updated_at=? WHERE company_id=? AND request_id=? AND status='pending_approval'", (int(result["approval_id"]), str(row.get("approver_user_id") or ""), _now(), row["company_id"], row["request_id"]))
        created_or_attached += 1

    for row_obj in leave_rows:
        row = dict(row_obj)
        current_id = row.get("approval_id")
        with _connect() as conn:
            existing = None
            if current_id:
                existing = conn.execute(
                    "SELECT approval_id,status FROM approvals WHERE company_id=? AND approval_id=?",
                    (row["company_id"], current_id),
                ).fetchone()
            if not existing:
                workflow_id = str(row.get("workflow_id") or "").strip()
                if workflow_id:
                    existing = conn.execute(
                        "SELECT approval_id,status FROM approvals WHERE company_id=? AND workflow_id=? AND requested_by=? ORDER BY approval_id DESC LIMIT 1",
                        (row["company_id"], workflow_id, row["user_id"]),
                    ).fetchone()
                else:
                    existing = conn.execute(
                        "SELECT approval_id,status FROM approvals WHERE company_id=? AND requested_by=? AND json_extract(metadata_json, '$.request_id')=? ORDER BY approval_id DESC LIMIT 1",
                        (row["company_id"], row["user_id"], row["leave_request_id"]),
                    ).fetchone()
        if existing:
            workflow_id = str(row.get("workflow_id") or "").strip()
            existing_id = int(existing["approval_id"])
            if str(existing["status"]).casefold() == "pending" and (not current_id or int(current_id) != existing_id):
                approver = str(row.get("approver_user_id") or "")
                if workflow_id:
                    attach_approval(row["company_id"], workflow_id, existing_id, approver)
                else:
                    with _connect() as conn:
                        conn.execute(
                            "UPDATE leave_requests SET approval_id=?,approver_user_id=?,updated_at=? WHERE company_id=? AND leave_request_id=? AND status='pending_approval'",
                            (existing_id, approver, _now(), row["company_id"], row["leave_request_id"]),
                        )
                created_or_attached += 1
            continue
        result = create_approval(
            company_id=row["company_id"],
            workflow_id=str(row.get("workflow_id") or f"legacy-{row['leave_request_id']}"),
            requested_by=row["user_id"],
            approval_type="leave_request",
            reason=str(row.get("reason") or "Leave request pending approval"),
            approver_user_id=str(row.get("approver_user_id") or ""),
            metadata={"tool": "leave_management", "request_id": row["leave_request_id"], "service_area": "HR", "title": f"{row.get('leave_type') or 'Leave'} request", "start_date": row.get("start_date"), "end_date": row.get("end_date"), "requested_days": row.get("requested_days"), "employee_purpose": row.get("reason"), "legacy_backfill": True},
        )
        if str(row.get("workflow_id") or "").strip():
            attach_approval(row["company_id"], str(row["workflow_id"]), int(result["approval_id"]), str(row.get("approver_user_id") or ""))
        else:
            with _connect() as conn:
                conn.execute("UPDATE leave_requests SET approval_id=?,approver_user_id=?,updated_at=? WHERE company_id=? AND leave_request_id=? AND status='pending_approval'", (int(result["approval_id"]), str(row.get("approver_user_id") or ""), _now(), row["company_id"], row["leave_request_id"]))
        created_or_attached += 1

    # Some older versions persisted only workflow_requests and never created
    # the corresponding approval row. Backfill those records so they appear in
    # the employee's pending list and the authorized admin approval queue.
    for row_obj in workflow_rows:
        row = dict(row_obj)
        workflow_id = str(row.get("workflow_id") or "").strip()
        if not workflow_id:
            continue
        with _connect() as conn:
            existing = conn.execute(
                "SELECT approval_id,status FROM approvals WHERE company_id=? AND workflow_id=? AND requested_by=? ORDER BY approval_id DESC LIMIT 1",
                (row["company_id"], workflow_id, row["user_id"]),
            ).fetchone()
            context_row = conn.execute(
                "SELECT context_json,selected_tools_json FROM workflow_requests WHERE company_id=? AND workflow_id=?",
                (row["company_id"], workflow_id),
            ).fetchone()
        if existing:
            # Do not create duplicate approvals for workflows already approved,
            # rejected, or still pending in the approvals table.
            existing_status = str(existing["status"] or "").casefold()
            if existing_status in {"approved", "rejected", "cancelled"}:
                with _connect() as conn:
                    conn.execute(
                        "UPDATE workflow_requests SET status=?,updated_at=? WHERE company_id=? AND workflow_id=? AND lower(status)='pending_approval'",
                        (existing_status, _now(), row["company_id"], workflow_id),
                    )
            continue

        context: Dict[str, Any] = {}
        selected_tools: List[str] = []
        if context_row:
            try:
                context = json.loads(context_row["context_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                context = {}
            try:
                selected_tools = json.loads(context_row["selected_tools_json"] or "[]")
            except (TypeError, json.JSONDecodeError):
                selected_tools = []
        if not isinstance(context, dict):
            context = {}
        if not isinstance(selected_tools, list):
            selected_tools = []
        departments = context.get("departments") if isinstance(context.get("departments"), list) else []
        service_area = str(departments[0] if departments else "").strip()
        first_tool = str(selected_tools[0] if selected_tools else "").casefold()
        intent = str(row.get("intent") or "").strip()
        if not service_area:
            if first_tool in {"create_ticket", "device_service", "password_access_service", "software_service", "knowledge_base_service"} or intent.startswith("it_"):
                service_area = "IT"
            elif first_tool.startswith("hr_") or first_tool in {"leave_management", "benefits_service", "hr_training_service"} or intent.startswith(("hr_", "leave", "employee_", "professional_", "payroll_")):
                service_area = "HR"
            elif first_tool in {"purchase_request", "purchase_order", "hardware_catalog", "inventory_check"}:
                service_area = "Procurement"
            else:
                service_area = "Company"
        tool_results = context.get("tool_results") if isinstance(context.get("tool_results"), list) else []
        request_id = ""
        for tool_result in tool_results:
            if isinstance(tool_result, dict):
                request_id = str(tool_result.get("request_id") or "").strip()
                if request_id:
                    break
        request_text = str(row.get("request_text") or "Company workflow request").strip()
        title = intent.replace("_", " ").title() if intent else request_text[:150]
        result = create_approval(
            company_id=row["company_id"],
            workflow_id=workflow_id,
            requested_by=row["user_id"],
            approval_type=intent or f"{service_area.casefold()}_request",
            reason=request_text,
            metadata={
                "request_id": request_id or workflow_id,
                "service_area": service_area,
                "department": service_area,
                "request_type": intent or row.get("request_category") or "workflow_request",
                "title": title,
                "tool": first_tool,
                "request_category": row.get("request_category") or "",
                "legacy_workflow_backfill": True,
            },
        )
        if result:
            created_or_attached += 1

    return created_or_attached


def _record_audit(
    *,
    company_id: str,
    user_id: str = "",
    workflow_id: str = "",
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    details: dict | None = None,
) -> None:

    from datetime import datetime, timezone

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (
                company_id,
                user_id,
                workflow_id,
                action,
                resource_type,
                resource_id,
                details_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                user_id,
                workflow_id,
                action,
                resource_type,
                resource_id,
                json.dumps(
                    details or {},
                    ensure_ascii=False,
                    default=str,
                ),
                created_at,
            ),
        )


def decide_approval(
    company_id: str,
    approval_id: int,
    approver_user_id: str,
    decision: str,
    reason: str = "",
) -> Optional[Dict[str, Any]]:

    decision = decision.strip().lower()

    if decision not in {"approved", "rejected"}:
        raise ValueError(
            "Approval decision must be 'approved' or 'rejected'."
        )

    decided_at = _now()
    purchase_order_id = ""

    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT
                approval_id,
                status,
                approver_user_id,
                requested_by,
                metadata_json,
                workflow_id
            FROM approvals
            WHERE company_id = ?
              AND approval_id = ?
            """,
            (
                company_id,
                approval_id,
            ),
        ).fetchone()

        if row is None:
            return None

        if row["status"] != "pending":
            raise ValueError(
                "This approval has already been decided."
            )

        try:
            approval_metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            approval_metadata = {}
        leave_row = None
        department_request = None
        if approval_metadata.get("tool") == "leave_management":
            if str(row["requested_by"] or "") == str(approver_user_id):
                raise PermissionError("Employees cannot approve their own requests.")
            approver_user = conn.execute(
                "SELECT role,status FROM company_users WHERE company_id=? AND user_id=?",
                (company_id, approver_user_id),
            ).fetchone()
            if approver_user is None or str(approver_user["status"] or "").lower() != "active":
                raise PermissionError("The approver account is unavailable or inactive.")
            if row["approver_user_id"] and row["approver_user_id"] != approver_user_id:
                raise PermissionError("This approval is assigned to another approver.")
            if not row["approver_user_id"] and str(approver_user["role"] or "").lower() not in {"company_admin", "hr_admin"}:
                raise PermissionError("You are not authorized to decide this leave approval.")

            leave_row = conn.execute(
                "SELECT leave_request_id,employee_id,requested_days,user_id FROM leave_requests WHERE company_id=? AND workflow_id=? AND status='pending_approval'",
                (company_id, row["workflow_id"]),
            ).fetchone()
            if leave_row and decision == "approved":
                balance_row = conn.execute(
                    "SELECT leave_balance_days FROM employee_profiles WHERE company_id=? AND employee_id=?",
                    (company_id, leave_row["employee_id"]),
                ).fetchone()
                available = float(balance_row["leave_balance_days"] or 0) if balance_row else 0
                if available < float(leave_row["requested_days"] or 0):
                    raise ValueError("The current leave balance is insufficient to finalize this approval.")
        elif approval_metadata.get("request_id"):
            from company.store import authorize_user
            approver_user = conn.execute(
                "SELECT role,status FROM company_users WHERE company_id=? AND user_id=?",
                (company_id, approver_user_id),
            ).fetchone()
            if approver_user is None or str(approver_user["status"] or "").lower() != "active":
                raise PermissionError("The approver account is unavailable or inactive.")
            if str(row["requested_by"] or "") == str(approver_user_id):
                raise PermissionError("Employees cannot approve their own requests.")
            if row["approver_user_id"] and row["approver_user_id"] != approver_user_id:
                raise PermissionError("This approval is assigned to another approver.")
            area = str(approval_metadata.get("service_area") or approval_metadata.get("department") or "").lower()
            area_role = {"it": "it_admin", "finance": "finance_admin", "procurement": "procurement_admin", "recruitment": "recruitment_admin", "hr": "hr_admin"}.get(area)
            allowed_roles = {"company_admin", "hr_admin"}
            if area_role:
                allowed_roles.add(area_role)
            if not row["approver_user_id"] and str(approver_user["role"] or "").lower() not in allowed_roles:
                raise PermissionError("You are not authorized to decide this department approval.")
            department_request = conn.execute(
                "SELECT request_id,user_id,service_area,request_type,title,description,amount,currency,details_json FROM department_requests WHERE company_id=? AND workflow_id=? AND status='pending_approval'",
                (company_id, row["workflow_id"]),
            ).fetchone()
            if department_request and decision == "approved" and department_request["request_type"] == "purchase_request":
                try:
                    purchase_details = json.loads(department_request["details_json"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    purchase_details = {}
                try:
                    requested_quantity = int(purchase_details.get("quantity", 1))
                    inventory_id = int(purchase_details.get("inventory_id"))
                except (TypeError, ValueError):
                    raise ValueError("The purchase request has invalid inventory details.")
                stock = conn.execute(
                    "SELECT quantity_available FROM company_inventory WHERE company_id=? AND inventory_id=? AND status='active'",
                    (company_id, inventory_id),
                ).fetchone()
                if stock is None or int(stock["quantity_available"] or 0) < requested_quantity:
                    raise ValueError("The requested inventory is no longer available; the approval was not applied.")
                purchase_details["approved_inventory_id"] = inventory_id
                purchase_details["approved_quantity"] = requested_quantity

        conn.execute(
            """
            UPDATE approvals
            SET
                status = ?,
                approver_user_id = ?,
                reason = ?,
                decided_at = ?
            WHERE company_id = ?
              AND approval_id = ?
            """,
            (
                decision,
                approver_user_id,
                reason,
                decided_at,
                company_id,
                approval_id,
            ),
        )
        if row and approval_metadata.get("tool") == "leave_management" and leave_row:
            leave_status = "approved" if decision == "approved" else "rejected"
            if decision == "approved":
                conn.execute(
                    "UPDATE employee_profiles SET leave_balance_days=leave_balance_days-?, updated_at=? WHERE company_id=? AND employee_id=?",
                    (leave_row["requested_days"], decided_at, company_id, leave_row["employee_id"]),
                )
            conn.execute(
                "UPDATE leave_requests SET status=?,approver_user_id=?,decision_reason=?,updated_at=? WHERE company_id=? AND leave_request_id=? AND status='pending_approval'",
                (leave_status, approver_user_id, reason, decided_at, company_id, leave_row["leave_request_id"]),
            )
            # Keep employee service history aligned with the leave decision.
            conn.execute(
                """
                UPDATE employee_service_records
                SET action_type=?, status=?, decision=?, approval_id=?, updated_at=?
                WHERE company_id=? AND employee_id=? AND workflow_id=?
                  AND tool_name='leave_management'
                  AND status='success' AND action_type='Executed'
                  AND approval_id IS NULL
                """,
                (
                    "Completed" if decision == "approved" else "Rejected",
                    leave_status,
                    decision.upper(),
                    approval_id,
                    decided_at,
                    company_id,
                    leave_row["employee_id"],
                    row["workflow_id"],
                ),
            )
            conn.execute(
                "INSERT INTO notifications (company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (company_id, leave_row["user_id"], row["workflow_id"], f"leave_{decision}", f"Leave request {decision}", f"{leave_row['leave_request_id']} was {decision}." + (f" Reason: {reason}" if decision == "rejected" and reason else ""), "leave_request", leave_row["leave_request_id"], decided_at),
            )
            conn.execute(
                "INSERT INTO audit_logs (company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (company_id, approver_user_id, row["workflow_id"], f"leave_{decision}", "leave_request", leave_row["leave_request_id"], json.dumps({"reason": reason, "days": leave_row["requested_days"]}), decided_at),
            )
        elif row and department_request:
            request_status = "approved" if decision == "approved" else "rejected"
            if decision == "approved" and department_request["request_type"] == "purchase_request":
                conn.execute(
                    "UPDATE company_inventory SET quantity_available=quantity_available-?,updated_at=? WHERE company_id=? AND inventory_id=?",
                    (requested_quantity, decided_at, company_id, inventory_id),
                )
                try:
                    purchase_details = json.loads(department_request["details_json"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    purchase_details = {}
                purchase_order_id = f"PO-{datetime.now(timezone.utc):%Y%m%d}-{approval_id:06d}"
                purchase_details.update({
                    "source_request_id": department_request["request_id"],
                    "purchase_order_id": purchase_order_id,
                    "reserved_inventory_id": inventory_id,
                    "reserved_quantity": requested_quantity,
                })
                conn.execute(
                    "UPDATE department_requests SET details_json=?,updated_at=? WHERE company_id=? AND request_id=?",
                    (json.dumps(purchase_details, ensure_ascii=False), decided_at, company_id, department_request["request_id"]),
                )
                conn.execute(
                    "INSERT INTO department_requests(request_id,company_id,user_id,service_area,request_type,title,description,amount,currency,status,workflow_id,details_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (purchase_order_id, company_id, department_request["user_id"], "Procurement", "purchase_order", f"Order for {department_request['title']}", f"Created from approved request {department_request['request_id']}.", department_request["amount"], department_request["currency"], "processing", row["workflow_id"], json.dumps(purchase_details, ensure_ascii=False), decided_at, decided_at),
                )
                conn.execute(
                    "INSERT INTO notifications(company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (company_id, department_request["user_id"], row["workflow_id"], "procurement_order_created", "Purchase order created", f"Purchase order {purchase_order_id} was created for {department_request['request_id']} and is processing.", "department_request", purchase_order_id, decided_at),
                )
                conn.execute(
                    "INSERT INTO audit_logs(company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (company_id, approver_user_id, row["workflow_id"], "purchase_order_created", "department_request", purchase_order_id, json.dumps({"source_request_id": department_request["request_id"], "quantity": requested_quantity, "inventory_id": inventory_id}), decided_at),
                )
            conn.execute(
                "UPDATE department_requests SET status=?,approver_user_id=?,decision_reason=?,updated_at=? WHERE company_id=? AND request_id=? AND status='pending_approval'",
                (request_status, approver_user_id, reason, decided_at, company_id, department_request["request_id"]),
            )
            conn.execute(
                "INSERT INTO notifications (company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (company_id, department_request["user_id"], row["workflow_id"], f"{department_request['service_area'].lower()}_request_{decision}", f"Request {decision}", f"{department_request['request_id']} was {decision}." + (f" Reason: {reason}" if decision == "rejected" and reason else ""), "department_request", department_request["request_id"], decided_at),
            )
            conn.execute(
                "INSERT INTO audit_logs (company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (company_id, approver_user_id, row["workflow_id"], f"department_request_{decision}", "department_request", department_request["request_id"], json.dumps({"reason": reason}), decided_at),
            )

    approval = get_approval(
        company_id=company_id,
        approval_id=approval_id,
    )

    if approval:
        try:
            from company.memory_service import update_workflow_status, save_workflow_execution
            final_status = "completed" if decision == "approved" else "rejected"
            update_workflow_status(
                company_id, str(approval.get("workflow_id") or ""), final_status,
                {"action": decision.upper(), "approval_id": approval_id, "approver_user_id": approver_user_id, "reason": reason},
            )
            save_workflow_execution(
                company_id, str(approval.get("workflow_id") or ""), "approval_decision",
                input_data={"approval_id": approval_id},
                output_data={"status": decision, "approver_user_id": approver_user_id, "reason": reason},
            )
            if purchase_order_id:
                save_workflow_execution(
                    company_id, str(approval.get("workflow_id") or ""), "inventory_reserved",
                    input_data={"approval_id": approval_id},
                    output_data={"inventory_id": inventory_id, "quantity": requested_quantity, "status": "reserved"},
                )
                save_workflow_execution(
                    company_id, str(approval.get("workflow_id") or ""), "purchase_order_created",
                    input_data={"approval_id": approval_id},
                    output_data={"purchase_order_id": purchase_order_id, "status": "processing"},
                )
                save_workflow_execution(
                    company_id, str(approval.get("workflow_id") or ""), "workflow_completed",
                    input_data={"purchase_order_id": purchase_order_id},
                    output_data={"status": "completed"},
                )
        except Exception:
            # The approval and business record are already committed. Keep
            # that result authoritative if the optional workflow log fails.
            pass

    if approval and purchase_order_id:
        approval["purchase_order_id"] = purchase_order_id
        approval["workflow_status"] = "completed"
    return approval


def approve_request(
    company_id: str,
    approval_id: int,
    approver_user_id: str,
    reason: str = "",
) -> Optional[Dict[str, Any]]:

    return decide_approval(
        company_id=company_id,
        approval_id=approval_id,
        approver_user_id=approver_user_id,
        decision="approved",
        reason=reason,
    )


def reject_request(
    company_id: str,
    approval_id: int,
    approver_user_id: str,
    reason: str = "",
) -> Optional[Dict[str, Any]]:

    return decide_approval(
        company_id=company_id,
        approval_id=approval_id,
        approver_user_id=approver_user_id,
        decision="rejected",
        reason=reason,
    )


def request_approval_clarification(company_id: str, approval_id: int,
                                   approver_user_id: str, question: str) -> Dict[str, Any]:
    """Pause an approval and notify its requester for required information."""
    from company.store import authorize_user
    actor = authorize_user(company_id, approver_user_id)
    question = str(question or "").strip()
    if not question:
        raise ValueError("Enter the information needed from the requester.")
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM approvals WHERE company_id=? AND approval_id=?", (company_id, int(approval_id))).fetchone()
        if row is None:
            return {"status": "not_found", "message": "Approval was not found."}
        if row["status"] != "pending":
            return {"status": "invalid_state", "message": "Only pending approvals can request clarification."}
        if row["requested_by"] == approver_user_id:
            raise PermissionError("You cannot request clarification on your own request.")
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        area = str(metadata.get("service_area") or metadata.get("department") or "").casefold()
        area_role = {"it": "it_admin", "finance": "finance_admin", "procurement": "procurement_admin", "recruitment": "recruitment_admin", "hr": "hr_admin"}.get(area)
        assigned = str(row["approver_user_id"] or "")
        allowed = str(actor.get("role") or "").casefold() in {"company_admin", "hr_admin", area_role}
        if assigned:
            allowed = allowed or assigned == approver_user_id
        if not allowed:
            raise PermissionError("You are not authorized to request clarification for this approval.")
        conn.execute("UPDATE approvals SET status='needs_clarification',reason=?,decided_at=? WHERE company_id=? AND approval_id=?", (question, now, company_id, int(approval_id)))
        conn.execute("UPDATE department_requests SET status='needs_clarification',decision_reason=?,updated_at=? WHERE company_id=? AND workflow_id=? AND status='pending_approval'", (question, now, company_id, row["workflow_id"]))
        conn.execute("UPDATE leave_requests SET status='needs_clarification',decision_reason=?,updated_at=? WHERE company_id=? AND workflow_id=? AND status='pending_approval'", (question, now, company_id, row["workflow_id"]))
        conn.execute("INSERT INTO notifications(company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (company_id, row["requested_by"], row["workflow_id"], "approval_clarification", "More information requested", question, "approval", str(approval_id), now))
        conn.execute("INSERT INTO audit_logs(company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (company_id, approver_user_id, row["workflow_id"], "approval_clarification_requested", "approval", str(approval_id), json.dumps({"question": question}), now))
    try:
        from company.memory_service import update_workflow_status, save_workflow_execution
        update_workflow_status(company_id, str(row["workflow_id"]), "needs_clarification", {"action": "NEEDS_CLARIFICATION", "approval_id": int(approval_id)})
        save_workflow_execution(company_id, str(row["workflow_id"]), "approval_clarification", input_data={"approval_id": int(approval_id)}, output_data={"question": question, "status": "needs_clarification"})
    except Exception:
        pass
    return {"status": "success", "message": "Clarification request sent to the employee."}


def respond_to_approval_clarification(company_id: str, approval_id: int,
                                      requester_user_id: str, response: str) -> Dict[str, Any]:
    """Record the employee's response and return the same approval to its approver."""
    from company.store import authorize_user
    authorize_user(company_id, requester_user_id)
    response = str(response or "").strip()
    if not response:
        raise ValueError("Enter a response before submitting.")
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM approvals WHERE company_id=? AND approval_id=? AND requested_by=?", (company_id, int(approval_id), requester_user_id)).fetchone()
        if row is None:
            return {"status": "not_found", "message": "Clarification request was not found in your account."}
        if row["status"] != "needs_clarification":
            return {"status": "invalid_state", "message": "This approval is not waiting for your clarification."}
        prior = str(row["reason"] or "")
        combined = f"{prior}\nEmployee response: {response}".strip()
        conn.execute("UPDATE approvals SET status='pending',reason=?,decided_at=NULL WHERE company_id=? AND approval_id=?", (combined, company_id, int(approval_id)))
        conn.execute("UPDATE department_requests SET status='pending_approval',decision_reason=?,updated_at=? WHERE company_id=? AND workflow_id=? AND status='needs_clarification'", (combined, now, company_id, row["workflow_id"]))
        conn.execute("UPDATE leave_requests SET status='pending_approval',decision_reason=?,updated_at=? WHERE company_id=? AND workflow_id=? AND status='needs_clarification'", (combined, now, company_id, row["workflow_id"]))
        metadata = json.loads(row["metadata_json"] or "{}")
        recipients = [str(row["approver_user_id"])] if row["approver_user_id"] else []
        if not recipients:
            area = str(metadata.get("service_area") or metadata.get("department") or "").casefold()
            area_role = {"it": "it_admin", "finance": "finance_admin", "procurement": "procurement_admin", "recruitment": "recruitment_admin", "hr": "hr_admin"}.get(area)
            roles = {"company_admin", "hr_admin"}
            if area_role:
                roles.add(area_role)
            placeholders = ",".join("?" for _ in roles)
            recipients = [str(item[0]) for item in conn.execute(f"SELECT user_id FROM company_users WHERE company_id=? AND status='active' AND role IN ({placeholders})", (company_id, *sorted(roles))).fetchall()]
        for recipient in recipients:
            conn.execute("INSERT INTO notifications(company_id,user_id,workflow_id,notification_type,title,body,resource_type,resource_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (company_id, recipient, row["workflow_id"], "approval_clarification_response", "Clarification received", f"The employee responded to approval #{approval_id}.", "approval", str(approval_id), now))
        conn.execute("INSERT INTO audit_logs(company_id,user_id,workflow_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (company_id, requester_user_id, row["workflow_id"], "approval_clarification_answered", "approval", str(approval_id), json.dumps({"response": response}), now))
    try:
        from company.memory_service import update_workflow_status, save_workflow_execution
        update_workflow_status(company_id, str(row["workflow_id"]), "pending_approval", {"action": "CLARIFICATION_RECEIVED", "approval_id": int(approval_id)})
        save_workflow_execution(company_id, str(row["workflow_id"]), "approval_clarification_response", input_data={"approval_id": int(approval_id)}, output_data={"response": response, "status": "pending_approval"})
    except Exception:
        pass
    return {"status": "success", "message": "Your response was sent and the approval is pending review again."}
