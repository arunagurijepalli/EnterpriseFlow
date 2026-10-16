"""Pure helpers for safe handling of user replies to pending actions."""
from __future__ import annotations

import re
from typing import Any, Dict

_CONFIRMATION_REPLIES = {
    "yes", "yes proceed", "yes please", "yes please proceed", "proceed",
    "confirm", "confirmed", "go ahead", "okay", "ok", "okay proceed",
    "ok proceed", "yes go ahead", "please proceed", "confirm action",
}
_CANCELLATION_REPLIES = {
    "no", "no cancel", "no thanks", "cancel", "cancel it", "cancel this",
    "cancel request", "cancel the request", "do not proceed", "dont proceed",
    "stop", "never mind", "nevermind", "do not submit", "dont submit",
}


def normalize_confirmation_reply(message: str) -> str:
    """Normalize punctuation/spacing without fuzzy-matching confirmations."""
    value = str(message or "").casefold().strip()
    value = value.replace("’", "'")
    value = re.sub(r"[^\w\s']+", " ", value)
    value = value.replace("'", "")
    return " ".join(value.split())


def is_pending_confirmation_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    validation = result.get("validation")
    decision = result.get("decision")
    validation = validation if isinstance(validation, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    return (
        str(validation.get("status") or "").casefold() == "pending_confirmation"
        or bool(decision.get("confirmation_required"))
    )


def classify_pending_confirmation_reply(message: str, result: Any) -> str:
    """Return confirm, cancel, hold, or new_request for the current reply."""
    if not is_pending_confirmation_result(result):
        return "new_request"
    normalized = normalize_confirmation_reply(message)
    if normalized in _CONFIRMATION_REPLIES:
        return "confirm"
    if normalized in _CANCELLATION_REPLIES:
        return "cancel"
    return "hold"


def hold_pending_confirmation_result(previous_result: Dict[str, Any]) -> Dict[str, Any]:
    """Answer a follow-up without losing or executing the pending action."""
    result = dict(previous_result)
    validation = result.get("validation")
    validation = dict(validation) if isinstance(validation, dict) else {}
    decision = result.get("decision")
    decision = dict(decision) if isinstance(decision, dict) else {}

    original_request = str(result.get("raw_message") or "the requested action").strip()
    tools = result.get("tool_names") or result.get("tools") or []
    if not tools and isinstance(result.get("tool_plan"), list):
        tools = [item.get("tool") for item in result["tool_plan"] if isinstance(item, dict)]
    tool_names = {str(tool or "").casefold() for tool in tools}
    intent = str(result.get("intent") or "").casefold()
    departments = result.get("departments") or []
    department_text = " ".join(str(x) for x in departments).casefold()

    if "create_ticket" in tool_names or "it" in department_text or intent.startswith("data_recovery"):
        action_label = "IT support ticket"
        not_created = "No IT ticket has been created yet, so there is no ticket ID to view."
    elif "hr" in department_text or "hr_general_request_service" in tool_names:
        action_label = "HR request"
        not_created = "The HR request has not been submitted yet."
    else:
        action_label = "requested action"
        not_created = "The action has not been executed or submitted yet."

    result["response"] = (
        f"{not_created} Your {action_label} for '{original_request}' is still waiting for your confirmation. "
        "Reply 'Yes, proceed' to confirm and continue, or 'No, cancel' to cancel it. "
        "I have kept the pending action unchanged."
    )
    result["validation"] = validation
    result["decision"] = decision
    trace = list(result.get("trace") or [])
    trace.append({
        "stage": "pending_confirmation_guard",
        "message": "A non-confirmation reply was handled without running a new workflow or executing the pending action.",
    })
    result["trace"] = trace
    return result
