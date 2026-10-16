def create_ticket(details, message):
    """Create or retrieve a tenant-scoped IT service ticket.

    This function never performs the underlying infrastructure operation. It
    records a request for the IT queue; password-provider, MDM, backup, change
    management and security integrations must be configured separately.
    """
    details = details if isinstance(details, dict) else {}
    from company.request_service import (
        create_department_request,
        list_my_department_requests,
        get_my_department_request,
    )
    import re

    company_id = str(details.get("company_id") or "").strip()
    user_id = str(details.get("user_id") or "").strip()
    text = str(message or "").strip()
    lowered = text.casefold()
    create_intent = bool(re.search(r"\b(create|raise|open|submit|report|file)\b.{0,60}\b(ticket|incident|request)\b|\b(ticket|incident|request)\b.{0,60}\b(create|raise|open|submit|report|file)\b", lowered))

    # Direct ID lookups, including contextual follow-up questions, are read-only.
    match = re.search(r"\bIT-[A-Z0-9-]{6,}\b", text, re.IGNORECASE)
    ticket_id = str(details.get("ticket_id") or (match.group(0) if match else "")).strip()
    if ticket_id and not create_intent:
        record = get_my_department_request(company_id, user_id, ticket_id)
        if not record or str(record.get("service_area") or "").casefold() != "it":
            return {"status": "not_found", "executed": False, "message": "That IT request was not found in your account."}
        category = (record.get("details") or {}).get("category") or (record.get("details") or {}).get("service_request_type") or record.get("request_type")
        return {
            "status": "success", "executed": False, "read_only": True,
            "record": record, "request_id": record.get("request_id"),
            "ticket_status": record.get("status"), "category": category,
            "message": f"IT request {record['request_id']} is {str(record['status']).replace('_', ' ')}. Title: {record.get('title') or 'IT request'}. Category: {category or 'support'}. You can see it under Employee Portal → My IT Tickets.",
        }

    history_query = bool(re.search(r"\b(show|list|display|view|retrieve|get|check|find|where|track)\b", lowered)) and bool(re.search(r"\b(ticket|tickets|incident|incidents|request history)\b", lowered)) and not create_intent
    if history_query:
        records = list_my_department_requests(company_id, user_id, "IT", limit=100)
        return {
            "status": "success" if records else "no_result", "executed": False,
            "read_only": True, "records": records,
            "message": f"Retrieved {len(records)} IT support request(s). Open Employee Portal → My IT Tickets to view IDs and status." if records else "No IT support tickets were found in your account.",
        }

    important = details.get("important", {})
    if not isinstance(important, dict):
        important = {}
    service_type = str(details.get("service_request_type") or "").strip()
    category = str(details.get("category") or important.get("category") or service_type or "support")
    priority = str(details.get("service_request_priority") or details.get("priority") or important.get("priority") or ("urgent" if service_type == "security_incident" else "normal"))
    if service_type in {"security_incident", "offboarding_access_removal", "data_recovery_backup", "change_management", "software_whitelisting", "mfa_2fa_support"}:
        requires_approval = True
    else:
        requires_approval = bool(details.get("service_request_requires_approval", False))
    subject = str(
        details.get("service_request_title")
        or important.get("subject")
        or important.get("issue")
        or details.get("subject")
        or details.get("issue")
        or _infer_ticket_title(text, category)
    )
    metadata = {
        "category": category,
        "priority": priority,
        "service_request_type": service_type or "technical_support",
        "needs_external_integration": bool(details.get("service_request_needs_external_integration")),
        "processing_note": (
            "Request recorded for IT processing only; external integrations are not invoked by ticket creation. "
            "This ticket does not itself change passwords, revoke access, restore data, enroll devices, "
            "whitelist domains, or deploy system changes."
        ),
    }
    if details.get("service_request_confidential") or service_type == "security_incident":
        metadata["confidential"] = True
        metadata["visibility"] = "authorized_it_staff"
    if details.get("service_request_priority"):
        metadata["priority"] = priority

    return create_department_request(
        company_id=company_id, user_id=user_id,
        workflow_id=str(details.get("workflow_id") or ""),
        service_area="IT", request_type="ticket",
        title=subject[:200], description=text, details=metadata,
        requires_approval=requires_approval,
    )


def _infer_ticket_title(message, category):
    import re
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    text = re.sub(r"^(?:please\s+)?(?:create|raise|open|submit|report|file)\s+(?:an?\s+)?(?:it\s+)?(?:support\s+)?(?:ticket|incident|request)\s*(?:for|about|regarding)?\s*", "", text, flags=re.IGNORECASE)
    text = text.rstrip(" .!?;:")
    if not text:
        text = str(category or "IT support request").replace("_", " ").title()
    return text[:200]


