"""Deterministic HR/IT service catalogue and safe follow-up routing.

The catalogue creates tenant-scoped *requests/tickets*, not fictional external
operations. Integrations such as identity-provider changes, payroll, MDM and
backup restoration still need a configured provider and an authorized operator.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

ACTION_RE = re.compile(
    r"\b(?:i need|i want|i would like|please|create|raise|open|submit|file|apply|request|"
    r"report|enrol|enroll|sign me up|reset|unlock|install|configure|whitelist|allowlist|allowlisting|"
    r"recover|restore|transfer me|move me|correct|fix|update my|change my|remove|disable|"
    r"revoke|deprovision|offboard|offboarding|resigning|onboard|book|claim|reimburse|issue me|send me|provide me|"
    r"set up|set me up|grant|enable|block|schedule|escalate)\b",
    re.IGNORECASE,
)
QUESTION_ONLY_RE = re.compile(
    r"^\s*(?:what|which|where|when|why|how|who|can you explain|tell me|could you explain)\b",
    re.IGNORECASE,
)

# Specialized request categories not already represented by a dedicated
# transactional HR workflow. Titles and type identifiers are server-owned.
HR_REQUEST_CATEGORIES = {
    "employment_verification_letter": "Employment verification / salary certificate",
    "expense_reimbursement": "Expense reimbursement",
    "relocation_mobility": "Relocation / office transfer",
    "medical_accommodation": "Medical or workplace accommodation",
    "visa_immigration_support": "Visa / immigration support",
    "whistleblower_ethics": "Confidential ethics report",
    "payroll_compensation_request": "Payroll / compensation support",
    "performance_appraisal_request": "Performance appraisal / promotion support",
    "attendance_correction": "Attendance correction",
    "insurance_claim": "Insurance claim support",
    "insurance_enrollment": "Insurance enrollment",
    "employee_onboarding_request": "Employee onboarding support",
    "employee_offboarding_request": "Employee offboarding / exit support",
    "family_leave_support": "Maternity / paternity / parental leave support",
    "hr_document_request": "HR document request",
    "employee_grievance": "Employee grievance / workplace concern",
    "professional_training_request": "Training and professional development request",
    "benefit_enrollment_request": "Employee benefits / wellness enrollment",
    "remote_work_request": "Remote-work / flexible-work arrangement",
    "generic_hr_request": "General HR service request",
}

IT_REQUEST_CATEGORIES = {
    "mfa_2fa_support": "MFA / 2FA support",
    "software_whitelisting": "Software / domain allowlisting",
    "byod_mdm_enrollment": "BYOD / mobile-device enrollment",
    "data_recovery_backup": "Data recovery / backup restore",
    "offboarding_access_removal": "Offboarding access removal",
    "change_management": "IT change / system upgrade request",
    "security_incident": "Security incident report",
    "office_equipment_support": "Printer / scanner / projector support",
    "peripheral_device_request": "Hardware peripheral request",
    "password_reset": "Password reset / account unlock",
    "software_installation_access": "Software installation / access / license",
    "account_access_request": "Account / company email access support",
    "network_connectivity": "Network / connectivity support",
    "device_repair_support": "Device repair / performance support",
    "hardware_asset_request": "Hardware allocation / replacement request",
    "it_general_request": "General IT support request",
}

# Pattern order matters: high-risk and specific terms should match first.
_RULES = [
    # IT security / access lifecycle
    ("IT", "security_incident", "create_ticket", "IT Support Agent", r"\b(phishing|malware|ransomware|security incident|antivirus alert|data loss prevention|data leak|suspicious email|security breach)\b", True, "urgent", True),
    ("IT", "offboarding_access_removal", "create_ticket", "IT Support Agent", r"\b(de.?provision(?:ing)?|offboarding access|offboarding.{0,30}(?:access|account|email|system)|(?:access|account|email).{0,30}offboarding|(?:request )?removal of (?:employee )?access for (?:an? )?employee(?: who is leaving| who is resigning| leaving)?|remove (?:employee )?access for|remove employee access|remove access when (?:an? )?(?:employee|staff|contractor) (?:leaves|resigns|exits)|revoke (?:employee )?access when (?:an? )?(?:employee|staff|contractor) (?:leaves|resigns|exits)|revoke employee access|disable access when (?:an? )?(?:employee|staff|contractor) (?:leaves|resigns|exits)|disable access for|revoke (?:an? employee'?s? )?access|disable employee account|terminate account access|employee who is leaving access)\b", True, "high", True),
    ("IT", "data_recovery_backup", "create_ticket", "IT Support Agent", r"\b(data recovery|recover deleted files?|restore deleted files?|restore (?:a )?backup|backup restore|recover (?:my )?files?|file recovery|recover (?:my )?(?:onedrive|sharepoint|cloud) files?|restore (?:my )?(?:onedrive|sharepoint|cloud) (?:file|document|backup)|accidentally deleted (?:an? )?(?:important )?(?:work )?files?|deleted (?:an? )?(?:important )?(?:work )?files?|help (?:me )?recovering (?:it|this|that|the file|my file|my files)|recovering (?:it|this|that|the file|my file|my files)|help (?:me )?recover (?:it|this|that|the file|my file|my files))\b", True, "high", True),
    ("IT", "change_management", "create_ticket", "IT Support Agent", r"\b(change request|system(?:-wide)? upgrade|infrastructure change|production change|schedule maintenance|deploy (?:a )?system update|scheduled (?:company )?software upgrade|schedule (?:a )?(?:company )?software upgrade|company software upgrade|scheduled upgrade|system software upgrade)\b", True, "high", True),
    ("IT", "byod_mdm_enrollment", "create_ticket", "IT Support Agent", r"\b(byod|mdm enrollment|mobile device management|enroll my personal (?:phone|device)|company profile on my phone|personal (?:phone|tablet) enrollment)\b", True, "normal", True),
    ("IT", "software_whitelisting", "software_service", "IT Support Agent", r"\b(whitelist(?:ing)?|allowlist(?:ing)?|allow[- ]listing|allow list|domain block|blocked domain|blocked website|software whitelisting|allow this website|allow this domain|website reviewed for allowlisting|business website.*allowlist(?:ing)?)\b", True, "high", True),
    ("IT", "mfa_2fa_support", "password_access_service", "IT Support Agent", r"\b(mfa|2fa|multi[- ]factor|authenticator app|otp not working|one[- ]time password|two[- ]factor)\b", True, "high", True),
    ("IT", "password_reset", "password_access_service", "IT Support Agent", r"\b(password reset|reset(?:ting)? my password|help (?:me )?reset(?:ting)? (?:my )?password|forgot my password|account locked|unlock my account|locked out of my account)\b", True, "normal", True),
    ("IT", "account_access_request", "password_access_service", "IT Support Agent", r"\b(company email setup|set up (?:my )?(?:company )?email|email account setup|email access|account access|login access|locked out of (?:my )?(?:company )?account|unlock (?:my )?(?:company )?account|grant (?:me )?access to (?:my )?account)\b", True, "normal", True),
    ("IT", "software_installation_access", "software_service", "IT Support Agent", r"\b(install(?:ation)? (?:the )?(?:company )?software|install (?:python|java|visual studio code|vs code|microsoft office|adobe)|software (?:license|licence|access)|application access|grant access to (?:the )?(?:software|application|tool)|license request|licence request|install software|software installation)\b", True, "normal", True),
    ("IT", "network_connectivity", "create_ticket", "IT Support Agent", r"\b(network (?:problem|issue|connectivity|connection|outage|ticket|support)|(?:problem|issue)\b.{0,35}\b(?:network|internet|wi.?fi|vpn)|internet (?:problem|issue|outage|support ticket|connection issue|not working)|vpn (?:disconnecting|outage|support|ticket|connection issue|problem)|wi.?fi (?:problem|issue|outage|connection issue|support ticket|not working)|connectivity (?:request|ticket|issue)|network keeps disconnecting|vpn keeps disconnecting)\b", False, "normal", True),
    ("IT", "device_repair_support", "create_ticket", "IT Support Agent", r"\b(blue screen|laptop crash(?:ing)?|computer crash(?:ing)?|(?:laptop|computer|device) repair|repair (?:my )?(?:laptop|computer|device)|broken (?:laptop|computer|monitor|keyboard)|laptop (?:won't start|will not start|not booting|overheating)|computer (?:won't start|will not start|not booting)|slow computer|slow laptop|device performance issue)\b", False, "normal", True),
    ("IT", "office_equipment_support", "create_ticket", "IT Support Agent", r"\b(printer|scanner|projector|conference[- ]room display|office equipment)\b", False, "normal", False),
    ("IT", "peripheral_device_request", "device_service", "IT Support Agent", r"\b(mouse|keyboard|monitor|webcam|headset|dock(?:ing station)?|mobile phone|tablet)\b", True, "normal", True),

    # HR confidentiality-sensitive and specialized requests
    ("HR", "whistleblower_ethics", "hr_grievance_service", "HR Agent", r"\b(whistleblower|report fraud|fraud report|ethics violation|anonymous report|report harassment|workplace harassment|retaliation report)\b", True, "high", True),
    ("HR", "employee_grievance", "hr_grievance_service", "HR Agent", r"\b(employee grievance|workplace grievance|workplace complaint|team conflict|unprofessional behavior|manager misconduct|report a workplace concern|raise a grievance|report (?:sexual )?harassment|complaint about (?:my )?manager)\b", True, "normal", True),
    ("HR", "benefit_enrollment_request", "benefits_service", "HR Agent", r"\b(gym membership|gym benefit|wellness membership|employee perk enrollment|enroll in (?:the )?(?:gym|wellness)|sign up for (?:the )?(?:gym|wellness)|enroll me in (?:employee )?benefits|enroll in (?:the )?(?:employee |company )?benefits|benefits enrollment|employee benefits enrollment|apply for employee benefits|add me to (?:the )?(?:employee )?benefits)\b", True, "normal", True),
    ("HR", "remote_work_request", "hr_general_request_service", "HR Agent", r"\b(request (?:to )?work from home|work from home arrangement|remote work request|remote-work arrangement|flexible work arrangement|change my work location|change my remote work schedule|update my work from home schedule|update my remote work schedule|request (?:a )?hybrid work arrangement|hybrid work arrangement)\b", True, "normal", True),
    ("HR", "visa_immigration_support", "hr_general_request_service", "HR Agent", r"\b(visa sponsorship|visa stamping|immigration support|immigration documents|work visa|visa processing|immigration assistance|visa for onsite|immigration help|employment visa documentation|hr assistance with (?:employment )?visa|visa documentation support)\b", True, "normal", True),
    ("HR", "medical_accommodation", "hr_general_request_service", "HR Agent", r"\b(medical accommodation|workplace accommodation|work accommodation|ergonomic chair|special seating|medical restriction|reasonable accommodation)\b", True, "normal", True),
    ("HR", "relocation_mobility", "hr_general_request_service", "HR Agent", r"\b(relocation|relocate|transfer to (?:another|a different) (?:company )?(?:office(?: location)?|city)|move to (?:another|a different) (?:company )?(?:office(?: location)?|city)|office transfer|location transfer|work location transfer)\b", True, "normal", True),
    ("HR", "expense_reimbursement", "hr_general_request_service", "HR Agent", r"\b(expense reimbursement|reimburse(?:ment)?|business trip expense|client dinner expense|internet bill claim|travel expense claim)\b", True, "normal", True),
    ("HR", "employment_verification_letter", "hr_general_request_service", "HR Agent", r"\b(employment verification|employment letter|salary certificate|proof of employment|employment certificate|bank loan employment letter)\b", True, "normal", True),
    ("HR", "payroll_compensation_request", "hr_general_request_service", "HR Agent", r"\b(tax declaration|tax withholding|payroll correction|salary discrepancy|salary adjustment|salary increase|salary not credited|salary advance|compensation(?: package| adjustment| question| request| review)?|bonus request|bonus correction|request (?:a )?bonus|update (?:my )?bank account|change (?:my )?bank account|update (?:my )?bank details|change (?:my )?bank details|correct (?:my )?bank details|payslip(?: request)?|pay slip(?: request)?|salary slip(?: request)?|pay stub|missing salary)\b", True, "normal", True),
    ("HR", "performance_appraisal_request", "hr_general_request_service", "HR Agent", r"\b(appraisal form|request (?:an? )?appraisal|promotion request|request (?:a )?promotion|promotion letter|performance review request|performance review meeting|request (?:a )?performance review meeting|request (?:manager )?feedback|manager feedback request|performance appraisal)\b", True, "normal", True),
    ("HR", "professional_training_request", "hr_training_service", "HR Agent", r"\b(training request|request training|professional development|skill development course|technical training course|enroll in (?:a )?technical training course|technical training program|certification training|upskilling course|training program request|enroll in a training course)\b", True, "normal", True),
    ("HR", "attendance_correction", "hr_general_request_service", "HR Agent", r"\b(attendance correction|correct (?:my |an? )?attendance(?: record| entry| log)?|missed punch|forgot to clock in|attendance adjustment|attendance record correction|attendance.{0,25}(?:wrong|incorrect|correction|update|fix|adjust))\b", True, "normal", True),
    ("HR", "insurance_claim", "hr_general_request_service", "HR Agent", r"\b(insurance claim|health insurance claim|medical insurance claim|submit an insurance claim)\b", True, "normal", True),
    ("HR", "insurance_enrollment", "hr_general_request_service", "HR Agent", r"\b(insurance enrollment|enroll (?:me|my family|my spouse|my partner) in (?:the )?(?:company )?(?:health )?insurance(?: plan)?|enroll in (?:the )?(?:(?:company|employee) )?(?:health )?insurance(?: plan)?|company health insurance plan|add (?:me|my family|my spouse) to insurance|health insurance sign.?up|health insurance enrollment|benefit enrollment)\b", True, "normal", True),
    ("HR", "employee_offboarding_request", "hr_general_request_service", "HR Agent", r"\b(initiate offboarding|start offboarding|begin offboarding|request offboarding|process offboarding|employee offboarding|offboarding process|my offboarding process|help with (?:my )?offboarding|i am resigning|i'm resigning|offboard (?:an? )?(?:employee|new hire|staff member)|exit interview|exit formalities|employee separation process)\b", True, "normal", True),
    ("HR", "employee_onboarding_request", "hr_general_request_service", "HR Agent", r"\b(start onboarding|initiate onboarding|onboard (?:a )?(?:new employee|new hire)|new hire onboarding|new hire documents|onboarding documents|employee onboarding documents|help completing (?:my )?(?:employee )?onboarding documents|complete (?:my )?(?:employee )?onboarding documents|resignation support|i want to resign|i need to resign|resignation process)\b", True, "normal", True),
    ("HR", "family_leave_support", "leave_management", "HR Agent", r"\b(maternity leave|paternity leave|parental leave)\b", True, "normal", True),
    ("HR", "hr_document_request", "hr_general_request_service", "HR Agent", r"\b(employment document|experience letter|experience certificate|relieving letter|no.?objection certificate|n.?o.?c|service certificate|visa letter)\b", True, "normal", True),
]


def is_action_request(text: str) -> bool:
    lowered = str(text or "").strip().casefold()
    if not lowered:
        return False

    # Requests for instructions must not be treated as permission to execute
    # the operation mentioned in the question (e.g. "How do I reset MFA?").
    guidance_question = bool(re.match(
        r"^\s*(?:how (?:do|can|should|would) i\b|how to\b|what (?:is|are|should|tool|steps|do i)\b|"
        r"where (?:do|can|should) i\b|when should i\b|why (?:does|is|do)\b|"
        r"can you (?:tell me|explain|show me how|walk me through)\b|"
        r"could you (?:tell me|explain|walk me through)\b|what is the process for\b|"
        r"is there a way to\b)",
        lowered,
    ))
    explicit_request = bool(re.match(
        r"^\s*(?:i need\b|i want\b|i would like\b|i'd like\b|please\b|"
        r"create\b|raise\b|open\b|submit\b|file\b|report\b|reset\b|unlock\b|"
        r"install\b|configure\b|whitelist\b|allowlist\b|recover\b|restore\b|"
        r"transfer me\b|move me\b|correct my\b|update my\b|change my\b|remove access\b|"
        r"disable access\b|revoke access\b|claim\b|reimburse\b|issue me\b|send me\b|"
        r"can i (?:get|have|request|apply for|submit|enroll|enrol|reset|report)\b|"
        r"could i (?:get|have|request|apply for|submit)\b|may i (?:get|have|request)\b|"
        r"(?:could|can|would) you help me (?:submit|request|apply|report|reset|install|recover|restore|transfer|correct|update|change|enroll|enrol)\b)",
        lowered,
    ))
    if guidance_question and not explicit_request:
        return False

    # Questions about procedures are information requests, not submissions.
    if QUESTION_ONLY_RE.search(lowered) and not explicit_request:
        return False
    if explicit_request:
        return True
    return bool(ACTION_RE.search(lowered))


def classify_specialized_request(text: str) -> Optional[Dict[str, Any]]:
    """Return deterministic routing for an actionable HR/IT catalogue request."""
    lowered = str(text or "").strip().casefold()
    if not lowered:
        return None
    if not is_action_request(lowered):
        return None

    for area, request_type, tool, agent, pattern, approval_required, priority, needs_integration in _RULES:
        if not re.search(pattern, lowered, re.IGNORECASE):
            continue
        titles = HR_REQUEST_CATEGORIES if area == "HR" else IT_REQUEST_CATEGORIES
        title = titles.get(request_type, request_type.replace("_", " ").title())
        details: Dict[str, Any] = {
            "service_request_type": request_type,
            "service_request_title": title,
            "service_request_area": area,
            "service_request_priority": priority,
            "service_request_requires_approval": bool(approval_required),
            "service_request_needs_external_integration": bool(needs_integration),
        }
        if request_type in {"security_incident", "offboarding_access_removal", "whistleblower_ethics", "medical_accommodation"}:
            details["service_request_confidential"] = True
        if area == "IT":
            details["category"] = request_type
            details["priority"] = priority
        if request_type == "family_leave_support":
            leave_match = re.search(r"\b(maternity|paternity|parental)\s+leave\b", lowered)
            details["leave_type"] = f"{leave_match.group(1).title()} leave" if leave_match else "Parental leave"
        return {
            "request_category": "enterprise_action",
            "intent": request_type,
            "department": area,
            "departments": [area],
            "agents": [agent],
            "tools": [tool],
            "tool_plan": [{"tool": tool, "agent": agent, "purpose": f"Submit and track a {title.lower()} request in the {area} workflow."}],
            "details": details,
            "requires_action": True,
            "confidence": 0.92,
            "catalog_route": True,
        }

    # A bare ticket-creation command has no symptom/category for the model to
    # infer. Route it deterministically to IT and let the tool ask for the
    # missing issue before confirmation; never let the LLM turn this into a
    # generic knowledge search.
    explicit_ticket_action = bool(re.search(
        r"\b(?:create|creat|cretae|make|raise|open|submit|log|file)\b.{0,55}"
        r"\b(?:an?\s+)?(?:it\s+)?(?:support\s+)?ticket\b|"
        r"\b(?:it\s+)?(?:support\s+)?ticket\b.{0,55}"
        r"\b(?:create|creat|cretae|make|raise|open|submit|log|file)\b",
        lowered, re.IGNORECASE,
    ))
    if explicit_ticket_action:
        title = IT_REQUEST_CATEGORIES["it_general_request"]
        details = {
            "service_request_type": "it_general_request",
            "service_request_title": title,
            "service_request_area": "IT",
            "service_request_priority": "normal",
            "service_request_requires_approval": False,
            "service_request_needs_external_integration": False,
            "category": "it_general_request",
            "priority": "normal",
        }
        return {
            "request_category": "enterprise_action",
            "intent": "it_general_request",
            "department": "IT",
            "departments": ["IT"],
            "agents": ["IT Support Agent"],
            "tools": ["create_ticket"],
            "tool_plan": [{"tool": "create_ticket", "agent": "IT Support Agent", "purpose": "Create and track an explicitly requested IT support ticket."}],
            "details": details,
            "requires_action": True,
            "confidence": 0.97,
            "catalog_route": True,
        }

    # Extensible domain fallback: a valid new HR/IT action should still become
    # a tracked, confirmation-gated request even when it does not match a named
    # category above. Keep the existing leave and priced laptop/procurement
    # workflows untouched.
    if re.search(r"\b(?:leave|time off|day off|vacation)\b", lowered):
        return None  # use the dedicated leave workflow and its date/balance checks
    if re.search(r"\b(?:laptop|workstation|computer)\b", lowered) and not re.search(
        r"\b(?:problem|issue|trouble|not working|broken|repair|crash|slow|blue screen|won't start|will not start|install(?:ed|ation)?|software|license|licence)\b", lowered
    ) and not re.search(r"\b(?:hardware asset request|it asset request|device allocation|allocate a loaner)\b", lowered) and re.search(
        r"\b(?:need|want|request|issue me|allocate|provide|purchase|buy|order|price|cost|catalog|catalogue|inventory|stock|model|budget|development|workstation|new)\b", lowered
    ):
        return None  # preserve the existing laptop assistant + catalog/procurement workflow

    hr_terms = re.findall(
        r"\b(?:hr|human resources|employee|employment|payroll|salary|payslip|pay slip|compensation|bonus|benefit|benefits|insurance|appraisal|promotion|performance review|grievance|harassment|workplace|training|professional development|certificate|employment letter|relocation|relocate|office transfer|visa|immigration|reimbursement|reimburse|expense|tax declaration|maternity|paternity|parental|onboarding|offboarding|resignation|medical accommodation|ergonomic chair|wellness|gym membership|work from home|remote work|hybrid work|holiday calendar|dress code|attendance|leave correction)\b",
        lowered,
    )
    it_terms = re.findall(
        r"\b(?:it support|information technology|technical issue|technical problem|technical support|internal system|internal application|network|internet|wi.?fi|vpn|connectivity|laptop|computer|workstation|hardware|device|software|install(?:ed|ation)?|license|licence|access|account|password|login|mfa|2fa|otp|authenticator|security|phishing|malware|server|printer|scanner|projector|domain|website blocked|whitelist|allowlist|byod|mdm|backup|restore|recover|recovery|onedrive|sharepoint|deleted file|data recovery|change request|system upgrade|email setup|email account|corporate email|firewall|usb|blue screen|device repair|employee account)\b",
        lowered,
    )
    if not hr_terms and not it_terms:
        return None

    # Prefer a clear technical signal over generic "employee/workplace" terms.
    if it_terms and (not hr_terms or len(it_terms) >= len(hr_terms)):
        area, agent = "IT", "IT Support Agent"
        if re.search(r"\b(?:offboard(?:ing)?|de.?provision|revoke employee access|remove employee access|disable employee account|terminate account access)\b", lowered):
            tool, request_type = "create_ticket", "offboarding_access_removal"
        elif re.search(r"\b(?:password|mfa|2fa|otp|authenticator|account access|login|email setup|email account|corporate email|employee account)\b", lowered):
            tool, request_type = "password_access_service", "account_access_request"
        elif re.search(r"\b(?:software|install(?:ed|ation)?|license|licence|whitelist|allowlist|domain|python installed|java installed)\b", lowered):
            tool, request_type = "software_service", "software_installation_access"
        elif re.search(r"\b(?:laptop|workstation|computer|mouse|keyboard|monitor|webcam|headset|dock|tablet|mobile phone|device allocation|device request|new device|hardware request)\b", lowered):
            tool, request_type = "device_service", "hardware_asset_request" if re.search(r"\b(?:laptop|workstation|computer|new device|hardware request)\b", lowered) else "peripheral_device_request"
        elif re.search(r"\b(?:network|internet|wi.?fi|vpn|connectivity)\b", lowered):
            tool, request_type = "create_ticket", "network_connectivity"
        elif re.search(r"\b(?:recover|recovery|restore|backup|onedrive|sharepoint|deleted file)\b", lowered):
            tool, request_type = "create_ticket", "data_recovery_backup"
        else:
            tool, request_type = "create_ticket", "it_general_request"
        titles = IT_REQUEST_CATEGORIES
        priority = "high" if re.search(r"\b(?:security|phishing|malware|ransomware|data leak|offboarding|revoke access)\b", lowered) else "normal"
        confidential = bool(re.search(r"\b(?:phishing|malware|ransomware|security|data leak|offboarding|revoke access)\b", lowered))
    else:
        area, agent = "HR", "HR Agent"
        if re.search(r"\b(?:gym membership|wellness|employee perks|benefit enrollment)\b", lowered):
            tool, request_type = "benefits_service", "benefit_enrollment_request"
        elif re.search(r"\b(?:work from home|remote work|remote-work|hybrid work|flexible work|flexible schedule)\b", lowered):
            tool, request_type = "hr_general_request_service", "remote_work_request"
        elif re.search(r"\b(?:training|course|certification|upskilling)\b", lowered):
            tool, request_type = "hr_training_service", "professional_training_request"
        elif re.search(r"\b(?:harassment|grievance|workplace complaint|ethics|fraud report|whistleblower)\b", lowered):
            tool, request_type = "hr_grievance_service", "employee_grievance"
        else:
            tool, request_type = "hr_general_request_service", "generic_hr_request"
        titles = HR_REQUEST_CATEGORIES
        priority = "high" if re.search(r"\b(?:harassment|whistleblower|ethics|fraud|medical accommodation)\b", lowered) else "normal"
        confidential = bool(re.search(r"\b(?:harassment|whistleblower|ethics|fraud|medical accommodation)\b", lowered))

    title = titles.get(request_type, request_type.replace("_", " ").title())
    if request_type in {"it_general_request", "generic_hr_request"}:
        compact = re.sub(r"\s+", " ", str(text).strip()).rstrip(".!? ")
        title = (compact[:150] if compact else title)
    # User confirmation is enforced separately by ACTION_TOOLS. Internal
    # department approval is reserved for categories that actually need it;
    # routine network/device/office support should not be stuck as Pending
    # Approval simply because it was routed by the generic fallback.
    routine_it_categories = {
        "network_connectivity", "it_general_request",
        "device_repair_support", "office_equipment_support",
    }
    needs_department_approval = (
        request_type not in routine_it_categories if area == "IT" else True
    )
    details = {
        "service_request_type": request_type,
        "service_request_title": title,
        "service_request_area": area,
        "service_request_priority": priority,
        "service_request_requires_approval": needs_department_approval,
        "service_request_needs_external_integration": True,
        "service_request_confidential": confidential,
    }
    if area == "IT":
        details.update({"category": request_type, "priority": priority})
    return {
        "request_category": "enterprise_action", "intent": request_type,
        "department": area, "departments": [area], "agents": [agent],
        "tools": [tool],
        "tool_plan": [{"tool": tool, "agent": agent, "purpose": f"Create and track a confirmed {title.lower()} request in the {area} service queue."}],
        "details": details, "requires_action": True, "confidence": 0.80,
        "catalog_route": True, "catalog_fallback": True,
    }


def extract_recent_it_ticket_id(history: Optional[Iterable[Dict[str, Any]]]) -> str:
    """Return the most recent IT ticket ID in prior assistant/user messages."""
    for item in reversed(list(history or [])):
        if not isinstance(item, dict):
            continue
        text = str(item.get("content") or item.get("message") or "")
        matches = re.findall(r"\bIT-[A-Z0-9-]{6,}\b", text, re.IGNORECASE)
        if matches:
            return matches[-1].upper()
    return ""


def classify_read_only_route(text: str, history: Optional[Iterable[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Resolve high-confidence read-only questions before provider tool plans."""
    raw = str(text or "").strip()
    lowered = raw.casefold()
    if not lowered:
        return None

    # Terminal commands and pasted run paths are not employee service requests.
    # This guard runs before provider-selected tools are accepted by workflow.py.
    command_like = bool(re.match(
        r"^(?:\.{1,2}[^\s]*[\\/]scripts[\\/]|"
        r"[a-z]:[\\/]|(?:python(?:\.exe)?|pip(?:3)?|streamlit(?:\.exe)?|"
        r"git|npm|node|powershell|cmd)(?:\s|$))",
        lowered,
    )) or bool(re.search(
        r"\\scripts\\streamlit(?:\.exe)?\s+run\s+.*\bapp\.py\b",
        lowered,
    ))
    if command_like:
        return {
            "request_category": "information_request",
            "intent": "command_or_code_input",
            "department": "Knowledge",
            "departments": ["Knowledge"],
            "agents": ["Knowledge Agent"],
            "tools": ["search_knowledge"],
            "tool_plan": [{"tool": "search_knowledge", "agent": "Knowledge Agent", "purpose": "Treat pasted command/code as informational input; do not create an employee request."}],
            "details": {"query": raw, "information_only": True},
            "requires_action": False,
        }

    ticket_id = extract_recent_it_ticket_id(history)
    vague_ticket_followup = bool(ticket_id) and bool(re.search(
        r"\b(where (?:do|can) i see|where is it|show (?:me )?(?:that|it|the ticket)|"
        r"show (?:me )?(?:the )?details|ticket details|details of (?:that|it|the ticket)|"
        r"what(?:'s| is) (?:the )?status|status of (?:that|it|the ticket)|track (?:that|it|the ticket)|"
        r"did (?:it|that) (?:go through|submit)|that ticket|my ticket status)\b",
        lowered,
    ))
    if vague_ticket_followup:
        return {
            "request_category": "information_request",
            "intent": "it_ticket_follow_up",
            "department": "IT",
            "departments": ["IT"],
            "agents": ["IT Support Agent"],
            "tools": ["create_ticket"],
            "tool_plan": [{"tool": "create_ticket", "agent": "IT Support Agent", "purpose": "Retrieve the previously created IT request without creating a new one."}],
            "details": {"ticket_id": ticket_id, "read_only_follow_up": True},
            "requires_action": False,
        }

    # Natural language general learning/technology questions must never turn
    # into a business action simply because a provider guessed an HR tool.
    is_learning_question = bool(
        re.search(r"\b(?:what|which|how|where|can you tell me)\b", lowered)
        and re.search(r"\b(?:learn|learning|course|tutorial|practice|tool|start|begin)\b", lowered)
        and re.search(r"\b(?:python|programming|coding|machine learning|ai|data science|sql|java)\b", lowered)
        and not is_action_request(lowered)
    )
    if is_learning_question:
        return {
            "request_category": "information_request", "intent": "general_learning_guidance",
            "department": "Knowledge", "departments": ["Knowledge"], "agents": ["Knowledge Agent"],
            "tools": ["search_knowledge"],
            "tool_plan": [{"tool": "search_knowledge", "agent": "Knowledge Agent", "purpose": "Handle a read-only learning/information question; do not create an HR or IT request."}],
            "details": {"query": raw}, "requires_action": False,
        }

    # A plain network/software/device symptom asks for guidance by default;
    # employees can explicitly request a ticket if self-help does not resolve it.
    has_ticket_action = bool(re.search(r"\b(?:create|raise|open|submit|report)\b.{0,40}\b(?:ticket|incident|request)\b|\b(?:ticket|incident)\b.{0,40}\b(?:create|raise|open|submit|report)\b", lowered))
    has_technical_symptom = bool(re.search(
        r"\b(network|internet|wi.?fi|vpn|connectivity|printer|scanner|projector|software|laptop|computer|system|device|application|server|email)\b.{0,65}\b(problem|issue|trouble|not working|not connecting|was not connecting|cannot connect|can't connect|slow|failed|broken|crashing|crashed|error|blue screen|won't start|will not start|keeps disconnecting|not booting)\b|"
        r"\b(problem|issue|trouble|not working|not connecting|was not connecting|cannot connect|can't connect|slow|failed|broken|crashing|crashed|error|blue screen|won't start|will not start|keeps disconnecting|not booting)\b.{0,65}\b(network|internet|wi.?fi|vpn|connectivity|printer|scanner|projector|software|laptop|computer|system|device|application|server|email)\b",
        lowered,
    ))
    if has_technical_symptom and not has_ticket_action and not is_action_request(lowered):
        return {
            "request_category": "information_request", "intent": "it_troubleshooting_guidance",
            "department": "IT", "departments": ["IT"], "agents": ["IT Support Agent"],
            "tools": ["knowledge_base_service"],
            "tool_plan": [{"tool": "knowledge_base_service", "agent": "IT Support Agent", "purpose": "Provide safe troubleshooting guidance and check accessible tenant IT knowledge."}],
            "details": {"query": raw, "problem": raw}, "requires_action": False,
        }

    # Ticket IDs explicitly requested by the employee are read-only unless
    # they also ask to create/open/raise a new ticket.
    id_match = re.search(r"\bIT-[A-Z0-9-]{6,}\b", raw, re.IGNORECASE)
    creates_new = bool(re.search(r"\b(?:create|raise|open|submit|report)\b", lowered))
    if id_match and not creates_new:
        return {
            "request_category": "information_request", "intent": "it_ticket_status",
            "department": "IT", "departments": ["IT"], "agents": ["IT Support Agent"],
            "tools": ["create_ticket"],
            "tool_plan": [{"tool": "create_ticket", "agent": "IT Support Agent", "purpose": "Retrieve the requested IT ticket status."}],
            "details": {"ticket_id": id_match.group(0).upper(), "read_only_follow_up": True}, "requires_action": False,
        }

    # Payroll/salary clarification questions should remain read-only and route
    # to HR context rather than become an accidental submission.
    payroll_information_question = (
        not is_action_request(lowered)
        and bool(re.search(r"\b(?:question about|explain|help understanding|what are|why was|how does|how are)\b", lowered))
        and bool(re.search(r"\b(?:payslip|pay slip|salary deductions?|tax deductions?|payroll|compensation|bonus|salary credit)\b", lowered))
    )
    if payroll_information_question:
        return {
            "request_category": "information_request", "intent": "payroll_compensation_information",
            "department": "HR", "departments": ["HR"], "agents": ["HR Agent"],
            "tools": ["hr_policy_service"],
            "tool_plan": [{"tool": "hr_policy_service", "agent": "HR Agent", "purpose": "Answer a read-only payroll/compensation question from configured policy or approved employee information."}],
            "details": {"query": raw, "information_only": True}, "requires_action": False,
        }

    # Read-only employee record lookups are often phrased as commands
    # ("show performance", "list my leave requests") rather than questions.
    # Resolve them before the HR service-request fallback so they never become
    # approval items merely because the text contains an HR keyword.
    query_verb = bool(re.match(
        r"^\s*(?:show|list|display|view|retrieve|get|check|find)\b", lowered
    ))
    personal_lookup = bool(re.match(
        r"^\s*(?:my|our)\s+(?:latest\s+|previous\s+|past\s+)?"
        r"(?:performance(?:\s+review)?|leave\s+(?:requests?|history|balance)|"
        r"attendance(?:\s+(?:record|history|status))?|tickets?|ticket\s+status|"
        r"employee\s+profile|profile|payslip|pay\s+slip)\b", lowered
    ))
    is_record_lookup = (query_verb or personal_lookup) and not is_action_request(lowered)
    if is_record_lookup:
        if re.search(r"\bperformance(?:\s+review|\s+record|\s+for)?\b", lowered):
            return {
                "request_category": "information_request", "intent": "performance_information",
                "department": "HR", "departments": ["HR"], "agents": ["HR Agent"],
                "tools": ["performance_service"],
                "tool_plan": [{"tool": "performance_service", "agent": "HR Agent", "purpose": "Retrieve authorized, company-scoped performance information without creating an approval request."}],
                "details": {"query": raw, "information_only": True}, "requires_action": False,
            }
        if re.search(r"\b(?:leave\s+(?:requests?|history|balance)|time\s+off\s+balance|leave\s+records?)\b", lowered):
            return {
                "request_category": "information_request", "intent": "leave_information",
                "department": "HR", "departments": ["HR"], "agents": ["HR Agent"],
                "tools": ["leave_management"],
                "tool_plan": [{"tool": "leave_management", "agent": "HR Agent", "purpose": "Retrieve the authenticated employee's saved leave history or balance."}],
                "details": {"query": raw, "information_only": True, "read_only_follow_up": True}, "requires_action": False,
            }
        if re.search(r"\b(?:ticket|tickets|incident|incidents|my\s+it\s+requests?)\b", lowered):
            return {
                "request_category": "information_request", "intent": "it_ticket_history",
                "department": "IT", "departments": ["IT"], "agents": ["IT Support Agent"],
                "tools": ["create_ticket"],
                "tool_plan": [{"tool": "create_ticket", "agent": "IT Support Agent", "purpose": "Retrieve saved IT tickets belonging to the authenticated employee."}],
                "details": {"query": raw, "read_only_follow_up": True}, "requires_action": False,
            }
        if re.search(r"\battendance\b", lowered):
            return {
                "request_category": "information_request", "intent": "attendance_information",
                "department": "HR", "departments": ["HR"], "agents": ["HR Agent"],
                "tools": ["attendance_service"],
                "tool_plan": [{"tool": "attendance_service", "agent": "HR Agent", "purpose": "Retrieve authorized attendance information without submitting a correction request."}],
                "details": {"query": raw, "information_only": True}, "requires_action": False,
            }

    read_question = bool(QUESTION_ONLY_RE.search(lowered)) and not is_action_request(lowered)
    if not read_question:
        return None

    if re.search(r"\b(leave policy|annual leave policy|vacation policy|leave allowance|who approves leave|how to apply for leave|how do i apply for leave|how can i apply for leave|leave application process|leave request procedure|work from home (?:policy|rules|guidelines)|remote work (?:policy|rules|guidelines)|remote working rules|wfh (?:policy|rules)|dress code|holiday calendar|company holidays|flexible work policy|employee policy|hr policy)\b", lowered):
        tool, agent, area, intent = "hr_policy_service", "HR Agent", "HR", "hr_policy_information"
    elif re.search(r"\b(leave balance|how many leave|leave days|time off balance|my leave history)\b", lowered):
        tool, agent, area, intent = "leave_management", "HR Agent", "HR", "leave_information"
    elif re.search(r"\b(my (?:it )?tickets?|my (?:it )?ticket\b|ticket history|ticket status|status of (?:my )?ticket|track (?:my )?ticket|show .*tickets?)\b", lowered):
        tool, agent, area, intent = "create_ticket", "IT Support Agent", "IT", "it_ticket_history"
    elif re.search(r"\b(network|internet|wi.?fi|vpn|connectivity|printer|software).{0,45}\b(problem|issue|trouble|not working|slow|failed)\b|\b(problem|issue|trouble|not working|slow|failed)\b.{0,45}\b(network|internet|wi.?fi|vpn|connectivity|printer|software)\b", lowered):
        tool, agent, area, intent = "knowledge_base_service", "IT Support Agent", "IT", "it_troubleshooting_guidance"
    elif re.search(r"\b(benefits?|insurance|wellness|gym membership|employee perks)\b", lowered):
        tool, agent, area, intent = "benefits_service", "HR Agent", "HR", "benefits_information"
    elif re.search(r"\b(password|mfa|2fa|otp|authenticator|network|internet|wi.?fi|vpn|software installation|install software|printer|scanner|projector|backup|data recovery|file restore|account access|email setup)\b", lowered):
        tool, agent, area, intent = "knowledge_base_service", "IT Support Agent", "IT", "it_support_guidance"
    else:
        tool, agent, area, intent = "search_knowledge", "Knowledge Agent", "Knowledge", "general_information"

    routed_details = {"query": raw}
    if tool == "create_ticket":
        routed_details["read_only_follow_up"] = True
        if id_match:
            routed_details["ticket_id"] = id_match.group(0).upper()
    return {
        "request_category": "information_request", "intent": intent,
        "department": area, "departments": [area], "agents": [agent],
        "tools": [tool], "tool_plan": [{"tool": tool, "agent": agent, "purpose": "Answer a read-only employee question using the appropriate service."}],
        "details": routed_details,
        "requires_action": False,
    }
