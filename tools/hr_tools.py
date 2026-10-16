"""Tenant-scoped HR tools backed by configured company data."""

from datetime import datetime


# ============================================================
# HELPERS
# ============================================================

def _get_text(details, message):
    """
    Safely combine details and original user message into searchable text.
    """
    parts = []

    if isinstance(message, str):
        parts.append(message)

    if isinstance(details, dict):
        important = details.get("important")

        if isinstance(important, dict):
            for value in important.values():
                if value is not None:
                    parts.append(str(value))
        elif important is not None:
            parts.append(str(important))

        for key, value in details.items():
            if key != "important" and value is not None:
                parts.append(str(value))

    return " ".join(parts).lower()


def _extract_employee_id(details, message):
    """Resolve the authenticated employee and enforce cross-employee access rules."""
    details = details if isinstance(details, dict) else {}
    from company.store import authorize_user

    company_id = str(details.get("company_id") or "").strip()
    user_id = str(details.get("user_id") or "").strip()
    user = authorize_user(company_id, user_id)

    own_id = str(user.get("employee_id") or "").strip()
    role = str(user.get("role") or "").casefold()
    is_admin = role in {"hr_admin", "company_admin"}

    import re
    explicit_match = re.search(
        r"\bEMP[A-Z0-9-]+\b",
        str(message or ""),
        re.IGNORECASE,
    )
    explicit_id = explicit_match.group(0).upper() if explicit_match else ""

    if not is_admin:
        # Never trust an AI-extracted employee ID over the authenticated identity.
        # Explicit requests for another employee remain forbidden.
        if explicit_id and explicit_id.casefold() != own_id.casefold():
            return "__forbidden__"
        return own_id or None

    # HR/admin can inspect another employee only if they belong to this company.
    requested = explicit_id or str(details.get("employee_id") or "").strip()
    if not requested or requested.casefold() == own_id.casefold():
        return own_id or None

    from company.store import _connect
    conn = _connect()
    try:
        found = conn.execute(
            "SELECT 1 FROM company_users WHERE company_id = ? AND employee_id = ?",
            (company_id, requested),
        ).fetchone()
    finally:
        conn.close()

    return requested if found else None


def _base_result(action, message, request_type):
    return {
        "status": "success",
        "action": action,
        "message": message,
        "request_type": request_type,
        "executed": True,
    }


# ============================================================
# EMPLOYEE INFORMATION
# ============================================================

# ============================================================
# EMPLOYEE INFORMATION
# ============================================================

