from typing import Any, Dict, List


# =========================================================
# AGENT ROUTES
# =========================================================

AGENT_ROUTES = {
    "human resources": "HR Agent",
    "hr": "HR Agent",

    "it support": "IT Support Agent",
    "information technology": "IT Support Agent",
    "it": "IT Support Agent",

    "procurement": "Procurement Agent",
    "purchasing": "Procurement Agent",

    "finance": "Finance Agent",
    "financial": "Finance Agent",


    "knowledge": "Knowledge Agent",
    "knowledge base": "Knowledge Agent",
    "enterprise knowledge": "Knowledge Agent",
    "company knowledge": "Knowledge Agent",
    "knowledge management": "Knowledge Agent",
    "communications": "Communications Agent",
    "email": "Communications Agent",

    "general": "Enterprise Workflow Agent",
}


# =========================================================
# HELPERS
# =========================================================

def _normalize(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, set):
        return list(value)

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        return [value]

    return [value]


def _clean_string(value):
    if value is None:
        return ""

    return str(value).strip()


# =========================================================
# RESOLVE SINGLE AGENT
# =========================================================

def resolve_agent(
    department: str,
) -> str:

    department = _clean_string(
        department
    ).lower()

    return AGENT_ROUTES.get(
        department,
        "Enterprise Workflow Agent",
    )


# =========================================================
# RESOLVE MULTIPLE AGENTS
# =========================================================

def resolve_agents(
    departments: List[str],
) -> List[str]:

    agents = []

    for department in _normalize(
        departments
    ):

        agent = resolve_agent(
            department
        )

        if agent not in agents:
            agents.append(
                agent
            )

    return agents


# =========================================================
# EXTRACT TOOL PLAN
# =========================================================

def _extract_tool_plan(
    request: Dict[str, Any],
) -> List[Dict[str, Any]]:

    raw_plan = request.get(
        "tool_plan"
    )

    if not isinstance(
        raw_plan,
        list,
    ):
        return []

    tool_plan = []

    for item in raw_plan:

        if not isinstance(
            item,
            dict,
        ):
            continue

        tool = (
            item.get("tool")
            or item.get("tool_name")
            or item.get("name")
        )

        if not tool:
            continue

        tool = str(
            tool
        ).strip()

        if not tool:
            continue

        agent = (
            item.get("agent")
            or item.get("assigned_agent")
            or item.get("owner")
        )

        purpose = (
            item.get("purpose")
            or item.get("description")
            or "Execute the selected enterprise tool."
        )

        tool_plan.append(
            {
                "tool": tool,
                "agent": (
                    str(agent).strip()
                    if agent
                    else ""
                ),
                "purpose": str(
                    purpose
                ).strip(),
            }
        )

    return tool_plan


# =========================================================
# COORDINATE REQUEST
# =========================================================

def coordinate_request(
    analysis: Dict[str, Any],
) -> Dict[str, Any]:

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # analyze_request() may return:
    #
    # {
    #     "request": {
    #         ...
    #     }
    # }
    #
    # OR:
    #
    # {
    #     "intent": ...,
    #     "departments": ...,
    #     ...
    # }
    #
    # Support BOTH formats.
    # -----------------------------------------------------

    if not isinstance(
        analysis,
        dict,
    ):

        analysis = {}

    nested_request = analysis.get(
        "request"
    )

    if isinstance(
        nested_request,
        dict,
    ):

        request = nested_request

    else:

        request = analysis

    # -----------------------------------------------------
    # Basic fields
    # -----------------------------------------------------

    intent = _clean_string(
        request.get(
            "intent"
        )
    )

    request_category = _clean_string(
        request.get(
            "request_category"
        )
    )

    # -----------------------------------------------------
    # Departments
    # -----------------------------------------------------

    departments = _normalize(
        request.get(
            "departments"
        )
    )

    # If only primary department exists
    # add it to the department list.

    primary_department = _clean_string(
        request.get(
            "department"
        )
    )

    if (
        primary_department
        and primary_department not in departments
    ):

        departments.insert(
            0,
            primary_department,
        )

    # -----------------------------------------------------
    # Existing AI agents
    # -----------------------------------------------------

    ai_agents = _normalize(
        request.get(
            "agents"
        )
    )

    # -----------------------------------------------------
    # AI-generated tool plan
    # -----------------------------------------------------

    tool_plan = _extract_tool_plan(
        request
    )

    # -----------------------------------------------------
    # Tools
    # -----------------------------------------------------

    tools = _normalize(
        request.get(
            "tools"
        )
    )

    # Derive tools from tool_plan
    # when necessary.

    plan_tools = []

    for item in tool_plan:

        tool = item.get(
            "tool"
        )

        if tool and tool not in plan_tools:

            plan_tools.append(
                tool
            )

    if plan_tools:

        tools = plan_tools

    # -----------------------------------------------------
    # Preserve agent ownership from AI tool plan
    # -----------------------------------------------------

    plan_agents = []

    for item in tool_plan:

        agent = item.get(
            "agent"
        )

        if agent and agent not in plan_agents:

            plan_agents.append(
                agent
            )

    # -----------------------------------------------------
    # Resolve agents from departments only when
    # the AI did not already assign them.
    # -----------------------------------------------------

    if plan_agents:

        agents = plan_agents

    elif ai_agents:

        agents = ai_agents

    elif departments:

        agents = resolve_agents(
            departments
        )

    else:

        agents = [
            "Enterprise Workflow Agent"
        ]

    # -----------------------------------------------------
    # Ensure every tool in the plan has an agent
    # -----------------------------------------------------

    normalized_plan = []

    for item in tool_plan:

        tool = item.get(
            "tool"
        )

        agent = item.get(
            "agent"
        )

        # Preserve explicit AI assignment.
        if not agent:

            # Try to identify agent from departments/tools.
            # Only use a fallback if the AI omitted ownership.

            if len(agents) == 1:

                agent = agents[0]

            else:

                agent = (
                    "Enterprise Workflow Agent"
                )

        normalized_plan.append(
            {
                "tool": tool,
                "agent": agent,
                "purpose": item.get(
                    "purpose",
                    "Execute the selected enterprise tool.",
                ),
            }
        )

    tool_plan = normalized_plan

    # -----------------------------------------------------
    # If there is no tool_plan but tools exist,
    # create a basic plan.
    #
    # This is only a structural fallback.
    # It does NOT hardcode individual requests.
    # -----------------------------------------------------

    if not tool_plan and tools:

        for tool in tools:

            if len(agents) == 1:

                agent = agents[0]

            else:

                agent = (
                    "Enterprise Workflow Agent"
                )

            tool_plan.append(
                {
                    "tool": tool,
                    "agent": agent,
                    "purpose": (
                        "Execute the selected enterprise tool."
                    ),
                }
            )

    # -----------------------------------------------------
    # Final agent list should come from tool ownership
    # when a tool plan exists.
    # -----------------------------------------------------

    if tool_plan:

        final_agents = []

        for item in tool_plan:

            agent = item.get(
                "agent"
            )

            if (
                agent
                and agent not in final_agents
            ):

                final_agents.append(
                    agent
                )

        if final_agents:

            agents = final_agents

    # -----------------------------------------------------
    # Primary agent
    # -----------------------------------------------------

    primary_agent = (
        agents[0]
        if agents
        else "Enterprise Workflow Agent"
    )

    # -----------------------------------------------------
    # Details
    # -----------------------------------------------------

    details = request.get(
        "details"
    )

    if not isinstance(
        details,
        dict,
    ):

        details = {}

    # -----------------------------------------------------
    # Action requirement
    # -----------------------------------------------------

    requires_action = bool(
        request.get(
            "requires_action",
            False,
        )
    )

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    confidence = request.get(
        "confidence"
    )

    # -----------------------------------------------------
    # Final result
    # -----------------------------------------------------

    result = {

        "request": request,

        "intent": intent,

        "request_category": request_category,

        "department": (
            primary_department
            or (
                departments[0]
                if departments
                else ""
            )
        ),

        "departments": departments,

        "agent": primary_agent,

        "agents": agents,

        "tools": tools,

        "tool_plan": tool_plan,

        "details": details,

        "requires_action": requires_action,

        "confidence": confidence,

        "coordination_status": "ready",

        "agent_capabilities": [
            {
                "name": agent,
                "department": next(
                    (
                        dept
                        for dept in departments
                        if resolve_agent(
                            dept
                        ) == agent
                    ),
                    "General",
                ),
            }
            for agent in agents
        ],
    }

    return result