def password_access_service(details, message):
    details = details if isinstance(details, dict) else {}
    from company.request_service import create_department_request
    important = details.get("important", {})
    if not isinstance(important, dict):
        important = {}
    service_type = str(details.get("service_request_type") or "").strip()
    lowered = str(message or "").casefold()
    if not service_type:
        service_type = "mfa_2fa_support" if any(term in lowered for term in ("mfa", "2fa", "authenticator", "multi-factor", "multi factor", "otp")) else ("password_reset" if "password" in lowered else "account_access")
    title = str(details.get("service_request_title") or service_type.replace("_", " ").title())
    needs_approval = bool(details.get("service_request_requires_approval")) or service_type == "mfa_2fa_support"
    return create_department_request(
        company_id=str(details.get("company_id") or ""), user_id=str(details.get("user_id") or ""),
        workflow_id=str(details.get("workflow_id") or ""), service_area="IT", request_type=service_type,
        title=title, description=str(message or ""),
        details={"category": service_type, "system": important.get("system") or details.get("system", ""),
                 "needs_external_integration": True,
                 "processing_note": "IT request recorded; no password or identity-provider changes were executed automatically."},
        requires_approval=needs_approval,
    )


def device_service(details, message):
    details = details if isinstance(details, dict) else {}
    from company.request_service import create_department_request, list_my_department_requests
    text = str(message or "").strip()
    lowered = text.casefold()
    company_id = str(details.get("company_id") or "")
    user_id = str(details.get("user_id") or "")
    if any(word in lowered for word in ("request", "replace", "replacement", "allocate", "need", "want", "provide", "issue me", "new")):
        service_type = str(details.get("service_request_type") or "peripheral_device_request")
        item = str(details.get("item") or details.get("device") or "")
        if not item:
            item = next((word for word in ("mouse", "keyboard", "monitor", "webcam", "headset", "dock", "tablet", "mobile phone") if word in lowered), "device")
        title = str(details.get("service_request_title") or f"{item.title()} request")
        return create_department_request(
            company_id=company_id, user_id=user_id,
            workflow_id=str(details.get("workflow_id") or ""), service_area="IT",
            request_type=service_type if service_type != "peripheral_device_request" else "device_request",
            title=title, description=text,
            details={"category": service_type, "device": item,
                     "needs_external_integration": True,
                     "processing_note": "Device request recorded for IT asset review; inventory assignment has not been performed."},
            requires_approval=bool(details.get("service_request_requires_approval", True)),
        )
    records = list_my_department_requests(company_id, user_id, "IT")
    device_records = [row for row in records if row.get("request_type") in {"device_request", "peripheral_device_request"}]
    if device_records:
        return {"status": "success", "executed": False, "records": device_records, "message": f"Found {len(device_records)} device request(s) in your account."}
    return {"status": "not_configured", "executed": False, "message": "No company device inventory or device assignment is configured. I can still submit an IT device request for authorized review."}


def software_service(details, message):
    """Record software install/access/license/whitelisting requests for IT.

    The record is not a claim that software was installed or access was granted.
    """
    details = details if isinstance(details, dict) else {}
    from company.request_service import create_department_request
    text = str(message or "").strip()
    lowered = text.casefold()
    important = details.get("important", {})
    if not isinstance(important, dict):
        important = {}

    service_type = str(details.get("service_request_type") or "").strip()
    if not service_type:
        if any(term in lowered for term in ("whitelist", "allowlist", "blocked domain", "blocked website", "domain block")):
            service_type = "software_whitelisting"
        elif any(term in lowered for term in ("access", "license", "licence", "permission", "grant")):
            service_type = "software_access"
        elif any(term in lowered for term in ("install", "setup", "configure", "deploy")):
            service_type = "software_installation"
        else:
            service_type = "software_support"
    software = str(important.get("software") or details.get("software") or "Software / application")
    title = str(details.get("service_request_title") or f"{software}: {service_type.replace('_', ' ')}")
    requires_approval = bool(details.get("service_request_requires_approval")) or service_type == "software_whitelisting"
    return create_department_request(
        company_id=str(details.get("company_id") or ""), user_id=str(details.get("user_id") or ""),
        workflow_id=str(details.get("workflow_id") or ""), service_area="IT", request_type=service_type,
        title=title, description=text,
        details={"category": service_type, "software": software,
                 "needs_external_integration": True,
                 "processing_note": "IT request recorded. No software was installed, license assigned, or domain allowlist changed by this submission."},
        requires_approval=requires_approval,
    )


