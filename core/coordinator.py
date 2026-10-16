from typing import Any, Dict, List


# ============================================================
# AGENT ROUTES
# ============================================================

AGENT_ROUTES: Dict[str, Dict[str, str]] = {

    "hr": {
        "department": "HR",
        "agent": "HR Agent",
    },

    "human resources": {
        "department": "HR",
        "agent": "HR Agent",
    },

    "it": {
        "department": "IT",
        "agent": "IT Support Agent",
    },

    "it support": {
        "department": "IT",
        "agent": "IT Support Agent",
    },

    "information technology": {
        "department": "IT",
        "agent": "IT Support Agent",
    },

    "procurement": {
        "department": "Procurement",
        "agent": "Procurement Agent",
    },

    "purchasing": {
        "department": "Procurement",
        "agent": "Procurement Agent",
    },

    "finance": {
        "department": "Finance",
        "agent": "Finance Agent",
    },

    "accounting": {
        "department": "Finance",
        "agent": "Finance Agent",
    },

    "knowledge": {
        "department": "Knowledge",
        "agent": "Knowledge Agent",
    },

    "communications": {
        "department": "Communications",
        "agent": "Communications Agent",
    },

    "email": {
        "department": "Communications",
        "agent": "Communications Agent",
    },
}


# ============================================================
# NORMALIZATION
# ============================================================

def _normalize(value: Any) -> str:

    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def _as_list(value: Any) -> List[Any]:

    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


# ============================================================
# RESOLVE ONE AGENT
# ============================================================

def resolve_agent(
    department: str = "",
    agent: str = "",
) -> Dict[str, str]:

    normalized_department = _normalize(
        department
    )

    normalized_agent = _normalize(
        agent
    )

    # --------------------------------------------------------
    # Explicit agent supplied by Gemini
    # --------------------------------------------------------

    if normalized_agent:

        if "hr" in normalized_agent:
            return {
                "department": "HR",
                "agent": "HR Agent",
            }

        if (
            "it" in normalized_agent
            or "support" in normalized_agent
        ):
            return {
                "department": "IT",
                "agent": "IT Support Agent",
            }

        if "procurement" in normalized_agent:
            return {
                "department": "Procurement",
                "agent": "Procurement Agent",
            }

        if (
            "finance" in normalized_agent
            or "accounting" in normalized_agent
        ):
            return {
                "department": "Finance",
                "agent": "Finance Agent",
            }

        if "knowledge" in normalized_agent:
            return {
                "department": "Knowledge",
                "agent": "Knowledge Agent",
            }

        if "communication" in normalized_agent or "email" in normalized_agent:
            return {"department": "Communications", "agent": "Communications Agent"}

    # --------------------------------------------------------
    # Department supplied by Gemini
    # --------------------------------------------------------

    route = AGENT_ROUTES.get(
        normalized_department
    )

    if route:
        return dict(route)

    # --------------------------------------------------------
    # Unknown department
    #
    # Do NOT guess using message keywords.
    # --------------------------------------------------------

    return {
        "department": (
            department
            if department
            else "Enterprise"
        ),
        "agent": (
            agent
            if agent
            else "Enterprise Workflow Agent"
        ),
    }


# ============================================================
# RESOLVE MULTIPLE AGENTS
# ============================================================

def resolve_agents(
    departments: Any = None,
    agents: Any = None,
) -> List[Dict[str, str]]:

    department_list = _as_list(
        departments
    )

    agent_list = _as_list(
        agents
    )

    resolved: List[Dict[str, str]] = []

    # --------------------------------------------------------
    # First resolve explicit agent list
    # --------------------------------------------------------

    for agent in agent_list:

        route = resolve_agent(
            agent=str(agent)
        )

        if route not in resolved:
            resolved.append(route)

    # --------------------------------------------------------
    # Then resolve department list
    # --------------------------------------------------------

    for department in department_list:

        route = resolve_agent(
            department=str(department)
        )

        if route not in resolved:
            resolved.append(route)

    return resolved


# ============================================================
# COORDINATE REQUEST
# ============================================================