# =========================================================
# PUBLIC COORDINATOR
# =========================================================

def run_coordinator(
    analysis: Dict[str, Any],
) -> Dict[str, Any]:

    return coordinate_request(
        analysis
    )


# =========================================================
# CAPABILITIES
# =========================================================

def get_agent_capabilities(
    agent_name: str,
):

    capabilities = {

        "HR Agent": [
            "employee information",
            "leave management",
            "attendance",
            "benefits",
            "HR policies",
            "employee documents",
            "employee onboarding",
            "performance management",
        ],

        "IT Support Agent": [
            "IT support",
            "device support",
            "software access",
            "password and account access",
            "knowledge base",
            "technical troubleshooting",
        ],

        "Procurement Agent": [
            "hardware catalog",
            "purchase requests",
            "purchase orders",
            "vendor information",
            "inventory",
        ],

        "Finance Agent": [
            "budget",
            "expenses",
            "invoices",
            "payments",
            "payroll",
        ],

        "Knowledge Agent": [
            "company knowledge search",
            "enterprise documents",
            "company policies",
            "knowledge retrieval",
            "document search",
            "policy document lookup",
        ],

        "Communications Agent": [
            "internal email drafts",
            "tenant-scoped inbox and sent mail",
            "confirmed internal message delivery",
        ],

        "Enterprise Workflow Agent": [
            "general enterprise requests",
            "cross-department coordination",
            "general knowledge",
        ],
    }

    return capabilities.get(
        agent_name,
        [],
    )


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    test_request = {
        "request_category": "enterprise_action",

        "intent": (
            "Onboard eight new employees"
        ),

        "department": "Human Resources",

        "departments": [
            "Human Resources",
            "Procurement",
            "IT Support",
        ],

        "agents": [
            "HR Agent",
            "Procurement Agent",
            "IT Support Agent",
        ],

        "tools": [
            "onboarding_service",
            "hardware_catalog",
            "purchase_request",
            "software_service",
            "password_access_service",
        ],

        "tool_plan": [
            {
                "tool": "onboarding_service",
                "agent": "HR Agent",
                "purpose": "HR onboarding",
            },
            {
                "tool": "hardware_catalog",
                "agent": "Procurement Agent",
                "purpose": "Find suitable laptops",
            },
            {
                "tool": "purchase_request",
                "agent": "Procurement Agent",
                "purpose": "Create purchase request",
            },
            {
                "tool": "software_service",
                "agent": "IT Support Agent",
                "purpose": "Provide software access",
            },
            {
                "tool": "password_access_service",
                "agent": "IT Support Agent",
                "purpose": "Create accounts",
            },
        ],

        "details": {
            "employee_count": 8,
        },

        "requires_action": True,

        "confidence": 0.98,
    }

    import pprint

    pprint.pp(
        run_coordinator(
            test_request
        )
    )
