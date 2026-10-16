"""Tenant-scoped read-only lookup for employee pending requests and admin approvals."""
from __future__ import annotations

import re
from typing import Any, Dict

from company.approval_service import list_pending_approvals, reconcile_pending_approval_records
from company.request_service import list_my_pending_requests


def get_pending_lookup_result(prompt: str, company_id: str, user_id: str, role: str) -> Dict[str, Any]:
    """Return authoritative saved records for an employee or authorized approver."""
    role = str(role or "employee").casefold()
    own_requests = role == "employee" or bool(re.search(
        r"\bmy\s+pending\s+requests\b", str(prompt or ""), re.IGNORECASE
    ))

    if own_requests:
        all_pending = list_my_pending_requests(company_id, user_id)
        approval_statuses = {"pending_approval", "pending", "awaiting_approval"}
        clarification_statuses = {"needs_clarification", "awaiting_clarification"}
        approval_query = bool(re.search(
            r"\bmy\s+pending\s+approvals?\b|\bpending\s+approvals?\b|\bapproval\s+queue\b",
            str(prompt or ""), re.IGNORECASE,
        )) and not bool(re.search(r"\bpending\s+requests?\b", str(prompt or ""), re.IGNORECASE))
        if approval_query:
            records = [item for item in all_pending if str(item.get("status") or "").casefold() in approval_statuses]
            clarification_count = sum(1 for item in all_pending if str(item.get("status") or "").casefold() in clarification_statuses)
            if records:
                lines = [f"You have {len(records)} request(s) awaiting approval:"]
                for item in records[:25]:
                    request_id = str(item.get("request_id") or item.get("workflow_id") or "Request")
                    title = str(item.get("display_title") or item.get("title") or item.get("request_type") or "Company request")
                    area = str(item.get("service_area") or "Company")
                    status = str(item.get("status") or "pending_approval").replace("_", " ").title()
                    lines.append(f"- **{title}** — ID: `{request_id}` · {area} · {status}")
                lines.append("These are saved requests awaiting an authorized approval decision; submission does not mean approval or completion.")
            else:
                lines = ["You have no requests currently awaiting approval."]
            if clarification_count:
                lines.append(f"\nYou also have {clarification_count} request(s) awaiting clarification; they are not in the approval queue. Ask **my pending requests** to review them separately.")
        else:
            records = all_pending
            approval_records = [item for item in records if str(item.get("status") or "").casefold() in approval_statuses]
            clarification_records = [item for item in records if str(item.get("status") or "").casefold() in clarification_statuses]
            if records:
                lines = [f"You have {len(records)} request(s) requiring follow-up: {len(approval_records)} awaiting approval and {len(clarification_records)} awaiting clarification."]
                for group_title, group in (("Awaiting approval", approval_records), ("Awaiting clarification", clarification_records)):
                    if group:
                        lines.append(f"\n**{group_title}**")
                    for item in group[:25]:
                        request_id = str(item.get("request_id") or item.get("workflow_id") or "Request")
                        title = str(item.get("display_title") or item.get("title") or item.get("request_type") or "Company request")
                        area = str(item.get("service_area") or "Company")
                        status = str(item.get("status") or "pending_approval").replace("_", " ").title()
                        lines.append(f"- **{title}** — ID: `{request_id}` · {area} · {status}")
                lines.append("These are saved workflow records. Submission does not mean approval or completion.")
            else:
                lines = ["You have no requests currently waiting for approval or clarification."]
        tool_name = "list_my_pending_requests"
        agent_names = ["HR Agent", "IT Support Agent"]
        department = "My Requests"
    else:
        # Reconcile legacy submissions on a privileged approval lookup so they
        # become visible without requiring the user to create a duplicate.
        reconcile_pending_approval_records(company_id)
        records = list_pending_approvals(company_id) if role == "company_admin" else list_pending_approvals(company_id, user_id)
        area_roles = {"it": "it_admin", "hr": "hr_admin", "finance": "finance_admin", "procurement": "procurement_admin", "recruitment": "recruitment_admin"}
        if role != "company_admin":
            records = [item for item in records if item.get("approver_user_id") == user_id or (not item.get("approver_user_id") and area_roles.get(str((item.get("metadata") or {}).get("service_area") or (item.get("metadata") or {}).get("department") or "").casefold()) == role)]
        if records:
            lines = [f"There are {len(records)} pending approval(s) in your authorized queue:"]
            for item in records[:25]:
                meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                request_id = str(meta.get("request_id") or f"Approval #{item.get('approval_id')}")
                title = str(meta.get("title") or item.get("approval_type") or "Company request").replace("_", " ").title()
                area = str(meta.get("service_area") or meta.get("department") or "Company")
                lines.append(f"- **{title}** — ID: `{request_id}` · {area} · Pending approval (approval #{item.get('approval_id')})")
        else:
            lines = ["There are no pending approvals assigned to your authorized queue."]
        tool_name = "list_pending_approvals"
        agent_names = ["Company Admin Agent"] if role == "company_admin" else ["Approval Coordinator"]
        department = "Company Approvals"

    return {
        "response": "\n".join(lines),
        "raw_message": str(prompt or ""),
        "company_id": company_id,
        "user_id": user_id,
        "user_role": role,
        "workflow_id": "",
        "status": "completed",
        "validation": {"status": "success"},
        "decision": {"action": "CONTINUE", "reason": "Read-only pending request lookup."},
        "request_category": "information_request",
        "intent": "pending_requests_lookup",
        "department": department,
        "departments": [department],
        "assigned_agents": agent_names,
        "tool_names": [tool_name],
        "tools": [tool_name],
        "tool_plan": [{"tool": tool_name, "agent": agent_names[0], "purpose": "Retrieve saved pending requests/approvals for the authenticated user."}],
        "tool_results": [{"tool": tool_name, "status": "success", "executed": False, "record_count": len(records), "records": records}],
        "details": {"record_count": len(records)},
    }