def employee_information(details, message):
    """
    Retrieve employee information from the tenant-scoped
    employee_profiles table.

    Priority:
    1. Explicit employee_id
    2. Logged-in user's employee_id
    3. Deny if no employee can be resolved

    Employees can only retrieve their own profile.
    Authorized admin roles may retrieve other employee profiles.
    """

    details = details if isinstance(details, dict) else {}

    company_id = str(
        details.get("company_id") or ""
    ).strip()

    user_id = str(
        details.get("user_id") or ""
    ).strip()

    user_role = "employee"

    requested_employee_id = str(
        details.get("employee_id") or ""
    ).strip()

    if not company_id:
        return _base_result(
            "Employee information service",
            "Company context is required to retrieve employee information.",
            "employee_information",
        )

    try:
        from company.store import authorize_user
        authenticated_user = authorize_user(company_id, user_id)
        user_role = str(authenticated_user.get("role") or "employee").strip().lower()
        from company.employee_service import (
            get_employee_id,
            get_employee_profile,
        )

        # ----------------------------------------------------
        # RESOLVE LOGGED-IN EMPLOYEE
        # ----------------------------------------------------

        current_employee_id = get_employee_id(
            company_id,
            user_id,
        )

        # ----------------------------------------------------
        # DETERMINE TARGET EMPLOYEE
        # ----------------------------------------------------

        target_employee_id = (
            requested_employee_id
            or current_employee_id
        )

        if not target_employee_id:
            return _base_result(
                "Employee information service",
                (
                    "I could not determine the employee record. "
                    "Please provide a valid employee ID such as EMP1001."
                ),
                "employee_information",
            )

        # ----------------------------------------------------
        # EMPLOYEE SELF-SERVICE SECURITY
        # ----------------------------------------------------

        admin_roles = {
            "company_admin",
            "hr_admin",
        }

        if (
            user_role == "employee"
            and current_employee_id
            and target_employee_id != current_employee_id
        ):
            return _base_result(
                "Employee information service",
                "You are only authorized to view your own employee information.",
                "employee_information",
            )

        # ----------------------------------------------------
        # GET REAL EMPLOYEE PROFILE FROM DATABASE
        # ----------------------------------------------------

        employee = get_employee_profile(
            employee_id=target_employee_id,
            company_id=company_id,
        )

        if not employee:
            return _base_result(
                "Employee information service",
                (
                    f"No employee profile was found for "
                    f"{target_employee_id}."
                ),
                "employee_information",
            )

        # ----------------------------------------------------
        # BUILD DATABASE-BASED RESULT
        # ----------------------------------------------------

        employee_data = {
            "employee_id": employee.get(
                "employee_id"
            ),
            "name": employee.get(
                "full_name"
            ),
            "email": employee.get(
                "email"
            ),
            "phone": employee.get(
                "phone"
            ),
            "department": employee.get(
                "department"
            ),
            "job_title": employee.get(
                "job_title"
            ),
            "role": employee.get(
                "role_name"
            ),
            "manager_employee_id": employee.get(
                "manager_employee_id"
            ),
            "joining_date": employee.get(
                "joining_date"
            ),
            "employment_status": employee.get(
                "employment_status"
            ),
            "location": employee.get(
                "location"
            ),
            "date_of_birth": employee.get(
                "date_of_birth"
            ),
            "leave_entitlement_days": employee.get(
                "leave_entitlement_days"
            ),
            "leave_balance_days": employee.get(
                "leave_balance_days"
            ),
        }

        # Remove empty values so the response contains
        # only information actually stored in the database.
        employee_data = {
            key: value
            for key, value in employee_data.items()
            if value not in (
                None,
                "",
            )
        }

        result = _base_result(
            "Employee information lookup",
            (
                f"Employee record for "
                f"{employee_data.get('name', target_employee_id)} "
                "was retrieved successfully."
            ),
            "employee_information",
        )

        result["employee"] = employee_data

        return result

    except Exception as exc:
        return _base_result(
            "Employee information service",
            f"Unable to retrieve employee information: {exc}",
            "employee_information",
        )


# ============================================================
# ATTENDANCE SERVICE
# ============================================================

def attendance_service(details, message):
    details = details if isinstance(details, dict) else {}
    from company.store import authorize_user
    try:
        authorize_user(str(details.get("company_id") or ""), str(details.get("user_id") or ""))
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}
    return {"status": "not_configured", "executed": False, "message": "Attendance records are not connected for this company, so I cannot report attendance values."}


# ============================================================
# BENEFITS SERVICE
# ============================================================