def knowledge_base_service(details, message):
    """Search the current tenant's IT documents and provide safe general help."""
    import re
    details = details if isinstance(details, dict) else {}
    text = str(message or "").strip()
    lowered = text.casefold()
    important = details.get("important", {})
    if not isinstance(important, dict):
        important = {}
    problem = str(important.get("problem") or important.get("issue") or details.get("problem") or details.get("issue") or "").strip()
    application = str(important.get("application") or important.get("software") or details.get("application") or details.get("software") or "").strip()
    device = str(important.get("device") or details.get("device") or "").strip()
    is_technical_problem = bool(re.search(
        r"\b(network|internet|wi.?fi|vpn|ethernet|connectivity|printer|scanner|projector|software|application|system|laptop|computer|device|password|login)\b.{0,65}\b(problem|issue|trouble|not working|slow|failed|broken|error|crash|can't connect|cannot connect)\b|"
        r"\b(problem|issue|trouble|not working|slow|failed|broken|error|crash|can't connect|cannot connect)\b.{0,65}\b(network|internet|wi.?fi|vpn|ethernet|connectivity|printer|scanner|projector|software|application|system|laptop|computer|device|password|login)\b",
        lowered,
    ))
    if not problem and is_technical_problem:
        problem = text

    # Query the authenticated tenant knowledge base; permissions are enforced
    # by search_knowledge before document snippets are returned.
    kb_result = {}
    if details.get("company_id") and details.get("user_id"):
        try:
            from tools.knowledge_tools import search_knowledge
            query_details = dict(details)
            query_details["query"] = text
            kb_result = search_knowledge(query_details, text)
            if not isinstance(kb_result, dict):
                kb_result = {}
        except Exception:
            kb_result = {}

    hits = kb_result.get("results") if isinstance(kb_result.get("results"), list) else []
    snippets = []
    for hit in hits[:3]:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or hit.get("filename") or "Company IT document").strip()
        snippet = str(hit.get("snippet") or hit.get("content") or "").strip()
        if snippet:
            snippets.append(f"{title}: {snippet}")

    if problem or is_technical_problem:
        if any(term in lowered for term in ("network", "internet", "wi-fi", "wifi", "vpn", "ethernet", "connectivity")):
            steps = (
                "Try these safe checks: (1) confirm Wi-Fi/Ethernet is connected and airplane mode is off; "
                "(2) disconnect and reconnect to the approved company network; (3) reconnect the company VPN if required; "
                "(4) check whether another approved site or internal service loads; (5) note any exact error and when it started. "
                "Do not change router, firewall, DNS, or security settings without IT approval."
            )
        elif any(term in lowered for term in ("printer", "scanner", "projector")):
            steps = (
                "Try these safe checks: (1) verify power and connection; (2) confirm the correct device is selected; "
                "(3) check for an error message or jam; (4) retry once. Avoid changing shared-device configuration without IT approval."
            )
        else:
            steps = (
                "Try these safe checks: (1) capture the exact error; (2) verify the related service and required connection; "
                "(3) close and reopen the affected app if safe; (4) check for approved updates; (5) retry once. "
                "Do not disable security controls or share passwords/OTP codes."
            )
        if snippets:
            company_guidance = "Relevant company IT material: " + " | ".join(snippets)
            source_note = "These notes came from accessible tenant documents."
        else:
            company_guidance = "No matching company-specific IT document was found, so the steps below are general guidance only."
            source_note = "If the issue persists, ask me to create an IT support ticket; I will request confirmation before submitting it."
        context = " | ".join(part for part in (
            f"Application: {application}" if application else "",
            f"Problem: {problem}" if problem else "",
            f"Device: {device}" if device else "",
        ) if part)
        prefix = f"Detected: {context.rstrip('.!?')}. " if context else ""
        return {
            "status": "success", "executed": True,
            "action": "IT troubleshooting guidance",
            "request_type": "troubleshooting", "query": text,
            "message": f"{prefix}{company_guidance} {steps} {source_note}",
            "details": {"application": application, "problem": problem, "device": device},
            "company_documents_found": bool(snippets),
            "tenant_scoped": bool(details.get("company_id")),
        }

    if snippets:
        return {
            "status": "success", "executed": True,
            "action": "IT knowledge lookup", "request_type": "knowledge_request",
            "query": text, "results": hits[:3],
            "message": "Found company IT guidance: " + " | ".join(snippets),
            "tenant_scoped": True,
        }

    return {
        "status": "no_result", "executed": False,
        "action": "IT knowledge lookup", "request_type": "knowledge_request",
        "query": text,
        "message": "No accessible company IT document matched this question. For general information, I can still explain common approaches; company-specific rules should be added under Admin → Knowledge Documents with department set to IT.",
        "results": [],
        "tenant_scoped": bool(details.get("company_id")),
    }

