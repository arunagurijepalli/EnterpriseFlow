"""
Knowledge Agent
---------------
Handles enterprise knowledge and company-document search.

The Knowledge Agent does not contain hardcoded answers.
It executes the search tool selected by the planning/coordinator layer.
"""

from typing import Any, Dict, List

from core.tool_executor import execute_tool, execute_tools


AGENT_NAME = "Knowledge Agent"
DEPARTMENT = "Knowledge"


def run_knowledge_agent(
    request: str,
    tools: List[str] | None = None,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Execute the knowledge-search tools selected by the workflow.
    """

    tools = tools or []
    details = details or {}

    if not tools:
        return {
            "agent": AGENT_NAME,
            "department": DEPARTMENT,
            "status": "no_tools",
            "results": [],
            "message": (
                "No knowledge-search tool was selected "
                "for this request."
            ),
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


def run_single_knowledge_tool(
    tool_name: str,
    request: str,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Execute one knowledge-search tool."""

    return execute_tool(
        tool_name=tool_name,
        details=details or {},
        message=request,
    )