def benefits_service(details, message):
    details = details if isinstance(details, dict) else {}
    from company.store import authorize_user, get_company_context
    company_id, user_id = str(details.get("company_id") or ""), str(details.get("user_id") or "")
    try:
        authorize_user(company_id, user_id)
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}
    context = get_company_context(company_id) or {}
    benefits = context.get("benefits", {}) if isinstance(context, dict) else {}
    text = _get_text(details, message)

    # --------------------------------------------------------
    # Information request
    # --------------------------------------------------------

    information_words = (
        "what benefits", "benefits available", "available benefits",
        "employee benefits", "what insurance", "health benefits",
        "benefits information", "list of benefits", "insurance options",
        "health insurance options", "benefits does the company offer",
    )
    enrollment_terms = ("enroll", "enrollment", "sign up", "add me", "add my family", "change my benefits", "apply for benefits")
    is_enrollment_request = any(term in text for term in enrollment_terms)
    is_information_question = (
        text.rstrip().endswith("?")
        or text.startswith(("what ", "which ", "do we have ", "does our company ", "are ", "is ", "tell me about ", "show me "))
    )
    is_information_request = not is_enrollment_request and (
        any(phrase in text for phrase in information_words) or is_information_question
    )

    if is_information_request:
        if not benefits:
            return {"status": "not_configured", "executed": False, "message": "No company benefits catalog is configured."}
        result = _base_result(
            "Benefits information",
            "The available employee benefits were retrieved from the HR benefits service.",
            "information",
        )

        result["benefits"] = benefits

        return result

    # --------------------------------------------------------
    # Application / enrollment
    # --------------------------------------------------------

    benefit_type = str(details.get("benefit_type") or details.get("service_request_type") or "health")
    if isinstance(details, dict):
        important = details.get("important")
        if isinstance(important, dict):
            benefit_type = str(important.get("benefit_type") or important.get("benefit") or benefit_type)
    title = str(details.get("service_request_title") or f"{benefit_type.replace('_', ' ').title()} benefits enrollment")

    from company.request_service import create_department_request
    result = create_department_request(
        company_id=company_id, user_id=user_id,
        workflow_id=str(details.get("workflow_id") or ""), service_area="HR",
        request_type=str(details.get("service_request_type") or "benefit_enrollment"),
        title=title, description=str(message or ""),
        details={
            "benefit_type": benefit_type,
            "category": str(details.get("service_request_type") or "benefit_enrollment"),
            "service_request_type": str(details.get("service_request_type") or "benefit_enrollment"),
            "eligibility_verification_required": True,
            "benefits_catalog_configured": bool(benefits),
            "needs_external_integration": True,
            "processing_note": "Enrollment request recorded for HR review; benefits have not been activated automatically.",
        }, requires_approval=True,
    )
    result["tool"] = "benefits_service"
    if result.get("status") == "success":
        result["message"] += " Eligibility review and any required provider integration are still pending."
    return result


# ============================================================
# LEAVE MANAGEMENT
# ============================================================


# ============================================================
# LEAVE MANAGEMENT
# ============================================================

