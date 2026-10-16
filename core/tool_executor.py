from typing import Any, Dict, List

from tools.registry import (
    get_tool,
    get_tool_description,
    list_tools,
)


# ============================================================
# TOOL ALIASES
# ============================================================

TOOL_ALIASES = {

    # ---------------- FINANCE ----------------

    "get_reimbursement_status": "payment_service",
    "search_expense_claims": "expense_service",
    "check_budget_allowance": "budget_service",
    "check_budget": "budget_service",
    "payment_status": "payment_service",

    # ---------------- PROCUREMENT ----------------

    "check_hardware_inventory": "inventory_check",
    "hardware_catalog_lookup": "hardware_catalog",
    "get_hardware_catalog": "hardware_catalog",
    "inventory_check_api": "inventory_check",
    "requisition_submission_tool": "purchase_request",

    "submit_purchase_request": "purchase_request",
    "create_purchase_order": "purchase_order",
    "check_vendor": "vendor_service",

    # ---------------- HR ----------------

    "employee_info": "employee_information",
    "employee_information": "employee_information",
    "leave_request": "leave_management",
    "leave_balance": "leave_management",
    "attendance_check": "attendance_service",
    "hr_policy": "hr_policy_service",

    # ---------------- IT ----------------

    "create_it_ticket": "create_ticket",
    "support_ticket": "create_ticket",
    "device_diagnosis": "device_service",
    "password_reset": "password_access_service",
    "software_support": "software_service",

    # ---------------- KNOWLEDGE ----------------

    "knowledge_search": "search_knowledge",
    "search_knowledge_base": "search_knowledge",
}


# ============================================================
# BUSINESS ACTION TOOLS
# ============================================================
#
# These tools can change enterprise/business state.
#
# They require explicit confirmation from the user before
# execution.
# ============================================================

ACTION_TOOLS = {
    "purchase_request",
    "purchase_order",
    "create_ticket",
    "leave_management",
    "expense_service",
    "interview_service",
    "job_requisition_service",
    "send_email",
    "hr_general_request_service",
    "hr_grievance_service",
    "hr_training_service",
    "employee_document_service",
    "benefits_service",
    "device_service",
    "password_access_service",
    "software_service",
}


# ============================================================
# CONFIRMATION PHRASES
# ============================================================

CONFIRMATION_PHRASES = {
    # Deliberately limited to standalone confirmation replies. Phrases such as
    # "please submit" or "create the purchase order" are action requests, not
    # confirmation, and must never bypass the pending-confirmation state.
    "yes", "yes please", "yes proceed", "yes please proceed", "proceed",
    "proceed please", "go ahead", "go ahead please", "do it", "confirm",
    "confirmed", "i confirm", "i approve", "okay", "ok", "okay proceed",
    "ok proceed", "yes go ahead", "confirm action",
}


# ============================================================
# EXPLICIT CONFIRMATION DETECTION
# ============================================================

def has_explicit_confirmation(message: str) -> bool:
    """Return true only for a standalone confirmation reply.

    This helper does not execute anything by itself. The actual tool guard
    additionally requires ``confirmed=True`` from resume_workflow, because a
    message that merely contains "yes" or "please submit" is not proof that
    the UI was waiting for confirmation.
    """
    import re

    normalized = str(message or "").casefold().strip()
    normalized = normalized.replace("’", "'")
    normalized = re.sub(r"[^\w\s']+", " ", normalized)
    normalized = normalized.replace("'", "")
    normalized = " ".join(normalized.split())
    return normalized in CONFIRMATION_PHRASES


# ============================================================
# TOOL NAME RESOLUTION
# ============================================================

def resolve_tool_name(tool_name: str) -> str:
    """
    Resolve an AI-selected tool name or alias into the actual
    registered executable tool.
    """

    if not tool_name:
        return ""

    normalized = str(tool_name).strip()

    # Direct registered tool
    if normalized in list_tools():
        return normalized

    # Alias
    alias = TOOL_ALIASES.get(normalized)

    if alias:
        return alias

    # Case-insensitive lookup
    lowered = normalized.lower()

    for registered_name in list_tools():

        if registered_name.lower() == lowered:
            return registered_name

    for alias_name, actual_name in TOOL_ALIASES.items():

        if alias_name.lower() == lowered:
            return actual_name

    return ""


