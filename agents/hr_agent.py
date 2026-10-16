"""
HR Agent
--------
Handles HR-related enterprise requests by executing tools selected
by the planning/LLM layer.
"""

from typing import Any, Dict, List

from core.tool_executor import execute_tool, execute_tools


AGENT_NAME = "HR Agent"
DEPARTMENT = "HR"


def run_hr_agent(
    request: str,
    tools: List[str] | None = None,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Execute the tools selected for an HR request.

    The HR agent does not decide based on hardcoded user questions.
    Tool selection comes from the workflow planning stage.
    """

    tools = tools or []
    details = details or {}

    if not tools:
        return {
            "agent": AGENT_NAME,
            "department": DEPARTMENT,
            "status": "no_tools",
            "results": [],
            "message": "No HR tool was selected for this request.",
        }

    results = execute_tools(
        tool_names=tools,
        details=details,
        message=request,
    )

    return {
        "agent": AGENT_NAME,
        "department": DEPARTMENT,
        "status": "completed",
        "results": results,
    }


def run_single_hr_tool(
    tool_name: str,
    request: str,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Execute one HR tool."""

    return execute_tool(
        tool_name=tool_name,
        details=details or {},
        message=request,
    )