def leave_management(details, message):
    """Handle leave balance, history, status, and leave applications."""
    import re

    details = details if isinstance(details, dict) else {}
    company_id = str(details.get("company_id") or "").strip()
    user_id = str(details.get("user_id") or "").strip()
    if not company_id or not user_id:
        return {
            "status": "error",
            "executed": False,
            "tool": "leave_management",
            "message": "Authenticated company and employee context are required.",
        }

    from company.leave_service import (
        get_leave_summary,
        create_leave_request,
        get_my_leave_request,
    )

    raw_message = str(message or "")
    text = raw_message.casefold()

    # Read-only history queries must never be classified as leave applications.
    read_only_history = (
        bool(re.search(
            r"\b(show|list|display|view|retrieve|get|check|find)\b", text
        ))
        and bool(re.search(r"\b(my|all|existing|previous|past)\b", text))
        and bool(re.search(
            r"\b(leave requests?|leave records?|request history|"
            r"approval statuses?|hr requests?)\b",
            text,
        ))
    )

    # Recognize direct leave intentions, including "I want leave",
    # so a confirmed multi-turn application is not mistaken for a balance query.
    negative_action = bool(re.search(
        r"\b(?:don't|dont|do not|never)\b.{0,80}\b(?:want|need|apply|request|take|book|schedule)\b",
        text,
    ))

    action_request = (not read_only_history) and (not negative_action) and bool(
        details.get("_confirmed_action")
        or re.search(r"\b(?:create|start|make)\b.{0,35}\b(?:leave|vacation|time off)\b", text)
        or re.search(r"\b(?:leave|vacation|time off)\s+request\b", text)
        or re.search(r"\b(apply for|submit|book|take|cancel|schedule)\b", text)
        or re.search(
            r"\b(?:want|need|would like|i'd like)\s+to\s+"
            r"(?:apply for|request|take|book|schedule)\b",
            text,
        )
        or re.search(
            r"\b(?:i\s+)?(?:want|need|would like)\s+"
            r"(?:to\s+)?(?:take\s+)?(?:annual|casual|sick|personal|earned|paid|unpaid\s+)?"
            r"(?:leave|time off)\b",
            text,
        )
        or re.search(
            r"\brequest\s+(?:leave|time off|a day off|"
            r"(?:a|one|two|single)\s+(?:day|days)\s+of\s+leave)\b",
            text,
        )
    )

    summary = get_leave_summary(company_id, user_id)

    # Information requests: balance, leave types, history, or request status.
    if not action_request:
        if summary.get("status") != "success":
            return {**summary, "tool": "leave_management", "executed": False}

        requests = summary.get("requests", [])
        if read_only_history or any(
            word in text for word in ("history", "previous", "past leave", "leave records")
        ):
            return {
                "status": "success", "tool": "leave_management", "executed": False,
                "records": requests,
                "message": f"Retrieved {len(requests)} leave request(s) from your employee record.",
            }

        if any(word in text for word in (
            "status", "approved", "rejected", "pending", "who has to approve", "approver"
        )):
            request_id_match = re.search(r"\bLV-[A-Z0-9-]+\b", raw_message, re.IGNORECASE)
            if request_id_match:
                record = get_my_leave_request(
                    company_id, user_id, request_id_match.group(0).upper()
                )
                if not record:
                    return {
                        "status": "not_found", "tool": "leave_management", "executed": False,
                        "message": "That leave request was not found in your account.",
                    }
            else:
                pending = [row for row in requests if row.get("status") in {"pending_approval", "pending"}]
                record = pending[0] if pending else (requests[0] if requests else None)
                if not record:
                    return {
                        "status": "no_result", "tool": "leave_management", "executed": False,
                        "message": "No leave requests were found in your history.",
                    }
            status_text = str(record.get("status") or "unknown").replace("_", " ")
            return {
                "status": "success", "tool": "leave_management", "executed": False,
                "record": record,
                "message": f"Leave request {record.get('leave_request_id')} is {status_text}.",
            }

        balance = summary.get("leave_balance", 0)
        entitlement = summary.get("leave_entitlement", 0)
        return {
            "status": "success", "tool": "leave_management", "executed": False,
            "leave_balance": balance,
            "leave_entitlement": entitlement,
            "leave_types": summary.get("leave_types", []),
            "message": f"Your current leave balance is {float(balance):g} day(s) out of {float(entitlement):g} entitled day(s).",
        }

    important = details.get("important", {})
    if not isinstance(important, dict):
        important = {}

    start_date = important.get("start_date") or details.get("start_date")
    end_date = important.get("end_date") or details.get("end_date")
    leave_type = important.get("leave_type") or details.get("leave_type") or ""
    reason = str(important.get("reason") or details.get("reason") or "").strip()

        # Extract the latest answer supplied during clarification.
    if not reason:
        matches = re.findall(
            r"Additional information:\s*(.+)",
            raw_message,
            re.IGNORECASE,
        )
        for answer in reversed(matches):
            answer = answer.strip()
            if not answer:
                continue
            # Do not mistake a date-only answer for a leave reason.
            if re.fullmatch(
                r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
                answer,
            ):
                continue
            reason = answer
            break

    # Accept an explicit purpose/reason from the employee's message.
    if not reason:
        match = re.search(
            r"\b(?:reason|purpose)\s*[:=-]\s*(.+?)(?:[.!?]|$)",
            raw_message, re.IGNORECASE,
        )
        if match:
            reason = match.group(1).strip()

    # Recognize a short purpose after the date sentence, e.g. "2026. Personal."
    if not reason:
        match = re.search(
            r"\b20\d{2}\s*[.!?]\s*([A-Za-z][A-Za-z ]{2,60})[.!?]?\s*$",
            raw_message,
        )
        if match:
            reason = match.group(1).strip()

    # Recognize natural-language purposes such as "for personal reasons".
    if not reason:
        match = re.search(
            r"\bfor\s+(?:my\s+)?((?:personal|medical|health|family|emergency|vacation|wedding)\s+(?:reasons?|leave|purposes?|function|functions|event|events|work|matter|matters))\b",
            raw_message,
            re.IGNORECASE,
        )
        if match:
            reason = match.group(1).strip()

    if not start_date or not end_date:
        return {
            "status": "missing_information", "executed": False,
            "tool": "leave_management",
            "message": "Please provide both a start date and an end date before I submit a leave request.",
        }
    if not reason:
        return {
            "status": "missing_information", "executed": False,
            "tool": "leave_management",
            "message": "What is the purpose of your leave?",
        }

    requested_days = (
        important.get("number_of_days") or important.get("days")
        or details.get("number_of_days") or details.get("days")
    )
    result = create_leave_request(
        company_id=company_id,
        user_id=user_id,
        workflow_id=str(details.get("workflow_id") or ""),
        start_date=str(start_date),
        end_date=str(end_date),
        leave_type=str(leave_type),
        reason=reason,
        requested_days=requested_days,
    )
    if isinstance(result, dict):
        result.setdefault("tool", "leave_management")
    return result