# ============================================================
# CHECK ACTION PERMISSION
# ============================================================
def can_execute_action_tool(
    tool_name: str,
    details: Dict[str, Any],
    message: str,
    confirmed: bool = False,
) -> bool:
    """
    Determine whether an action tool can execute.

    Read-only tools can execute automatically.

    Business-changing tools require explicit confirmation.

    confirmed=True is used only by the explicit
    confirmation/resume flow after the user has
    confirmed the pending action.
    """

    actual_name = resolve_tool_name(tool_name)

    if not actual_name:
        return False

    # Read-only / informational tool
    if actual_name not in ACTION_TOOLS:
        return True

    # IT ticket history and ID/status lookups are read-only even though the
    # same tool can create tickets. A contextual follow-up may carry an ID in
    # details rather than in the current short message.
    if actual_name == "create_ticket":
        import re
        normalized_message = " ".join(str(message or "").casefold().split())
        if details.get("read_only_follow_up") and details.get("ticket_id"):
            return True
        read_only_ticket_query = (
            bool(re.search(r"\b(?:show|list|display|view|retrieve|get|check|find|track|where)\b", normalized_message))
            and bool(re.search(r"\b(?:ticket|tickets|incident|incidents|history|status)\b", normalized_message))
            and not bool(re.search(r"\b(?:create|raise|open|submit|report|file)\b", normalized_message))
        )
        if read_only_ticket_query:
            return True

    # Benefits service can retrieve the catalog or create an enrollment.
    # Only the enrollment path is a business action.
    if actual_name == "benefits_service":
        import re
        normalized_message = " ".join(str(message or "").casefold().split())
        enrollment_intent = bool(re.search(
            r"\b(?:enroll|enrollment|sign up|add me|add my family|change my benefits|apply for benefits)\b",
            normalized_message,
        ))
        if not enrollment_intent and (
            "?" in normalized_message
            or normalized_message.startswith(("what ", "which ", "do we have ", "does our company ", "are ", "is ", "tell me about ", "show me "))
            or any(term in normalized_message for term in ("available benefits", "benefits information", "list of benefits"))
        ):
            return True

    # Existing HR request history is read-only; new HR requests require confirmation.
    if actual_name == "hr_general_request_service":
        import re

        normalized_message = " ".join(str(message or "").casefold().split())
        read_only_history = (
            bool(re.search(
                r"\b(?:show|list|display|view|retrieve|get|check|find)\b",
                normalized_message,
            ))
            and bool(re.search(r"\b(?:hr\s+)?requests?\b", normalized_message))
            and bool(re.search(
                r"\b(?:history|status|approval|approved|rejected|pending|records?)\b",
                normalized_message,
            ))
        )
        if read_only_history:
            return True

        negative_write = bool(re.search(
            r"\b(?:do not|don't|dont|never)\b.{0,120}\b(?:submit|create|raise|open|file|apply|modify|change|update|cancel|approve|delete)\b",
            normalized_message,
        ))
        if negative_write:
            return False
        # A new request must not self-confirm by containing words like
        # "please submit". Only resume_workflow can pass confirmed=True.
        return bool(confirmed)
    # The leave tool also serves authenticated read-only queries. Do not
    # ask employees to confirm before retrieving their own balance/history.
    if actual_name == "leave_management":
        normalized_message = " ".join(str(message or "").lower().split())
        has_read_intent = any(
            term in normalized_message
            for term in ("balance", "history", "status", "approved", "rejected", "pending", "how many leaves", "how much leave", "leave days", "how many leave", "time off balance")
        )
        has_write_intent = any(
            term in normalized_message
            for term in ("apply", "request", "submit", "book", "take leave", "day off", "cancel", "want leave", "need leave", "want to take", "need to take", "time off")
        )
        if has_read_intent and not has_write_intent:
            return True
        # A direct, authenticated leave request is already an explicit
        # employee action. Ask for missing dates first, then submit once they
        # are supplied instead of requiring a redundant second confirmation.
        if has_write_intent:
            # Write actions must pass the same confirmation gate as other tools.
            return bool(confirmed)

    # Explicit confirmation/resume path
    if confirmed:
        return True

    # Never infer confirmation from the original action text. A stateful,
    # authenticated resume path must be the source of confirmed=True.
    return False


# ============================================================
# NORMALIZE TOOL RESULT
# ============================================================

def normalize_tool_result(
    tool_name: str,
    result: Any,
) -> Dict[str, Any]:
    """
    Convert the raw tool output into a predictable structure.

    IMPORTANT:
    A None result is NOT considered successful.
    """

    # --------------------------------------------------------
    # Tool returned nothing
    # --------------------------------------------------------

    if result is None:
        return {
            "status": "no_result",
            "executed": False,
            "tool": tool_name,
            "result": None,
            "message": (
                f"The tool '{tool_name}' executed but "
                f"returned no result."
            ),
        }

    # --------------------------------------------------------
    # Tool already returned a structured dictionary
    # --------------------------------------------------------

    if isinstance(result, dict):

        normalized = dict(result)

        if "status" not in normalized:
            normalized["status"] = "success"

        if "executed" not in normalized:
            normalized["executed"] = True

        normalized["tool"] = tool_name

        return normalized

    # --------------------------------------------------------
    # Normal text / number / list result
    # --------------------------------------------------------

    return {
        "status": "success",
        "executed": True,
        "tool": tool_name,
        "result": result,
    }


