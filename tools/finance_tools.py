from typing import Any, Dict

import re
from company.store import authorize_user, get_company_context
from company.request_service import create_department_request, list_my_department_requests, get_my_department_request


def budget_service(details: Dict[str, Any], message: str):
    """
    Company-aware finance budget service.

    Uses the latest tenant/company context when available.
    """

    details = details if isinstance(details, dict) else {}
    message = str(message or "")
    company_id = str(details.get("company_id") or "")
    user_id = str(details.get("user_id") or "")
    try:
        authorize_user(company_id, user_id)
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}

    # ------------------------------------------------------------
    # COMPANY CONTEXT
    # ------------------------------------------------------------
    company_context = get_company_context(company_id) or {}

    if (
        isinstance(company_context, dict)
        and isinstance(company_context.get("context"), dict)
    ):
        company_context = company_context["context"]

    if not isinstance(company_context, dict):
        company_context = {}

    policies = company_context.get("policies", {})

    if not isinstance(policies, dict):
        policies = {}

    # ------------------------------------------------------------
    # TENANT-SPECIFIC FINANCE BUDGET
    # ------------------------------------------------------------
    available_budget = policies.get("finance_available_budget_inr")

    if available_budget is None:
        return {
            "status": "not_configured",
            "executed": False,
            "tool": "budget_service",
            "message": "Your company has not configured a finance budget, so I cannot verify available funds.",
        }

    approval_limit = policies.get("finance_approval_limit_inr")

    currency = policies.get("finance_currency")
    if not currency:
        return {"status": "not_configured", "executed": False, "tool": "budget_service", "message": "The company finance currency is not configured, so I cannot report budget values."}

    try:
        available_budget = float(available_budget)
    except (TypeError, ValueError):
        return {"status": "invalid_policy", "executed": False, "tool": "budget_service", "message": "The company finance budget configuration is invalid."}

    try:
        approval_limit = float(approval_limit) if approval_limit is not None else None
    except (TypeError, ValueError):
        approval_limit = None

    # ------------------------------------------------------------
    # REQUESTED AMOUNT
    # ------------------------------------------------------------
    amount = details.get("amount")

    if amount is not None:
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"status": "invalid", "executed": False, "tool": "budget_service", "message": "The requested amount is invalid."}

    # ------------------------------------------------------------
    # INFORMATION REQUEST:
    # "What is the available finance budget?"
    # ------------------------------------------------------------
    if amount is None:
        return {
            "status": "success",
            "action": "Budget availability check",
            "available_budget": available_budget,
            "currency": currency,
            "budget_configured": True,
            "message": (
                f"The current available finance budget is "
                f"{currency} {available_budget:,.0f}."
            ),
            "executed": True,
            "tool": "budget_service",
            "source": "company_context",
        }

    # ------------------------------------------------------------
    # ACTUAL BUDGET CHECK
    # ------------------------------------------------------------
    within_budget = amount <= available_budget
    requires_approval = True if approval_limit is None else amount > approval_limit

    return {
        "status": "success",
        "action": "Budget check",
        "requested_amount": amount,
        "available_budget": available_budget,
        "currency": currency,
        "within_budget": within_budget,
        "requires_approval": requires_approval,
        "approval_limit": approval_limit,
        "message": (
            "Request is within the available budget."
            if within_budget
            else "Request exceeds the available budget."
        ),
        "executed": True,
        "tool": "budget_service",
        "source": "company_context",
    }


def expense_service(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    company_id = str(details.get("company_id") or "")
    user_id = str(details.get("user_id") or "")
    try:
        authorize_user(company_id, user_id)
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}
    text = str(message or "").strip()
    match = re.search(r"\b(?:FIN|EXP)-[A-Z0-9-]+\b", text, re.IGNORECASE)
    if match and not any(word in text.lower() for word in ("submit", "create", "file", "claim")):
        record = get_my_department_request(company_id, user_id, match.group(0))
        if not record or record.get("service_area") != "Finance":
            return {"status": "not_found", "executed": False, "message": "That finance request was not found in your account."}
        return {"status": "success", "executed": False, "record": record, "message": f"Finance request {record['request_id']} is {record['status'].replace('_', ' ')}."}
    if any(word in text.lower() for word in ("status", "history", "previous", "my expenses", "my reimbursements")) and not any(word in text.lower() for word in ("submit", "create", "file", "claim")):
        records = list_my_department_requests(company_id, user_id, "Finance")
        return {"status": "success" if records else "no_result", "executed": False, "records": records, "message": f"Retrieved {len(records)} finance request(s) from your account." if records else "No finance requests were found in your account."}
    raw_amount = details.get("amount") or details.get("amount_inr")
    if raw_amount is None:
        match = re.search(r"(?:₹|\binr\s*)\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
        raw_amount = match.group(1).replace(",", "") if match else None
    if raw_amount is None:
        return {"status": "missing_information", "executed": False, "message": "Please include the expense amount before submitting a reimbursement request."}
    currency = str(details.get("currency") or ("INR" if "₹" in text or re.search(r"\binr\b", text, re.IGNORECASE) else "")).strip().upper()
    if currency != "INR":
        return {"status": "missing_information", "executed": False, "message": "Please provide the amount in INR so it can be checked against your company's configured approval policy."}
    important = details.get("important", {})
    if not isinstance(important, dict):
        important = {}
    context = get_company_context(company_id)
    policies = context.get("policies", {}) if isinstance(context, dict) else {}
    limit = policies.get("finance_approval_limit_inr") if isinstance(policies, dict) else None
    try:
        requires_approval = True if limit is None else float(raw_amount) >= float(limit)
    except (TypeError, ValueError):
        return {"status": "invalid", "executed": False, "message": "The expense amount or company approval threshold is invalid."}
    result = create_department_request(
        company_id=company_id, user_id=user_id, workflow_id=str(details.get("workflow_id") or ""),
        service_area="Finance", request_type="expense_reimbursement",
        title=str(important.get("merchant") or details.get("merchant") or "Expense reimbursement"),
        description=str(important.get("description") or text), amount=raw_amount,
        currency=currency,
        details={"expense_date": important.get("expense_date") or details.get("expense_date"), "category": important.get("category") or details.get("category"), "receipt_reference": important.get("receipt_reference") or details.get("receipt_reference")},
        requires_approval=requires_approval,
    )
    if result.get("status") == "success":
        result["tool"] = "expense_service"
    return result


def invoice_service(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    try:
        authorize_user(str(details.get("company_id") or ""), str(details.get("user_id") or ""))
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}
    return {"status": "not_configured", "executed": False, "message": "Invoice records are not configured for this company; no invoice status is available."}


def payment_service(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    try:
        authorize_user(str(details.get("company_id") or ""), str(details.get("user_id") or ""))
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc)}
    return {"status": "not_configured", "executed": False, "message": "Payment records are not configured for this company; no payment status is available."}


def payroll_service(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    try:
        user = authorize_user(str(details.get("company_id") or ""), str(details.get("user_id") or ""))
    except PermissionError:
        return {"status": "error", "executed": False, "message": "Authenticated company and user context are required."}
    if str(user.get("role", "")).lower() not in {"finance_admin", "company_admin"}:
        return {"status": "permission_denied", "executed": False, "message": "Payroll information is restricted to authorized Finance administrators."}
    return {"status": "not_configured", "executed": False, "message": "Payroll records are not configured for this company."}