# HR POLICY SERVICE
# ============================================================

def hr_policy_service(details, message):
    """
    Read the latest company policy data supplied through tenant context.

    This is an information-only service. It does not submit or modify
    employee requests such as leave applications.
    """

    # ------------------------------------------------------------
    # GET COMPANY CONTEXT
    # ------------------------------------------------------------
    company_context = {}

    if isinstance(details, dict):
        company_context = details.get("company_context", {})

    # Support both:
    # {"departments": ..., "policies": ...}
    # and:
    # {"context": {"departments": ..., "policies": ...}}
    if (
        isinstance(company_context, dict)
        and isinstance(company_context.get("context"), dict)
    ):
        company_context = company_context["context"]

    if not isinstance(company_context, dict):
        company_context = {}

    policies = company_context.get("policies", {})
    approval_rules = company_context.get("approval_rules", {})
    benefits = company_context.get("benefits", {})

    if not isinstance(policies, dict):
        policies = {}

    if not isinstance(approval_rules, dict):
        approval_rules = {}

    if not isinstance(benefits, dict):
        benefits = {}

    if not policies and not approval_rules and not benefits:
        return {"status": "not_configured", "executed": False, "message": "No HR policies are configured for this company."}

    # ------------------------------------------------------------
    # IDENTIFY POLICY TOPIC
    # ------------------------------------------------------------
    text = str(message or "").lower()

    # ------------------------------------------------------------
    # LAPTOP / IT PURCHASE POLICY
    # ------------------------------------------------------------
    if "laptop" in text or "computer" in text or "device" in text:
        laptop_budget = policies.get("laptop_budget_inr")
        purchase_limit = approval_rules.get("purchase_above_inr")

        if laptop_budget is None:
            return _base_result(
                "HR policy service",
                (
                    "No laptop budget policy is currently configured "
                    "for this company."
                ),
                "policy_information",
            )

        result = _base_result(
            "HR policy service",
            (
                f"The current company laptop budget policy is "
                f"₹{float(laptop_budget):,.0f} per laptop."
            ),
            "policy_information",
        )

        result["policy_name"] = "Laptop Budget Policy"
        result["laptop_budget_inr"] = laptop_budget

        if purchase_limit is not None:
            result["purchase_approval_threshold_inr"] = purchase_limit
            result["approval_rule"] = (
                f"Purchases above ₹{float(purchase_limit):,.0f} "
                "require approval."
            )

        result["source"] = "company_context"

        return result

    # ------------------------------------------------------------
    # LEAVE POLICY INFORMATION
    # ------------------------------------------------------------
    if "leave" in text or "holiday" in text or "time off" in text:
        leave_policy = policies.get("leave", {})

        if not isinstance(leave_policy, dict):
            leave_policy = {}

        annual_leave = leave_policy.get("annual_leave_days")
        manager_approval = leave_policy.get("manager_approval_required")

        message_parts = []

        if annual_leave is not None:
            message_parts.append(
                f"The current annual leave allowance is "
                f"{annual_leave} days."
            )

        if manager_approval is not None:
            if manager_approval:
                message_parts.append(
                    "Manager approval is required for leave requests."
                )
            else:
                message_parts.append(
                    "Manager approval is not required for leave requests."
                )

        if not message_parts:
            message_parts.append(
                "No leave policy details are currently configured "
                "for this company."
            )

        result = _base_result(
            "HR policy service",
            " ".join(message_parts),
            "policy_information",
        )

        result["policy_name"] = "Leave Policy"
        result["leave_policy"] = leave_policy
        result["source"] = "company_context"

        return result

    # ------------------------------------------------------------
    # GENERIC HR POLICY REQUEST
    # ------------------------------------------------------------
    result = _base_result(
        "HR policy service",
        (
            "The current company HR policy information was retrieved "
            "from the configured company workspace."
        ),
        "policy_information",
    )

    result["policies"] = policies
    result["approval_rules"] = approval_rules
    result["benefits"] = benefits
    result["source"] = "company_context"

    return result


