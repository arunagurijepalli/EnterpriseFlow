from __future__ import annotations

import re
from typing import Any, Dict

from company.request_service import create_department_request, get_my_department_request, list_my_department_requests
from company.store import authorize_user


def job_requisition_service(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    company_id = str(details.get("company_id") or "")
    user_id = str(details.get("user_id") or "")
    authorize_user(company_id, user_id)
    text = str(message or "").strip()
    important = details.get("important", {})
    if not isinstance(important, dict):
        important = {}
    match = re.search(r"\bREC-[A-Z0-9-]+\b", text, re.IGNORECASE)
    if match and not any(word in text.lower() for word in ("create", "open", "hire", "request")):
        record = get_my_department_request(company_id, user_id, match.group(0))
        if not record or record.get("service_area") != "Recruitment":
            return {"status": "not_found", "executed": False, "message": "That recruitment request was not found in your account."}
        return {"status": "success", "executed": False, "record": record, "message": f"Recruitment request {record['request_id']} is {record['status'].replace('_', ' ')}."}
    if any(word in text.lower() for word in ("status", "history", "previous", "my requisitions")) and not any(word in text.lower() for word in ("create", "open", "hire", "request")):
        records = list_my_department_requests(company_id, user_id, "Recruitment")
        return {"status": "success" if records else "no_result", "executed": False, "records": records, "message": f"Retrieved {len(records)} recruitment request(s)." if records else "No recruitment requests were found in your account."}
    title = str(important.get("job_title") or important.get("position") or details.get("job_title") or details.get("position") or details.get("title") or "").strip()
    if not title:
        return {"status": "missing_information", "executed": False, "message": "Please provide the job title before creating a requisition."}
    result = create_department_request(company_id=company_id, user_id=user_id, workflow_id=str(details.get("workflow_id") or ""), service_area="Recruitment", request_type="job_requisition", title=title, description=text, details={"department": important.get("department") or details.get("department") or "", "employment_type": important.get("employment_type") or details.get("employment_type") or "", "headcount": important.get("headcount") or details.get("headcount") or 1}, requires_approval=True)
    result["tool"] = "job_requisition_service"
    return result


def recruitment_status_service(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    company_id = str(details.get("company_id") or "")
    user_id = str(details.get("user_id") or "")
    authorize_user(company_id, user_id)
    match = re.search(r"\bREC-[A-Z0-9-]+\b", str(message or ""), re.IGNORECASE)
    if match:
        record = get_my_department_request(company_id, user_id, match.group(0))
        if not record or record.get("service_area") != "Recruitment":
            return {"status": "not_found", "executed": False, "message": "That recruitment request was not found in your account."}
        return {"status": "success", "executed": False, "record": record, "message": f"Recruitment request {record['request_id']} is {record['status'].replace('_', ' ')}."}
    records = list_my_department_requests(company_id, user_id, "Recruitment")
    return {"status": "success" if records else "no_result", "executed": False, "records": records, "message": f"Retrieved {len(records)} recruitment request(s)." if records else "No recruitment requests were found in your account."}


def candidate_service(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    authorize_user(str(details.get("company_id") or ""), str(details.get("user_id") or ""))
    return {"status": "not_configured", "executed": False, "message": "No tenant candidate directory is configured, so no candidate records can be returned."}


def interview_service(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    company_id = str(details.get("company_id") or "")
    user_id = str(details.get("user_id") or "")
    authorize_user(company_id, user_id)
    important = details.get("important", {})
    if not isinstance(important, dict):
        important = {}
    candidate_id = str(important.get("candidate_id") or details.get("candidate_id") or "").strip()
    scheduled_at = str(important.get("scheduled_at") or details.get("scheduled_at") or "").strip()
    if not candidate_id or not scheduled_at:
        return {"status": "missing_information", "executed": False, "message": "A candidate ID and interview date/time are required before scheduling."}
    result = create_department_request(company_id=company_id, user_id=user_id, workflow_id=str(details.get("workflow_id") or ""), service_area="Recruitment", request_type="interview", title=f"Interview with {candidate_id}", description=str(message or ""), details={"candidate_id": candidate_id, "scheduled_at": scheduled_at, "interviewers": important.get("interviewers") or details.get("interviewers") or []})
    result["tool"] = "interview_service"
    return result
