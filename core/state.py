from typing import Any, Dict, List
from typing_extensions import TypedDict


class WorkflowState(TypedDict, total=False):

    raw_message: str
    workflow_id: str

    company_id: str
    user_id: str
    user_role: str
    company_context: Dict[str, Any]

    conversation_history: List[Dict[str, Any]]

    analysis: Dict[str, Any]

    request_category: str
    request_type: str
    intent: str

    extracted_details: Dict[str, Any]
    details: Dict[str, Any]

    requires_action: bool
    confidence: float

    confirmation_requested: bool
    confirmation_received: bool

    department: str
    departments: List[str]

    assigned_agent: str
    assigned_agents: List[str]

    agent_results: List[Dict[str, Any]]

    tools: List[str]
    tool_plan: List[Dict[str, Any]]

    selected_tool: str
    tool_names: List[str]

    tool_input: Dict[str, Any]

    tool_result: Any
    tool_results: List[Dict[str, Any]]

    validation: Dict[str, Any]

    policy_evaluation: Dict[str, Any]

    decision: Any

    response: str

    trace: List[Dict[str, Any]]
