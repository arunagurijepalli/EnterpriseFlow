"""
Recruitment Agent
-----------------
Handles recruitment and talent-acquisition workflows.
"""

from typing import Any, Dict, List

from core.tool_executor import execute_tool, execute_tools


AGENT_NAME = "Recruitment Agent"
DEPARTMENT = "Recruitment"


def run_recruitment_agent(
    request: str,
    tools: List[str] | None = None,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:

    tools = tools or []
    details = details or {}

    if not tools:
        return {
            "agent": AGENT_NAME,
            "department": DEPARTMENT,
            "status": "no_tools",
            "results": [],
            "message": "No recruitment tool was selected for this request.",
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


def run_single_recruitment_tool(
    tool_name: str,
    request: str,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:

    return execute_tool(
        tool_name=tool_name,
        details=details or {},
        message=request,
    )