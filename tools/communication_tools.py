from __future__ import annotations

from typing import Any, Dict


def email_draft(details: Dict[str, Any], message: str) -> dict[str, Any]:
    details = details if isinstance(details, dict) else {}
    from company.email_service import create_email_draft
    recipient = details.get("recipient") or details.get("to")
    subject = details.get("subject")
    body = details.get("body") or details.get("email_body")
    if not recipient or not subject or not body:
        return {"status": "missing_information", "executed": False, "message": "Please provide the recipient, subject, and message body before saving an email draft."}
    return create_email_draft(str(details.get("company_id") or ""), str(details.get("user_id") or ""), str(recipient), str(subject), str(body))


def send_email_tool(details: Dict[str, Any], message: str) -> dict[str, Any]:
    details = details if isinstance(details, dict) else {}
    try:
        email_id = int(details.get("email_id"))
    except (TypeError, ValueError):
        return {"status": "missing_information", "executed": False, "message": "A saved email draft ID is required before sending."}
    from company.email_service import send_email
    return send_email(str(details.get("company_id") or ""), str(details.get("user_id") or ""), email_id)


def search_email(details: Dict[str, Any], message: str) -> dict[str, Any]:
    details = details if isinstance(details, dict) else {}
    from company.email_service import search_emails
    results = search_emails(str(details.get("company_id") or ""), str(details.get("user_id") or ""), str(details.get("query") or message or ""), str(details.get("folder") or "inbox"))
    return {"status": "success" if results else "no_result", "executed": False, "results": results, "message": f"Found {len(results)} matching internal email(s)." if results else "No matching internal email was found."}