# ============================================================
# EMPLOYEE DOCUMENT SERVICE
# ============================================================

def employee_document_service(details, message):
    details = details if isinstance(details, dict) else {}
    from company.store import authorize_user
    from company.request_service import create_department_request
    company_id, user_id = str(details.get("company_id") or ""), str(details.get("user_id") or "")
    try:
        authorize_user(company_id, user_id)
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}
    document_type = str(details.get("document_type") or details.get("document") or "Employment document").strip()
    result = create_department_request(company_id=company_id, user_id=user_id, workflow_id=str(details.get("workflow_id") or ""), service_area="HR", request_type="employee_document", title=document_type, description=str(message or ""), details={"document_type": document_type}, requires_approval=True)
    result["tool"] = "employee_document_service"
    return result


# ============================================================
# ONBOARDING SERVICE
# ============================================================

def onboarding_service(details, message):
    details = details if isinstance(details, dict) else {}
    from company.store import authorize_user
    try:
        authorize_user(str(details.get("company_id") or ""), str(details.get("user_id") or ""))
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}
    return {"status": "not_configured", "executed": False, "message": "No onboarding workflow records are configured for this company."}


# ============================================================
# PERFORMANCE SERVICE
# ============================================================

def performance_service(details, message):
    """
    Retrieve the authenticated employee's performance record
    from the company database.
    """

    details = details or {}

    try:
        employee_id = _extract_employee_id(details, message)
    except PermissionError as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}

    if employee_id == "__forbidden__":
        return {"status": "permission_denied", "executed": False, "message": "You can only access your own performance record."}

    if not employee_id:
        return _base_result(
            "Performance service",
            (
                "An employee ID is required to retrieve "
                "a specific performance record."
            ),
            "performance_request",
        )

    company_id = str(
        details.get("company_id") or ""
    ).strip()

    if not company_id:
        return _base_result(
            "Performance service",
            (
                "A company ID is required to retrieve "
                "company-scoped performance data."
            ),
            "performance_request",
        )

    # --------------------------------------------------------
    # Determine requested review period.
    # "last month" -> previous calendar month.
    # --------------------------------------------------------

    search_text = str(
        message or ""
    ).lower()

    review_period = (
        details.get("review_period")
        or details.get("performance_period")
    )

    if not review_period:
        important = details.get(
            "important",
            {},
        )

        if isinstance(important, dict):
            review_period = (
                important.get("review_period")
                or important.get("performance_period")
            )

    if not review_period and "last month" in search_text:
        from datetime import datetime

        current = datetime.now()

        if current.month == 1:
            year = current.year - 1
            month = 12
        else:
            year = current.year
            month = current.month - 1

        review_period = (
            datetime(
                year,
                month,
                1,
            ).strftime("%B %Y")
        )

    # --------------------------------------------------------
    # Read authoritative performance record from DB.
    # --------------------------------------------------------

    try:
        import sqlite3
        from company.store import DB_PATH, authorize_user
        actor = authorize_user(company_id, str(details.get("user_id") or ""))
        if employee_id != str(actor.get("employee_id") or "") and str(actor.get("role") or "").casefold() not in {"hr_admin", "company_admin"}:
            return {"status": "permission_denied", "executed": False, "message": "You can only access your own performance record."}
        db_path = DB_PATH

        with sqlite3.connect(
            str(db_path)
        ) as conn:

            conn.row_factory = sqlite3.Row

            if review_period:

                row = conn.execute(
                    """
                    SELECT
                        performance_id,
                        employee_id,
                        review_period,
                        rating,
                        goals,
                        achievements_summary,
                        manager_feedback,
                        status
                    FROM employee_performance
                    WHERE company_id = ?
                      AND employee_id = ?
                      AND review_period = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (
                        company_id,
                        employee_id,
                        str(review_period).strip(),
                    ),
                ).fetchone()

            else:

                row = conn.execute(
                    """
                    SELECT
                        performance_id,
                        employee_id,
                        review_period,
                        rating,
                        goals,
                        achievements_summary,
                        manager_feedback,
                        status
                    FROM employee_performance
                    WHERE company_id = ?
                      AND employee_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (
                        company_id,
                        employee_id,
                    ),
                ).fetchone()

    except Exception as exc:

        result = _base_result(
            "Performance service",
            (
                "Performance data could not be retrieved "
                "from the employee database."
            ),
            "performance_request",
        )

        result["status"] = "error"
        result["error"] = str(exc)
        result["employee_id"] = employee_id

        return result

    # --------------------------------------------------------
    # No performance record.
    # --------------------------------------------------------

    if not row:

        result = _base_result(
            "Performance service",
            (
                f"No performance record was found for "
                f"{employee_id}"
                + (
                    f" for {review_period}."
                    if review_period
                    else "."
                )
            ),
            "performance_request",
        )

        result["status"] = "no_result"
        result["employee_id"] = employee_id

        if review_period:
            result["review_period"] = (
                str(review_period)
            )

        return result

    # --------------------------------------------------------
    # Return actual performance details.
    # --------------------------------------------------------

    result = _base_result(
        "Performance service",
        (
            f"Performance record retrieved for "
            f"{employee_id}."
        ),
        "performance_request",
    )

    result["employee_id"] = row["employee_id"]
    result["review_period"] = row["review_period"]
    result["rating"] = row["rating"]
    result["goals"] = row["goals"]
    result["achievements_summary"] = (
        row["achievements_summary"]
    )
    result["manager_feedback"] = (
        row["manager_feedback"]
    )
    result["performance_status"] = (
        row["status"]
    )

    return result