# ============================================================
# EXECUTE ONE TOOL
# ============================================================
def execute_tool(
    tool_name: str,
    details: Dict[str, Any],
    message: str,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Safely execute one enterprise tool.

    confirmed=True is allowed only when the workflow is
    being resumed after an explicit user confirmation.
    """

    actual_name = resolve_tool_name(tool_name)

    # --------------------------------------------------------
    # Tool not found
    # --------------------------------------------------------

    if not actual_name:

        return {
            "status": "error",
            "requested_tool": tool_name,
            "executed_tool": "",
            "executed": False,
            "message": (
                f"No registered tool found for "
                f"'{tool_name}'."
            ),
        }

    # --------------------------------------------------------
    # Get tool
    # --------------------------------------------------------

    tool = get_tool(actual_name)

    if tool is None:

        return {
            "status": "error",
            "requested_tool": tool_name,
            "executed_tool": actual_name,
            "executed": False,
            "message": (
                f"Tool '{actual_name}' is unavailable."
            ),
        }

    # --------------------------------------------------------
    # Safety gate
    # --------------------------------------------------------

    # Ask for required inputs before asking for confirmation. These checks
    # are read-only and return before an action can change business state.
    import re
    context = details if isinstance(details, dict) else {}
    if not confirmed and actual_name == "purchase_request":
        has_purpose = any(
            str(context.get(key) or "").strip()
            for key in ("use_case", "purpose", "justification", "model", "item")
        )
        has_described_use = bool(
            re.search(
                r"\b(for\s+\w+|developer|development|design|engineering|ai|machine learning)\b",
                str(message or ""),
                re.IGNORECASE,
            )
        )
        if not has_purpose and not has_described_use:
            return {
                "status": "missing_information",
                "executed": False,
                "tool": actual_name,
                "requested_tool": tool_name,
                "request_status": "not_submitted",
                "message": (
                    "What will you use the laptop for, or which available "
                    "model would you like? No purchase request has been created."
                ),
            }

    if not confirmed and actual_name == "create_ticket":
        service_type = str(context.get("service_request_type") or context.get("category") or "").casefold()
        normalized_text = str(message or "").casefold()
        generic_ticket_action = service_type == "it_general_request" and bool(re.search(
            r"\b(?:create|creat|cretae|make|raise|open|submit|log|file)\b.{0,55}\bticket\b",
            normalized_text,
        ))
        issue_text = " ".join(str(context.get(key) or "") for key in ("issue", "problem", "symptom", "affected_system", "description"))
        issue_described = bool(re.search(
            r"\b(?:for|about|regarding|because)\s+(?:my\s+)?(?:wi.?fi|network|internet|vpn|printer|scanner|projector|laptop|computer|software|email|account|password|mfa|monitor|keyboard|mouse|device|application|server|system)\b|"
            r"\b(?:not working|not connecting|broken|crashing|failed|error|slow|won't start|will not start|issue with|problem with|need help with)\b",
            normalized_text + " " + issue_text.casefold(),
        ))
        if generic_ticket_action and not issue_described:
            return {
                "status": "missing_information", "executed": False,
                "tool": actual_name, "requested_tool": tool_name,
                "message": "Please briefly describe the IT issue (for example, 'my office printer is not working'). No ticket has been created yet.",
            }

    if not confirmed and actual_name == "leave_management":
        text = str(message or "").casefold()
        important = context.get("important") if isinstance(context.get("important"), dict) else {}
        action_intent = bool(
            context.get("request_action")
            or re.search(
                r"\b(?:apply|request|submit|book|take|cancel|want|need|schedule|create|start)\b.{0,45}\b(?:leave|vacation|time off|day off)\b|\b(?:leave|vacation|time off)\s+request\b",
                text,
            )
            or re.search(r"\b(?:apply|request|submit|book|take|cancel|want|need|schedule)\b", text)
        )
        has_dates = bool(
            (context.get("start_date") or important.get("start_date"))
            and (context.get("end_date") or important.get("end_date"))
        )
        if action_intent and not has_dates:
            return {
                "status": "missing_information",
                "executed": False,
                "tool": actual_name,
                "requested_tool": tool_name,
                "message": (
                    "Please provide the leave start date and end date. "
                    "No leave request has been submitted."
                ),
            }
        if action_intent and has_dates:
            reason = str(context.get("reason") or important.get("reason") or "").strip()
            if not reason:
                additional = re.findall(r"Additional information:\s*(.+)", str(message or ""), re.IGNORECASE)
                for candidate in reversed(additional):
                    candidate = candidate.strip()
                    if candidate and not re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]20?\d{2}(?:\s*(?:,|and|&)\s*\d{1,2}[-/]\d{1,2}[-/]20?\d{2})?", candidate):
                        reason = candidate
                        break
            if not reason and not re.search(
                r"\bfor\s+(?:my\s+)?(?:personal|medical|health|family|emergency|vacation|wedding)\s+(?:reasons?|leave|purposes?|function|event)\b",
                text,
            ):
                return {
                    "status": "missing_information", "executed": False,
                    "tool": actual_name, "requested_tool": tool_name,
                    "message": "What is the purpose of your leave? No leave request has been submitted yet.",
                }

    if not confirmed and actual_name == "expense_service":
        text = str(message or "")
        has_amount_in_text = bool(
            re.search(
                r"\bINR\s*[\d,]+|\b(?:of|for)\s*[\d,]+",
                text,
                re.IGNORECASE,
            )
        ) or (
            chr(0x20B9) in text
            and any(character.isdigit() for character in text)
        )
        if not context.get("amount") and not has_amount_in_text:
            return {
                "status": "missing_information",
                "executed": False,
                "tool": actual_name,
                "requested_tool": tool_name,
                "message": (
                    "Please provide the expense amount before continuing. "
                    "No expense request has been submitted."
                ),
            }

    if not can_execute_action_tool(
        tool_name=actual_name,
        details=details or {},
        message=message,
        confirmed=confirmed,
    ):

        return {
            "status": "pending_confirmation",
            "requested_tool": tool_name,
            "executed_tool": actual_name,
            "action_required": True,
            "executed": False,
            "message": (
                f"'{actual_name}' requires explicit user "
                f"confirmation before execution."
            ),
        }

    # --------------------------------------------------------
    # Execute
    # --------------------------------------------------------

    try:

        result = tool(
            details or {},
            message,
        )

        normalized = normalize_tool_result(
            tool_name=actual_name,
            result=result,
        )

        normalized["requested_tool"] = tool_name
        normalized["executed_tool"] = actual_name
        normalized["confirmation_used"] = confirmed

        return normalized

    except TypeError:

        # ----------------------------------------------------
        # Compatibility fallback:
        # Some older tools accept only message.
        # ----------------------------------------------------

        try:

            result = tool(message)

            normalized = normalize_tool_result(
                tool_name=actual_name,
                result=result,
            )

            normalized["requested_tool"] = tool_name
            normalized["executed_tool"] = actual_name
            normalized["confirmation_used"] = confirmed

            return normalized

        except Exception as exc:

            return {
                "status": "error",
                "requested_tool": tool_name,
                "executed_tool": actual_name,
                "executed": False,
                "message": str(exc),
            }

    except Exception as exc:

        return {
            "status": "error",
            "requested_tool": tool_name,
            "executed_tool": actual_name,
            "executed": False,
            "message": str(exc),
        }

# ============================================================
# EXECUTE MULTIPLE TOOLS
# ============================================================

def execute_tools(
    tool_names: List[str],
    details: Dict[str, Any],
    message: str,
    confirmed: bool = False,
) -> List[Dict[str, Any]]:
    """
    Execute multiple selected tools.

    Normal workflow:
        confirmed=False

    Explicit confirmation/resume workflow:
        confirmed=True
    """

    results: List[Dict[str, Any]] = []

    if not tool_names:
        return results

    for tool_name in tool_names:

        result = execute_tool(
            tool_name=tool_name,
            details=details or {},
            message=message,
            confirmed=confirmed,
        )

        results.append(result)

        status = result.get("status")

        # ----------------------------------------------------
        # Stop on failure
        # ----------------------------------------------------

        if status == "error":
            break

        # ----------------------------------------------------
        # Stop when no result
        # ----------------------------------------------------

        if status == "no_result":
            break

        # ----------------------------------------------------
        # Stop when confirmation is required
        # ----------------------------------------------------

        if status == "pending_confirmation":
            break

    return results


# ============================================================
# TOOL CAPABILITY HELPERS
# ============================================================

def get_available_tool_names() -> List[str]:
    """
    Return all executable enterprise tool names.
    """

    return list_tools()


def get_tool_capability(tool_name: str) -> Dict[str, Any]:
    """
    Return semantic metadata for a tool.
    """

    actual_name = resolve_tool_name(tool_name)

    if not actual_name:
        return {}

    description = get_tool_description(actual_name)

    if not description:
        return {}

    capability = dict(description)

    capability["tool"] = actual_name
    capability["requires_confirmation"] = (
        actual_name in ACTION_TOOLS
    )

    return capability


def get_all_tool_capabilities() -> Dict[str, Dict[str, Any]]:
    """
    Return semantic metadata for every registered tool.
    """

    capabilities = {}

    for tool_name in list_tools():

        capability = get_tool_capability(tool_name)

        if capability:
            capabilities[tool_name] = capability

    return capabilities
