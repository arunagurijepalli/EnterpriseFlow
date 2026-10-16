from typing import Any, Dict, List


def validate_tool_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the result returned by one enterprise tool.
    """

    if not result:
        return {
            "status": "failed",
            "valid": False,
            "message": "Tool returned no result.",
        }

    if result.get("status") == "error":
        return {
            "status": "failed",
            "valid": False,
            "message": result.get("message", "Tool execution failed."),
        }

    actual_result = result.get("result")

    if actual_result is None:
        return {
            "status": "failed",
            "valid": False,
            "message": "Tool returned an empty result.",
        }

    if isinstance(actual_result, dict):
        if actual_result.get("status") in {"error", "failed"}:
            return {
                "status": "failed",
                "valid": False,
                "message": actual_result.get(
                    "message",
                    "Enterprise tool reported failure."
                ),
            }

    return {
        "status": "passed",
        "valid": True,
        "message": "Tool result validated successfully.",
    }


def validate_tool_results(
    results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Validate all tool results from a multi-tool workflow.
    """

    if not results:
        return {
            "status": "failed",
            "valid": False,
            "message": "No tool results were produced.",
            "checks": [],
        }

    checks = []

    for result in results:
        check = validate_tool_result(result)

        checks.append({
            "tool": result.get("executed_tool", result.get("requested_tool")),
            **check,
        })

    failed = [
        check for check in checks
        if not check["valid"]
    ]

    if failed:
        return {
            "status": "failed",
            "valid": False,
            "message": "One or more enterprise tools failed validation.",
            "checks": checks,
        }

    return {
        "status": "passed",
        "valid": True,
        "message": "All enterprise tool results validated successfully.",
        "checks": checks,
    }