# ============================================================
# HR EMPLOYEE SERVICES
# ============================================================

def _submit_hr_service(details, message, request_type, title):
    """Submit a tenant-scoped HR service request for admin review.

    Specialized categories are selected by the server-side service catalogue.
    They are stored as first-class department requests and remain auditable.
    """
    details = details if isinstance(details, dict) else {}

    from company.store import authorize_user
    from company.request_service import create_department_request
    from core.service_catalog import HR_REQUEST_CATEGORIES

    company_id = str(details.get("company_id") or "").strip()
    user_id = str(details.get("user_id") or "").strip()

    try:
        authorize_user(company_id, user_id)
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}

    description = str(message or "").strip()
    if not description:
        return {
            "status": "missing_information", "executed": False,
            "message": "Please describe your HR request before submitting it.",
        }

    requested_type = str(details.get("service_request_type") or "").strip().casefold()
    # Accept catalog-defined types and safe generic future types. Previously an
    # unrecognized type cleared the variable but left request_type undefined,
    # causing an exception instead of recording a tracked HR request.
    import re
    requested_type = re.sub(r"[^a-z0-9_]+", "_", requested_type).strip("_")[:60]
    if not requested_type:
        requested_type = "generic_hr_request"
    request_type = requested_type
    configured_title = HR_REQUEST_CATEGORIES.get(requested_type)
    supplied_title = str(details.get("service_request_title") or "").strip()
    title = configured_title or supplied_title or request_type.replace("_", " ").title()

    metadata = {
        "category": request_type,
        "service_request_type": request_type,
        "needs_external_integration": bool(details.get("service_request_needs_external_integration")),
        "processing_note": (
            "Request recorded for authorized HR processing. Any external-system action "
            "must be completed by an authorized operator or configured integration."
        ),
    }
    if details.get("service_request_confidential") or requested_type == "whistleblower_ethics":
        metadata["confidential"] = True
        metadata["visibility"] = "hr_authorized_staff"
    if details.get("service_request_priority"):
        metadata["priority"] = str(details.get("service_request_priority"))[:20]

    result = create_department_request(
        company_id=company_id,
        user_id=user_id,
        workflow_id=str(details.get("workflow_id") or ""),
        service_area="HR",
        request_type=request_type,
        title=str(title or "HR service request")[:200],
        description=description,
        details=metadata,
        requires_approval=True,
    )
    result["tool"] = request_type + "_service"
    if requested_type and result.get("status") == "success":
        result["message"] += " HR approval and any required specialist integration are still pending."
    if requested_type == "whistleblower_ethics" and result.get("status") == "success":
        result["message"] += " This is marked confidential for authorized HR review; the current portal does not provide anonymous submission."
    return result


