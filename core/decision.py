from typing import Any, Dict, List


def make_decision(
    tool_results: List[Dict[str, Any]],
    validation: Dict[str, Any],
    request_details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Deterministic enterprise decision engine.

    The decision is based on validated tool results,
    not on invented LLM information.
    """

    request_details = request_details or {}

    # --------------------------------------------------------
    # Validation failure
    # --------------------------------------------------------

    if not validation.get("valid", False):

        return {
            "decision": "HUMAN_REVIEW",
            "reason": "Tool validation failed.",
            "action": "Escalate the request for human review.",
        }

    # --------------------------------------------------------
    # Inspect tool results
    # --------------------------------------------------------

    for tool_result in tool_results:

        result = tool_result.get("result", {})

        if not isinstance(result, dict):
            continue

        # ----------------------------------------------------
        # Budget decision
        # ----------------------------------------------------

        if "within_budget" in result:

            if not result["within_budget"]:

                return {
                    "decision": "HUMAN_REVIEW",
                    "reason": "Requested amount exceeds available budget.",
                    "action": "Finance approval is required.",
                }

            if result.get("requires_approval"):

                return {
                    "decision": "HUMAN_REVIEW",
                    "reason": "Request is within budget but requires approval.",
                    "action": "Send the request for finance approval.",
                }

        # ----------------------------------------------------
        # Inventory decision
        # ----------------------------------------------------

        if "available" in result:

            if result["available"] is False:

                return {
                    "decision": "HUMAN_REVIEW",
                    "reason": "Requested item is not currently available.",
                    "action": "Check alternatives or contact procurement.",
                }

        # ----------------------------------------------------
        # Payment / reimbursement
        # ----------------------------------------------------

        status_detail = str(
            result.get("status_detail", "")
        ).lower()

        if status_detail in {
            "failed",
            "rejected",
            "blocked",
        }:

            return {
                "decision": "HUMAN_REVIEW",
                "reason": f"Enterprise service reports status: {status_detail}.",
                "action": "Finance team review is required.",
            }

    # --------------------------------------------------------
    # Default successful action
    # --------------------------------------------------------

    return {
        "decision": "CONTINUE",
        "reason": "All required enterprise checks passed.",
        "action": "Proceed with the requested workflow.",
    }