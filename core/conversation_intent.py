"""Small deterministic helpers for separating new tasks from slot answers."""
from __future__ import annotations

import re

_PENDING_LOOKUP = re.compile(
    r"\b(?:my\s+pending\s+(?:approvals?|requests?)|pending\s+approvals?|"
    r"requests?\s+(?:waiting|awaiting)\s+(?:for\s+)?approval|"
    r"approval\s+queue|approvals?\s+assigned\s+to\s+me|show\s+(?:my\s+)?approvals?)\b",
    re.IGNORECASE,
)

_TOPIC_PATTERNS = {
    "it_network": r"\b(?:wi.?fi|wifi|network|internet|vpn|connectivity)\b",
    "it_software": r"\b(?:software|install\s+python|install\s+java|application access|license|licence)\b",
    "it_access": r"\b(?:password|mfa|2fa|otp|authenticator|account locked|login access)\b",
    "it_recovery": r"\b(?:deleted files?|data recovery|backup restore|recover(?:y|ing)? files?)\b",
    "it_security": r"\b(?:phishing|malware|security incident|ransomware|data leak)\b",
    "it_hardware": r"\b(?:laptop|workstation|mouse|keyboard|monitor|printer|scanner|projector|device)\b",
    "pending": r"\b(?:pending approvals?|pending requests?|approval queue|awaiting approval|my requests)\b",
    "hr_policy": r"\b(?:policy|policies|leave allowance|who approves|holiday calendar|work from home rules)\b",
    "hr_attendance": r"\b(?:attendance|missed punch|clock in|clock out)\b",
    "hr_training": r"\b(?:training|course|certification|upskilling)\b",
    "hr_benefits": r"\b(?:benefits?|insurance|wellness|gym membership)\b",
    "hr_grievance": r"\b(?:grievance|harassment|workplace complaint|ethics violation|whistleblower)\b",
    "hr_relocation": r"\b(?:relocation|relocate|office transfer|transfer to another office|work location transfer)\b",
    "hr_payroll": r"\b(?:payroll|payslip|pay slip|salary|compensation|bonus|tax declaration)\b",
    "hr_documents": r"\b(?:employment letter|employment verification|salary certificate|experience certificate|visa letter)\b",
    "hr_leave": r"\b(?:leave|vacation|time off|sick leave|annual leave|maternity leave|paternity leave)\b",
    "projects": r"\b(?:project submission|submit a project|project folder|project files)\b",
    "documents": r"\b(?:document exchange|upload a document|send a document|download a document)\b",
    "profile": r"\b(?:profile picture|profile photo|update my profile|my profile)\b",
}

_READ_OR_NEW_TASK_PREFIX = re.compile(
    r"^\s*(?:hi|hello|hey|good morning|good afternoon|good evening)\b|"
    r"^\s*(?:what\s+is|where\s+(?:is|do|can)|who\s+approves|show\s+me|list\s+my|"
    r"check\s+my|my\s+pending|pending\s+approvals|my\s+requests)\b",
    re.IGNORECASE,
)

_EXPLICIT_NEW_ACTION = re.compile(
    r"^\s*(?:i\s+(?:need|want|would like)|please|create|open|raise|submit|report|"
    r"request|install|reset|recover|restore|correct|update|remove|revoke|enrol|enroll)\b",
    re.IGNORECASE,
)

_DATE_OR_SLOT_ONLY = re.compile(
    r"^\s*(?:"
    r"\d{1,2}[-/]\d{1,2}[-/]20\d{2}(?:\s*(?:,|and|&|to|through|until)\s*\d{1,2}[-/]\d{1,2}[-/]20\d{2})?"
    r"|next\s+week|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|(?:sick|annual|casual|personal|unpaid|maternity|paternity|parental)\s+leave"
    r"|(?:two|three|four|five|\d+)\s+days?"
    r"|(?:personal|medical|family|emergency)\s+reasons?"
    r")\s*$",
    re.IGNORECASE,
)

def pending_lookup_requested(message: str) -> bool:
    """True when a message explicitly asks to list pending approvals/requests."""
    return bool(_PENDING_LOOKUP.search(str(message or "").strip()))


def _topics(text: str) -> set[str]:
    value = str(text or "")
    return {name for name, pattern in _TOPIC_PATTERNS.items() if re.search(pattern, value, re.IGNORECASE)}


def is_clear_new_request_during_clarification(message: str, previous_request: str = "") -> bool:
    """Avoid attaching a new domain request to an unrelated pending slot question."""
    text = str(message or "").strip()
    previous = str(previous_request or "").strip()
    if not text:
        return False
    if pending_lookup_requested(text):
        return True
    if _DATE_OR_SLOT_ONLY.match(text):
        return False
    if _READ_OR_NEW_TASK_PREFIX.search(text):
        return True

    current_topics = _topics(text)
    previous_topics = _topics(previous)
    previous_is_generic_ticket_prompt = bool(re.search(
        r"\b(?:create|creat|cretae|make|raise|open|submit|log|file)\b.{0,55}\bticket\b",
        previous, re.IGNORECASE,
    )) and not bool(re.search(
        r"\b(?:wi.?fi|network|internet|vpn|printer|scanner|projector|laptop|computer|software|password|mfa|email|device)\b",
        previous, re.IGNORECASE,
    ))
    current_is_symptom_detail = bool(current_topics & {"it_network", "it_software", "it_access", "it_recovery", "it_security", "it_hardware"}) and not bool(_EXPLICIT_NEW_ACTION.search(text))
    if previous_is_generic_ticket_prompt and current_is_symptom_detail:
        return False
    # A topic change (e.g. leave dates -> Wi-Fi issue) is a new request even if short.
    if current_topics and current_topics - previous_topics:
        return True

    # Explicit complete action sentences usually start a new task; short slot values
    # (like "sick leave" or dates) are preserved above.
    if _EXPLICIT_NEW_ACTION.search(text) and len(text.split()) >= 4:
        return True
    return False


def is_simple_greeting(message: str) -> bool:
    return bool(re.fullmatch(
        r"\s*(?:hi|hello|hey|hiya|good morning|good afternoon|good evening)[!.\s]*",
        str(message or ""), re.IGNORECASE,
    ))