def coordinate_request(
    message: str,
    analysis: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Coordinate an already-understood enterprise request.

    IMPORTANT:

    This function does NOT classify the raw user message
    using keyword rules.

    Gemini is responsible for understanding the request.

    The Coordinator is responsible for normalizing and
    organizing Gemini's structured decision.
    """

    analysis = analysis or {}

    # --------------------------------------------------------
    # Extract Gemini analysis
    # --------------------------------------------------------

    department = (
        analysis.get("department")
        or ""
    )

    departments = _as_list(
        analysis.get("departments")
    )

    if not departments and department:
        departments = [
            department
        ]

    agent = (
        analysis.get("agent")
        or ""
    )

    agents = _as_list(
        analysis.get("agents")
    )

    if not agents and agent:
        agents = [
            agent
        ]

    tools = _as_list(
        analysis.get("tools")
        or analysis.get("tool_names")
    )

    tool_plan = _as_list(
        analysis.get("tool_plan")
    )

    details = (
        analysis.get("details")
        or analysis.get("extracted_details")
        or {}
    )

    requires_action = bool(
        analysis.get(
            "requires_action",
            False,
        )
    )

    # Preserve action semantics even if the model misses the flag.
    # The confirmation guard still decides whether an action may execute.
    if (
        str(analysis.get("request_category") or "").strip().casefold()
        == "enterprise_action"
    ):
        requires_action = True

    confidence = analysis.get(
        "confidence",
        0.0,
    )

    # --------------------------------------------------------
    # Resolve agent assignments
    # --------------------------------------------------------

    resolved_agents = resolve_agents(
        departments=departments,
        agents=agents,
    )

    # --------------------------------------------------------
    # If Gemini supplied no agent information,
    # use a neutral enterprise coordinator.
    #
    # DO NOT inspect the user's message here.
    # --------------------------------------------------------

    if not resolved_agents:

        resolved_agents = [
            {
                "department": "Enterprise",
                "agent": "Enterprise Workflow Agent",
            }
        ]

    # --------------------------------------------------------
    # Build normalized department list
    # --------------------------------------------------------

    final_departments = []

    for route in resolved_agents:

        route_department = route.get(
            "department"
        )

        if (
            route_department
            and route_department
            not in final_departments
        ):
            final_departments.append(
                route_department
            )

    # --------------------------------------------------------
    # Build normalized agent list
    # --------------------------------------------------------

    final_agents = []

    for route in resolved_agents:

        route_agent = route.get(
            "agent"
        )

        if (
            route_agent
            and route_agent
            not in final_agents
        ):
            final_agents.append(
                route_agent
            )

    # --------------------------------------------------------
    # Primary assignment
    # --------------------------------------------------------

    primary_route = resolved_agents[0]

    primary_department = primary_route.get(
        "department",
        "Enterprise",
    )

    primary_agent = primary_route.get(
        "agent",
        "Enterprise Workflow Agent",
    )

    # --------------------------------------------------------
    # Ensure tool plan contains selected tools
    # --------------------------------------------------------

    normalized_tool_plan = []

    for item in tool_plan:

        if not isinstance(
            item,
            dict,
        ):
            continue

        tool = (
            item.get("tool")
            or item.get("tool_name")
        )

        if not tool:
            continue

        plan_item = dict(item)

        plan_item["tool"] = tool

        # If Gemini assigned an agent to this tool,
        # preserve it.
        if not plan_item.get("agent"):

            if len(final_agents) == 1:

                plan_item["agent"] = (
                    final_agents[0]
                )

        normalized_tool_plan.append(
            plan_item
        )

    # --------------------------------------------------------
    # If Gemini selected tools but did not create a
    # tool_plan, create a simple normalized plan.
    # --------------------------------------------------------

    if not normalized_tool_plan:

        for tool in tools:

            if not tool:
                continue

            plan_item = {
                "tool": tool,
                "purpose": (
                    "Execute the tool selected by "
                    "the request analysis."
                ),
            }

            if len(final_agents) == 1:

                plan_item["agent"] = (
                    final_agents[0]
                )

            normalized_tool_plan.append(
                plan_item
            )

    # --------------------------------------------------------
    # Return normalized coordination result
    # --------------------------------------------------------

    return {
        "department": primary_department,

        "departments": final_departments,

        "agent": primary_agent,

        "agents": final_agents,

        "tools": tools,

        "tool_plan": normalized_tool_plan,

        "details": details,

        "requires_action": requires_action,

        "confidence": confidence,

        "coordination_status": "success",
    }


# ============================================================
# PUBLIC COORDINATOR
# ============================================================

def run_coordinator(
    message: str,
    analysis: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Public coordinator entry point.

    Gemini -> Coordinator -> Specialist Agents
    """

    return coordinate_request(
        message=message,
        analysis=analysis,
    )


# ============================================================
# AGENT CAPABILITIES
# ============================================================

def get_agent_capabilities() -> Dict[str, List[str]]:
    """
    Return high-level agent capabilities.

    These are capability descriptions, not user-request
    keyword rules.
    """

    return {

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
            "technical support",
            "device support",
            "password and account access",
            "software and license support",
            "technical troubleshooting",
            "IT support tickets",
        ],

        "Procurement Agent": [
            "inventory",
            "hardware catalog",
            "procurement requests",
            "purchase orders",
            "vendor and supplier information",
        ],

        "Finance Agent": [
            "budget",
            "expenses",
            "reimbursements",
            "invoices",
            "payments",
            "payroll",
        ],

        "Knowledge Agent": [
            "enterprise knowledge",
            "general organizational information",
            "knowledge search",
        ],

        "Communications Agent": [
            "internal email drafts",
            "tenant-scoped inbox and sent mail",
            "confirmed internal message delivery",
        ],
    }