def hr_grievance_service(details, message):
    return _submit_hr_service(
        details, message, "hr_grievance", "Employee grievance"
    )


def hr_training_service(details, message):
    return _submit_hr_service(
        details, message, "hr_training", "Employee training request"
    )


def hr_general_request_service(details, message):
    """Read existing HR history for queries; submit only genuine new requests."""
    import re

    details = details if isinstance(details, dict) else {}
    text = str(message or "").casefold()

    read_only_history = (
        bool(re.search(
            r"\b(?:show|list|display|view|retrieve|get|check|find)\b", text
        ))
        and bool(re.search(r"\b(?:hr\s+)?requests?\b", text))
        and bool(re.search(
            r"\b(?:history|status|approval|approved|rejected|pending|records?)\b",
            text,
        ))
        and (
            not bool(re.search(
                r"\b(?:submit|create|raise|open|file|apply for|modify|change|update|cancel|approve|delete)\b",
                text,
            ))
            or bool(re.search(
                r"\b(?:do not|don't|dont|never)\b.{0,120}\b(?:submit|create|raise|open|file|apply|modify|change|update|cancel|approve|delete)\b",
                text,
            ))
        )
    )

    if read_only_history:
        company_id = str(details.get("company_id") or "").strip()
        user_id = str(details.get("user_id") or "").strip()

        if not company_id or not user_id:
            return {
                "status": "error",
                "executed": False,
                "tool": "hr_general_request_service",
                "message": "Authenticated company and employee context are required.",
            }

        from company.employee_service import get_user_service_history

        records = get_user_service_history(
            company_id=company_id,
            user_id=user_id,
            service_area="HR",
            limit=100,
        )

        # Display actual request records, not tool-execution activity logs.
        records = [
            row for row in records
            if str(row.get("request_id") or "").strip()
        ]

        return {
            "status": "success",
            "executed": False,
            "tool": "hr_general_request_service",
            "records": records,
            "record_count": len(records),
            "message": (
                f"Retrieved {len(records)} existing HR service record(s)."
                if records
                else "No existing HR service records were found for your account."
            ),
        }

    return _submit_hr_service(
        details, message, "hr_general_request", "General HR request"
    )


