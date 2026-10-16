from typing import Any, Dict, List

from langgraph.graph import StateGraph, START, END

from core.state import WorkflowState
from core.llm import analyze_request, chat_with_gemini
from core.tool_executor import execute_tools
from company.context import load_tenant_context
from company.policy_evaluator import evaluate_policy_rules
from company.approval_service import create_approval, list_pending_approvals
from company.employee_service import record_employee_service

from agents.coordinator_agent import run_coordinator
from agents.hr_agent import run_hr_agent
from agents.it_agent import run_it_agent
from agents.procurement_agent import run_procurement_agent
from agents.finance_agent import run_finance_agent
from agents.knowledge_agent import run_knowledge_agent


# =========================================================
# AGENT RUNNERS
# =========================================================

AGENT_RUNNERS = {
    "HR Agent": run_hr_agent,
    "IT Support Agent": run_it_agent,
    "Procurement Agent": run_procurement_agent,
    "Finance Agent": run_finance_agent,
    "Knowledge Agent": run_knowledge_agent,
}


# =========================================================
# HELPERS
# =========================================================

def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _unique(values: List[Any]) -> List[str]:
    result = []

    for value in values:
        value = _clean(value)

        if value and value not in result:
            result.append(value)

    return result


def _normalize_tool_plan(
    tool_plan: Any,
) -> List[Dict[str, Any]]:
    """
    Preserve the AI-generated tool ownership.

    Example:

    onboarding_service -> HR Agent
    hardware_catalog -> Procurement Agent
    software_service -> IT Support Agent
    password_access_service -> IT Support Agent
    """

    if not isinstance(tool_plan, list):
        return []

    normalized = []

    for item in tool_plan:

        if isinstance(item, str):
            normalized.append(
                {
                    "tool": item,
                    "agent": "",
                    "purpose": "",
                }
            )
            continue

        if not isinstance(item, dict):
            continue

        tool = (
            item.get("tool")
            or item.get("tool_name")
            or item.get("name")
        )

        agent = (
            item.get("agent")
            or item.get("assigned_agent")
            or item.get("owner")
        )

        purpose = (
            item.get("purpose")
            or item.get("description")
            or ""
        )

        if tool:
            normalized.append(
                {
                    "tool": _clean(tool),
                    "agent": _clean(agent),
                    "purpose": _clean(purpose),
                }
            )

    return normalized


def _extract_coordinator_request(
    coordinator_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Coordinator may return the actual request inside:

        coordinator_result["request"]

    Prefer that nested request when it contains
    meaningful AI-generated routing information.
    """

    if not isinstance(coordinator_result, dict):
        return {}

    nested = coordinator_result.get("request")

    if isinstance(nested, dict):

        if isinstance(
            nested.get("tool_plan"),
            list,
        ) and nested.get("tool_plan"):
            return nested

        if isinstance(
            nested.get("agents"),
            list,
        ) and nested.get("agents"):
            return nested

        if isinstance(
            nested.get("tools"),
            list,
        ) and nested.get("tools"):
            return nested

    return coordinator_result


# =========================================================
# UNDERSTANDING
# =========================================================

def understand_node(
    state: WorkflowState,
) -> Dict[str, Any]:

    message = state.get(
        "raw_message",
        "",
    )

    history = state.get(
        "conversation_history",
        [],
    )

    company_context = state.get(
        "company_context",
        {},
    )

    # -----------------------------------------------------
    # 1. AI UNDERSTANDS REQUEST
    # -----------------------------------------------------

    analysis = analyze_request(
        message,
        conversation_history=history,
        company_context=company_context,
    )

    # Deterministic routing guard at the workflow boundary. For well-known
    # requests, the service catalogue is authoritative: skip the second LLM
    # coordinator call, which previously could override an obvious IT ticket
    # intent with Knowledge/search_knowledge. We still keep the analysis above
    # for extracted dates, reasons, and other entities.
    from core.service_catalog import (
        classify_read_only_route,
        classify_specialized_request,
    )
    route_override = classify_read_only_route(message, history)
    if route_override is None:
        route_override = classify_specialized_request(message)

    if route_override:
        request = dict(analysis)
    else:
        # -----------------------------------------------------
        # 2. COORDINATOR ROUTES REQUEST
        # -----------------------------------------------------
        coordinator = run_coordinator(analysis)
        # -----------------------------------------------------
        # 3. EXTRACT ACTUAL REQUEST
        # -----------------------------------------------------
        request = _extract_coordinator_request(coordinator)

    if route_override:
        source_details = {}
        if isinstance(analysis.get("details"), dict):
            source_details.update(analysis["details"])
        if isinstance(request.get("details"), dict):
            source_details.update(request["details"])
        if isinstance(route_override.get("details"), dict):
            source_details.update(route_override["details"])
        if route_override.get("request_category") == "information_request":
            for key in (
                "service_request_type", "service_request_title", "service_request_area",
                "service_request_priority", "service_request_requires_approval",
                "service_request_needs_external_integration", "service_request_confidential",
            ):
                source_details.pop(key, None)
        request.update(route_override)
        request["details"] = source_details

    # -----------------------------------------------------
    # 4. AI-GENERATED TOOL PLAN
    # -----------------------------------------------------

    tool_plan = _normalize_tool_plan(
        request.get(
            "tool_plan",
            [],
        )
    )

    # -----------------------------------------------------
    # 5. AGENTS
    # -----------------------------------------------------

    agents = request.get(
        "agents",
        [],
    )

    if not isinstance(
        agents,
        list,
    ):
        agents = []

    plan_agents = [
        item.get("agent")
        for item in tool_plan
        if item.get("agent")
    ]

    agents = _unique(
        plan_agents + agents
    )

    # -----------------------------------------------------
    # 6. TOOLS
    # -----------------------------------------------------

    tools = request.get(
        "tools",
        [],
    )

    if not isinstance(
        tools,
        list,
    ):
        tools = []

    plan_tools = [
        item.get("tool")
        for item in tool_plan
        if item.get("tool")
    ]

    tools = _unique(
        plan_tools + tools
    )

    # SAFETY GATE: information-only requests must not execute
    # business-action tools, even if the model selected one.
    from core.tool_executor import ACTION_TOOLS, TOOL_ALIASES

    request_category = str(
        request.get("request_category")
        or analysis.get("request_category")
        or ""
    ).strip().casefold()

    message_lower = str(message or "").strip().casefold()

    informational_categories = {
        "information_request",
        "information",
        "knowledge_request",
        "knowledge_query",
        "policy_information",
    }

    learning_question = (
        "?" in message_lower
        and any(phrase in message_lower for phrase in (
            "what tool should i use to learn",
            "what tool can i use to learn",
            "which tool should i use to learn",
            "what should i use to learn",
        ))
        and any(term in message_lower for term in (
            "python", "programming", "coding",
        ))
    )

    information_only = (
        request_category in informational_categories
        or learning_question
    )

    if information_only:
        def canonical_tool(name):
            name = str(name or "").strip()
            return TOOL_ALIASES.get(name, name)

        route_details = request.get("details") if isinstance(request.get("details"), dict) else {}
        route_intent = str(request.get("intent") or analysis.get("intent") or "").casefold()

        def is_allowed_read_only_use(tool_name):
            canonical = canonical_tool(tool_name)
            if canonical == "create_ticket" and route_details.get("read_only_follow_up") and route_intent in {"it_ticket_follow_up", "it_ticket_status", "it_ticket_history"}:
                if route_intent == "it_ticket_history" or route_details.get("ticket_id"):
                    return True
            if canonical == "leave_management" and route_intent == "leave_information":
                return True
            if canonical == "hr_general_request_service" and route_intent == "hr_request_history":
                return True
            if canonical == "benefits_service" and route_intent in {"benefits_information", "general_information", "benefits_query"}:
                return True
            return False

        filtered_plan = []
        removed_action = False

        for item in tool_plan:
            tool_name = item.get("tool") if isinstance(item, dict) else ""
            if canonical_tool(tool_name) in ACTION_TOOLS and not is_allowed_read_only_use(tool_name):
                removed_action = True
            else:
                filtered_plan.append(item)

        safe_tools = [
            name for name in tools
            if canonical_tool(name) not in ACTION_TOOLS or is_allowed_read_only_use(name)
        ]

        request["request_category"] = "information_request"
        request["requires_action"] = False

        if removed_action:
            tool_plan = filtered_plan
            tools = _unique(
                [
                    item.get("tool")
                    for item in tool_plan
                    if isinstance(item, dict) and item.get("tool")
                ] + safe_tools
            )

            # Keep agent routing aligned with the remaining safe plan.
            agents = _unique([
                item.get("agent")
                for item in tool_plan
                if isinstance(item, dict) and item.get("agent")
            ])

            request["tool_plan"] = tool_plan
            request["tools"] = tools
            request["agents"] = agents

            if not tool_plan:
                fallback_plan = [{
                    "tool": "search_knowledge",
                    "agent": "Knowledge Agent",
                    "purpose": "Answer the informational question without creating a business request.",
                }]
                tool_plan = fallback_plan
                tools = ["search_knowledge"]
                agents = ["Knowledge Agent"]
                request["tool_plan"] = tool_plan
                request["tools"] = tools
                request["agents"] = agents
                request["departments"] = ["Knowledge"]
                request["department"] = "Knowledge"

    # -----------------------------------------------------
    # 7. DEPARTMENTS
    # -----------------------------------------------------

    departments = request.get(
        "departments",
        [],
    )

    if not isinstance(
        departments,
        list,
    ):
        departments = []

    # -----------------------------------------------------
    # 8. FALLBACK AGENT
    # -----------------------------------------------------

    if not agents:
        agents = [
            "Enterprise Workflow Agent"
        ]

    # -----------------------------------------------------
    # 9. DETAILS
    # -----------------------------------------------------

    details = request.get(
        "details",
        analysis.get(
            "details",
            {},
        ),
    )

    if not isinstance(
        details,
        dict,
    ):
        details = {}

    # -----------------------------------------------------
    # 10. TRACE
    # -----------------------------------------------------

    trace = list(
        state.get(
            "trace",
            [],
        )
    )

    trace.append(
        {
            "stage": "understanding",
            "message": "AI analyzed the enterprise request",
            "company_id": state.get("company_id", ""),
            "user_id": state.get("user_id", ""),
            "analysis": analysis,
        }
    )

    trace.append(
        {
            "stage": "coordination",
            "message": "Coordinator identified agents and tools",
            "agents": agents,
            "tools": tools,
            "tool_plan": tool_plan,
        }
    )

    return {
        "analysis": analysis,

        "intent": request.get(
            "intent",
            analysis.get(
                "intent",
                "",
            ),
        ),

        "request_category": request.get(
            "request_category",
            analysis.get(
                "request_category",
                "",
            ),
        ),

        "department": request.get(
            "department",
            analysis.get(
                "department",
                "",
            ),
        ),

        "departments": departments,

        "assigned_agents": agents,

        "tools": tools,

        "tool_names": tools,

        "tool_plan": tool_plan,

        "details": details,

        "requires_action": request.get(
            "requires_action",
            analysis.get(
                "requires_action",
                False,
            ),
        ),

        "confidence": request.get(
            "confidence",
            analysis.get(
                "confidence"
            ),
        ),

        "trace": trace,
    }


# =========================================================
# PLANNING
# =========================================================

def planning_node(
    state: WorkflowState,
) -> Dict[str, Any]:

    tool_plan = _normalize_tool_plan(
        state.get(
            "tool_plan",
            [],
        )
    )

    agents = []

    for item in tool_plan:

        agent = item.get(
            "agent"
        )

        if agent and agent not in agents:
            agents.append(agent)

    for agent in state.get(
        "assigned_agents",
        [],
    ):

        if agent and agent not in agents:
            agents.append(agent)

    tools = []

    for item in tool_plan:

        tool = item.get(
            "tool"
        )

        if tool and tool not in tools:
            tools.append(tool)

    for tool in state.get(
        "tools",
        [],
    ):

        if tool and tool not in tools:
            tools.append(tool)

    trace = list(
        state.get(
            "trace",
            [],
        )
    )

    trace.append(
        {
            "stage": "planning",
            "message": "Prepared dynamic tool execution plan",
            "agents": agents,
            "tools": tools,
            "tool_plan": tool_plan,
        }
    )

    return {
        "assigned_agents": agents,
        "tools": tools,
        "tool_names": tools,
        "tool_plan": tool_plan,
        "trace": trace,
    }



def _service_area_for_agent(
    agent: str,
    tool_name: str,
    department: str = "",
) -> str:
    """Map an agent/tool to an employee service area."""

    tool = str(tool_name or "").strip().lower()
    agent_name = str(agent or "").strip().lower()
    department_name = str(department or "").strip().lower()

    if "hr" in agent_name:
        return "HR"

    if "it" in agent_name:
        return "IT"

    if "procurement" in agent_name:
        return "Procurement"

    if "finance" in agent_name:
        return "Finance"
    if tool in {
        "leave_management",
        "attendance_service",
        "benefits_service",
        "hr_policy_service",
        "employee_document_service",
        "onboarding_service",
        "performance_service",
        "employee_information",
        "hr_grievance_service",
        "hr_training_service",
        "hr_general_request_service",
    }:
        return "HR"

    if tool in {
        "create_ticket",
        "device_service",
        "password_access_service",
        "software_service",
        "knowledge_base_service",
    }:
        return "IT"

    if tool in {
        "inventory_check",
        "hardware_catalog",
        "purchase_order",
        "purchase_request",
        "vendor_service",
    }:
        return "Procurement"

    if tool in {
        "budget_service",
        "expense_service",
        "invoice_service",
        "payment_service",
        "payroll_service",
    }:
        return "Finance"
    if department_name:
        return str(department).strip()

    return "Enterprise"


def _service_type_for_tool(
    tool_name: str,
) -> str:
    """Create a readable service type from a tool name."""

    tool = str(tool_name or "").strip()

    if not tool:
        return "Enterprise Service"

    labels = {
        "employee_information": "Employee Information",
        "hr_grievance_service": "HR Grievance",
        "hr_training_service": "HR Training",
        "hr_general_request_service": "General HR Request",
        "leave_management": "Leave",
        "attendance_service": "Attendance",
        "benefits_service": "Benefits",
        "hr_policy_service": "HR Policy",
        "employee_document_service": "Employee Documents",
        "onboarding_service": "Onboarding",
        "performance_service": "Performance",
        "create_ticket": "IT Support",
        "device_service": "Device",
        "password_access_service": "Password / Access",
        "software_service": "Software",
        "knowledge_base_service": "IT Knowledge",
        "inventory_check": "Inventory",
        "hardware_catalog": "Hardware Catalog",
        "purchase_order": "Purchase Order",
        "purchase_request": "Purchase Request",
        "vendor_service": "Vendor",
        "budget_service": "Budget",
        "expense_service": "Expense",
        "invoice_service": "Invoice",
        "payment_service": "Payment",
        "payroll_service": "Payroll",
    }

    return labels.get(
        tool,
        tool.replace("_", " ").title(),
    )


def _record_tool_service(
    state: WorkflowState,
    agent: str,
    tool_name: str,
    tool_result: Dict[str, Any],
) -> None:
    """Persist every employee service/tool usage."""

    company_id = _clean(state.get("company_id"))
    user_id = _clean(state.get("user_id"))

    if not company_id or not user_id:
        return

    if not isinstance(tool_result, dict):
        return

    actual_tool_name = (
        _clean(tool_name)
        or _clean(tool_result.get("tool"))
        or _clean(tool_result.get("executed_tool"))
        or _clean(tool_result.get("requested_tool"))
        or _clean(tool_result.get("tool_name"))
    )

    if not actual_tool_name:
        return

    status = (
        _clean(tool_result.get("status"))
        or "completed"
    )

    if tool_result.get("pending_confirmation") is True:
        action_type = "Confirmation Required"

    elif status.lower() == "missing_information":
        action_type = "Clarification Required"

    elif tool_result.get("executed") is True:
        action_type = "Executed"

    elif status.lower() in {
        "error",
        "failed",
        "failure",
        "no_result",
        "missing_information",
        "incomplete",
        "invalid",
        "not_found",
    }:
        action_type = "Failed"

    else:
        action_type = "Queried"

    decision = state.get("decision", {})

    if not isinstance(decision, dict):
        decision = {}

    try:
        record_employee_service(
            company_id=company_id,
            user_id=user_id,
            service_area=_service_area_for_agent(
                agent,
                actual_tool_name,
                state.get("department", ""),
            ),
            service_type=_service_type_for_tool(
                actual_tool_name,
            ),
            action_type=action_type,
            description=(
                tool_result.get("message")
                or tool_result.get("action")
                or tool_result.get("result")
                or f"Employee used {actual_tool_name}."
            ),
            status=status,
            decision=_clean(
                decision.get("action")
            ),
            workflow_id=_clean(
                state.get("workflow_id")
            ),
            approval_id=(
                tool_result.get("approval_id")
                if tool_result.get("approval_id") is not None
                else None
            ),
            agent_name=agent,
            tool_name=actual_tool_name,
            request_data={
                "message": state.get(
                    "raw_message",
                    "",
                ),
                "details": state.get(
                    "details",
                    {},
                ),
            },
            result_data=tool_result,
        )

    except Exception as exc:
        # History logging must never break the main workflow.
        trace = list(
            state.get("trace", [])
        )

        trace.append(
            {
                "stage": "employee_history",
                "status": "logging_failed",
                "tool": actual_tool_name,
                "error": str(exc),
            }
        )

        state["trace"] = trace

# =========================================================
# EXECUTION
# =========================================================

def execute_node(
    state: WorkflowState,
) -> Dict[str, Any]:

    tool_plan = _normalize_tool_plan(
        state.get(
            "tool_plan",
            [],
        )
    )

    raw_message = state.get(
        "raw_message",
        "",
    )

    details = state.get(
        "details",
        {},
    )

    if not isinstance(
        details,
        dict,
    ):
        details = {}

    all_tool_results = []
    agent_results = []

    trace = list(
        state.get(
            "trace",
            [],
        )
    )

    # -----------------------------------------------------
    # TENANT-SCOPED EXECUTION CONTEXT
    # -----------------------------------------------------

    execution_details = dict(details)
    execution_details["company_id"] = state.get("company_id", "")
    execution_details["user_id"] = state.get("user_id", "")
    execution_details["user_role"] = state.get("user_role", "")
    execution_details["workflow_id"] = state.get("workflow_id", "")

    execution_details["department"] = (
        state.get("department")
        or execution_details.get("department")
        or (
            state.get("company_context", {})
            .get("department", "")
            if isinstance(state.get("company_context", {}), dict)
            else ""
        )
    )

    execution_details["company_context"] = state.get(
        "company_context",
        {},
    )

    # -----------------------------------------------------
    # CONFIRMATION / RESUME STATE
    # -----------------------------------------------------

    confirmed = bool(
        state.get(
            "confirmation_received",
            False,
        )
    )
    # Tools may use this trusted workflow flag when an earlier request has
    # been explicitly confirmed. It avoids inferring a write action from the
    # original sentence alone (for example, "create leave request").
    execution_details["_confirmed_action"] = confirmed

    # -----------------------------------------------------
    # GROUP CONTIGUOUS TOOLS BY AGENT, preserving coordinator order.
    # -----------------------------------------------------

    grouped = []

    for item in tool_plan:

        tool = item.get(
            "tool"
        )

        agent = item.get(
            "agent"
        )

        if not tool:
            continue

        if not agent:
            agent = "Enterprise Workflow Agent"

        if not grouped or grouped[-1][0] != agent:
            grouped.append((agent, []))
        grouped[-1][1].append(item)

    # -----------------------------------------------------
    # EXECUTE EACH AGENT GROUP
    # -----------------------------------------------------

    for agent, items in grouped:

        agent_tool_names = [
            item["tool"]
            for item in items
            if item.get("tool")
        ]

        if not agent_tool_names:
            continue

        # IMPORTANT:
        # execute_tools signature is:
        #
        # execute_tools(
        #     tool_names,
        #     details,
        #     message
        # )
        #
        # DO NOT use raw_message= here.

        # Build email fields from the user's request; do not force an HR/leave template.
        if "email_draft" in agent_tool_names:
            import re

            email_text = str(raw_message or "")
            lowered_email = email_text.casefold()

            # Resolve explicit recipient instructions first.
            recipient_line = re.search(
                r"(?im)^\s*(?:recipient|to)\s*:\s*(.+?)\s*$", email_text
            )
            recipient_match = re.search(
                r"(?is)\b(?:email|draft|message)\b.{0,100}?\bto\s+(?:the\s+)?"
                r"(it\s+support(?:\s+team|\s+department)?|"
                r"hr(?:\s+team|\s+department)?|"
                r"human\s+resources|company\s+admin|manager)\b",
                email_text,
            )

            recipient_value = (
                recipient_line.group(1).strip().strip("\"'??")
                if recipient_line
                else recipient_match.group(1).strip() if recipient_match
                else str(execution_details.get("recipient") or "").strip()
            )

            if recipient_value:
                recipient_key = recipient_value.casefold()
                if recipient_key.startswith("it support"):
                    recipient_value = "IT Support"
                elif recipient_key in {"hr", "hr team", "hr department", "human resources"}:
                    recipient_value = "HR"
                elif recipient_key == "company admin":
                    recipient_value = "company admin"
                execution_details["recipient"] = recipient_value

            # An explicitly requested subject takes priority.
            subject_match = re.search(
                r"(?im)^\s*subject\s*:\s*(.+?)\s*$", email_text
            )
            if not subject_match:
                subject_match = re.search(
                    r"(?i)\b(?:use|set)\s+the\s+subject\s+(?:to\s+)?[\"?](.+?)[\"?]",
                    email_text,
                )

            if subject_match:
                execution_details["subject"] = (
                    subject_match.group(1).strip().strip("\"'??")
                )
            elif not str(execution_details.get("subject") or "").strip():
                execution_details["subject"] = (
                    "Leave Request" if "leave" in lowered_email
                    else "Internal Company Message"
                )

            # Prefer exact body text, or construct one from the actual request.
            explicit_body = re.search(
                r"(?is)\b(?:write|say|include)\s*:\s*[\"?](.+?)[\"?]",
                email_text,
            )
            if not explicit_body:
                explicit_body = re.search(
                    r"(?im)^\s*(?:body|message)\s*:\s*(.+?)\s*$",
                    email_text,
                )

            body_parts = []
            date_match = re.search(
                r"\b([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})\b", email_text
            )

            report_match = re.search(
                r"(?is)\b(?:reporting that|report that)\s+(.+?)"
                r"(?=\.\s*(?:use|set|explain|save|do not)|[.\n]|$)",
                email_text,
            )
            explain_match = re.search(
                r"(?is)\b(?:explain|mention|include)\s+that\s+(.+?)"
                r"(?=\.\s*(?:use|set|save|do not)|[.\n]|$)",
                email_text,
            )

            for match in (report_match, explain_match):
                if match:
                    sentence = match.group(1).strip().rstrip(". ")
                    if date_match:
                        sentence = re.sub(
                            r"\bthat date\b",
                            date_match.group(1),
                            sentence,
                            flags=re.IGNORECASE,
                        )
                    if sentence:
                        sentence = sentence[0].upper() + sentence[1:]
                        body_parts.append(sentence + ".")

            if explicit_body:
                message_body = explicit_body.group(1).strip()
            elif body_parts:
                message_body = " ".join(body_parts)
            elif "leave" in lowered_email and date_match:
                message_body = f"I am requesting leave on {date_match.group(1)}."
            else:
                existing_body = str(execution_details.get("body") or "").strip()
                old_leave_fallback = (
                    "Hello HR Team" in existing_body
                    and "Please confirm the requested date" in existing_body
                )
                if existing_body and not old_leave_fallback:
                    message_body = existing_body
                else:
                    subject_text = str(
                        execution_details.get("subject") or "this matter"
                    ).strip()
                    message_body = (
                        f"I am contacting you regarding {subject_text}. "
                        "Please advise on the next steps."
                    )

            recipient_for_greeting = str(
                execution_details.get("recipient") or ""
            ).casefold()
            if explicit_body and re.match(r"(?i)^(hello|hi|dear)\b", message_body):
                final_body = message_body
            else:
                if "it support" in recipient_for_greeting or recipient_for_greeting == "it":
                    greeting = "Hello IT Support Team,"
                elif recipient_for_greeting in {"hr", "hr team", "hr department", "human resources"}:
                    greeting = "Hello HR Team,"
                elif "company admin" in recipient_for_greeting:
                    greeting = "Hello Company Admin,"
                elif recipient_for_greeting:
                    greeting = f"Hello {str(execution_details['recipient']).strip()},"
                else:
                    greeting = "Hello,"
                final_body = f"{greeting}\n\n{message_body}\n\nRegards,\nEmployee"

            execution_details["body"] = final_body

        result = execute_tools(
            agent_tool_names,
            execution_details,
            raw_message,
            confirmed=confirmed,
        )

        # execute_tools() currently returns a LIST.
        if not isinstance(
            result,
            list,
        ):
            result = [
                {
                    "status": "error",
                    "message": (
                        "Tool executor returned "
                        "an invalid response."
                    ),
                }
            ]

        agent_result = {
            "agent": agent,
            "tools": agent_tool_names,
            "results": result,
        }

        agent_results.append(
            agent_result
        )

        # -------------------------------------------------
        # STORE EVERY TOOL RESULT
        # -------------------------------------------------

        for tool_result in result:

            if not isinstance(
                tool_result,
                dict,
            ):
                continue

            enriched = dict(
                tool_result
            )

            enriched.setdefault(
                "agent",
                agent,
            )

            all_tool_results.append(
                enriched
            )

            # -------------------------------------------------
            # PERSIST EMPLOYEE SERVICE HISTORY
            # -------------------------------------------------

            actual_tool_name = (
                tool_result.get("tool")
                or tool_result.get("executed_tool")
                or tool_result.get("requested_tool")
                or tool_result.get("tool_name")
                or ""
            )

            _record_tool_service(
                state,
                agent,
                str(actual_tool_name),
                tool_result,
            )

        trace.append(
            {
                "stage": "execution",
                "agent": agent,
                "tools": agent_tool_names,
                "result": result,
            }
        )

    return {
        "agent_results": agent_results,
        "tool_results": all_tool_results,
        "trace": trace,
    }


# =========================================================
# VALIDATION
# =========================================================

def validation_node(
    state: WorkflowState,
) -> Dict[str, Any]:

    tool_results = state.get(
        "tool_results",
        [],
    )

    if not tool_results:

        validation = {
            "status": "information",
            "valid": True,
            "message": (
                "No enterprise action tool "
                "was executed."
            ),
        }

        return {
            "validation": validation,
            "confirmation_requested": False,
        }

    failures = []
    clarifications = []
    successes = []
    pending = []

    failure_statuses = {
        "error",
        "failed",
        "failure",
        "missing_information",
        "incomplete",
        "invalid",
        "not_found",
        "permission_denied",
    }

    for result in tool_results:

        if not isinstance(
            result,
            dict,
        ):
            continue

        status = str(
            result.get(
                "status",
                "",
            )
        ).lower()

        if status == "missing_information":
            clarifications.append(result)
            continue

        # -------------------------------------------------
        # CONFIRMATION REQUIRED
        # -------------------------------------------------

        if (
            result.get(
                "pending_confirmation"
            ) is True
            or status == "pending_confirmation"
        ):
            pending.append(result)
            continue

        # -------------------------------------------------
        # FAILURE
        # -------------------------------------------------

        if status in failure_statuses:
            failures.append(result)
            continue

        # -------------------------------------------------
        # EXPLICIT EXECUTION SUCCESS
        # -------------------------------------------------

        if result.get(
            "executed"
        ) is True:
            successes.append(result)
            continue

        # -------------------------------------------------
        # USEFUL TOOL RESULT
        # -------------------------------------------------

        if any(
            key in result
            for key in [
                "message",
                "action",
                "data",
                "items",
                "records",
                "result",
            ]
        ):
            successes.append(result)
            continue

        failures.append(result)

    # -----------------------------------------------------
    # FINAL VALIDATION STATUS
    # -----------------------------------------------------

    if failures:

        validation = {
            "status": "failed",
            "valid": False,
            "message": (
                "One or more enterprise tools "
                "failed or returned incomplete results."
            ),
            "failures": failures,
            "successes": successes,
            "pending": pending,
        }

    elif clarifications:
        validation = {
            "status": "needs_clarification",
            "valid": False,
            "message": next((str(item.get("message")) for item in clarifications if item.get("message")), "Please provide the missing information to continue."),
            "clarifications": clarifications,
            "successes": successes,
        }

    elif pending:

        validation = {
            "status": "pending_confirmation",
            "valid": False,
            "message": (
                "Some enterprise actions require "
                "user confirmation before execution."
            ),
            "pending": pending,
            "successes": successes,
        }

    else:

        validation = {
            "status": "success",
            "valid": True,
            "message": (
                "Enterprise tool results "
                "were validated successfully."
            ),
            "successes": successes,
        }

    return {
        "validation": validation,
        "confirmation_requested": (
            validation.get("status")
            == "pending_confirmation"
        ),
    }


# =========================================================
# DECISION
# =========================================================

def decision_node(
    state: WorkflowState,
) -> Dict[str, Any]:

    validation = state.get(
        "validation",
        {},
    )

    status = validation.get(
        "status",
        "information",
    )

    details = state.get(
        "details",
        {},
    )

    if not isinstance(details, dict):
        details = {}

    important = details.get(
        "important",
        {},
    )

    if not isinstance(important, dict):
        important = {}

    amount_inr = (
        important.get("amount_inr")
        or important.get("amount")
        or important.get("price")
        or details.get("amount_inr")
        or details.get("amount")
        or details.get("estimated_cost_inr")
        or details.get("estimated_cost")
    )

    policy_context: Dict[str, Any] = {}

    if amount_inr is not None:
        try:
            policy_context["amount_inr"] = float(amount_inr)
        except (TypeError, ValueError):
            pass

    company_id = state.get(
        "company_id",
        "",
    )

    user_id = state.get(
        "user_id",
        "",
    )

    workflow_id = state.get(
        "workflow_id",
        "",
    )

    department = state.get(
        "department",
        "",
    )

    # -----------------------------------------------------
    # CANONICAL POLICY DEPARTMENT
    # -----------------------------------------------------
    # LLM output may use names such as "Human Resources",
    # while enterprise policies are stored using canonical
    # department names such as "HR".
    #
    # Resolve the policy department from the actual assigned
    # agent/tool so policy evaluation remains reliable.
    policy_department = department

    tool_results_for_department = state.get(
        "tool_results",
        [],
    )

    if tool_results_for_department:
        for item in tool_results_for_department:
            if not isinstance(item, dict):
                continue

            agent_name = str(
                item.get(
                    "agent",
                    "",
                )
            )

            tool_name = str(
                item.get(
                    "tool",
                    item.get(
                        "executed_tool",
                        item.get(
                            "requested_tool",
                            "",
                        ),
                    ),
                )
            )

            resolved_area = _service_area_for_agent(
                agent_name,
                tool_name,
                department,
            )

            if resolved_area:
                policy_department = resolved_area
                break

    policy_evaluation = {
        "policy_evaluated": False,
        "matched_rules": [],
        "actions": {},
        "approval_required": False,
    }

    if company_id and department:
        try:
            policy_evaluation = evaluate_policy_rules(
                company_id=company_id,
                department=policy_department,
                context=policy_context,
            )
        except Exception as exc:
            policy_evaluation = {
                "policy_evaluated": False,
                "matched_rules": [],
                "actions": {},
                "approval_required": False,
                "error": str(exc),
            }

    # -----------------------------------------------------
    # USER CONFIRMATION IS ALWAYS FIRST
    # -----------------------------------------------------

    if status == "pending_confirmation":

        reason = (
            "User confirmation is required "
            "before completing one or more actions."
        )

        decision = {
            "action": "HUMAN_REVIEW",
            "reason": reason,
            "confirmation_required": True,
        }

    elif status == "needs_clarification":
        decision = {
            "action": "CLARIFICATION_REQUIRED",
            "reason": str(validation.get("message") or "Required request information is missing."),
        }

    # -----------------------------------------------------
    # TOOL FAILURE
    # -----------------------------------------------------

    elif status == "failed" and any(
        isinstance(item, dict)
        and str(item.get("status", "")).casefold() == "permission_denied"
        for item in validation.get("failures", [])
    ):
        denied = next(
            item for item in validation.get("failures", [])
            if isinstance(item, dict)
            and str(item.get("status", "")).casefold() == "permission_denied"
        )
        decision = {
            "action": "ACCESS_DENIED",
            "reason": str(
                denied.get("message")
                or "You do not have permission to perform this request."
            ),
        }

    elif status == "failed":

        decision = {
            "action": "HUMAN_REVIEW",
            "reason": (
                "One or more enterprise tools "
                "failed or returned incomplete results."
            ),
        }

    # -----------------------------------------------------
    # SUCCESS + POLICY APPROVAL
    # -----------------------------------------------------

    elif status == "success":

        request_category = str(
            state.get(
                "request_category",
                "",
            )
            or ""
        ).strip().lower()

        requires_action = bool(
            state.get(
                "requires_action",
                False,
            )
        )

        informational_categories = {
            "information_request",
            "information",
            "knowledge_request",
            "knowledge_query",
            "policy_information",
        }

        tool_requires_approval = any(
            isinstance(item, dict) and item.get("approval_required") is True
            for item in state.get("tool_results", [])
        )
        if (
            tool_requires_approval
            or (
                requires_action
                and request_category not in informational_categories
                and policy_evaluation.get("approval_required", False)
            )
        ):

            matched_rules = policy_evaluation.get(
                "matched_rules",
                [],
            )

            approval_level = None

            # Select the rule that actually requires approval.
            # Do not blindly use the first matched rule because
            # informational rules such as annual_leave_days may
            # also be matched and have no approval level.
            for matched_rule in matched_rules:

                rule_actions = matched_rule.get(
                    "actions",
                    {},
                )

                if not isinstance(
                    rule_actions,
                    dict,
                ):
                    rule_actions = {}

                rule_approval_required = bool(
                    rule_actions.get(
                        "approval_required",
                        False,
                    )
                    or rule_actions.get(
                        "manager_approval_required",
                        False,
                    )
                )

                rule_level = matched_rule.get(
                    "approval_level"
                )

                if rule_approval_required or rule_level:
                    approval_level = (
                        rule_level
                        or "additional"
                    )
                    break

            if tool_requires_approval and not approval_level:
                approval_level = "manager"

            approval = None

            # Prevent duplicate pending approvals when the same
            # workflow is evaluated again.
            if company_id and workflow_id:
                try:
                    existing = list_pending_approvals(
                        company_id=company_id,
                    )

                    for item in existing:
                        if str(item.get("workflow_id")) == str(workflow_id):
                            approval = item
                            break
                except Exception:
                    approval = None

            if approval is None and company_id and workflow_id and user_id:
                leave_employee_id = next(
                    (
                        item.get("employee_id")
                        for item in state.get("tool_results", [])
                        if isinstance(item, dict) and item.get("tool") == "leave_management" and item.get("employee_id")
                    ),
                    "",
                )
                approver_user_id = ""
                if tool_requires_approval and leave_employee_id:
                    from company.leave_service import resolve_manager_user_id
                    approver_user_id = resolve_manager_user_id(company_id, str(leave_employee_id))
                approval = create_approval(
                    company_id=company_id,
                    workflow_id=workflow_id,
                    requested_by=user_id,
                    approval_type=(
                        approval_level or "additional"
                    ),
                    reason=(
                        "Company policy requires approval "
                        "before completing this action."
                    ),
                    approver_user_id=approver_user_id,
                    metadata={
                        "department": department,
                        "amount_inr": amount_inr,
                        "request": state.get(
                            "raw_message",
                            "",
                        ),
                        "policy_evaluation": policy_evaluation,

                        # Preserve the authoritative tool result
                        # needed for final business-action completion.
                        "tool": next(
                            (
                                item.get(
                                    "tool",
                                    item.get(
                                        "executed_tool",
                                        item.get(
                                            "requested_tool",
                                            "",
                                        ),
                                    ),
                                )
                                for item in state.get(
                                    "tool_results",
                                    [],
                                )
                                if isinstance(item, dict)
                                and (item.get("request_id") or item.get("approval_required"))
                            ),
                            "",
                        ),

                        "employee_id": next(
                            (
                                item.get("employee_id")
                                for item in state.get(
                                    "tool_results",
                                    [],
                                )
                                if isinstance(item, dict)
                                and item.get("employee_id")
                            ),
                            "",
                        ),

                        "employee_name": next(
                            (
                                item.get("employee_name")
                                for item in state.get(
                                    "tool_results",
                                    [],
                                )
                                if isinstance(item, dict)
                                and item.get("employee_name")
                            ),
                            "",
                        ),

                        "requested_days": next(
                            (
                                item.get("requested_days")
                                for item in state.get(
                                    "tool_results",
                                    [],
                                )
                                if isinstance(item, dict)
                                and item.get("requested_days") is not None
                            ),
                            None,
                        ),

                        "start_date": next(
                            (
                                item.get("start_date")
                                for item in state.get(
                                    "tool_results",
                                    [],
                                )
                                if isinstance(item, dict)
                                and item.get("start_date")
                            ),
                            "",
                        ),
                        "end_date": next(
                            (
                                item.get("end_date")
                                for item in state.get("tool_results", [])
                                if isinstance(item, dict) and item.get("end_date")
                            ),
                            "",
                        ),
                        "request_id": next(
                            (
                                item.get("request_id")
                                for item in state.get("tool_results", [])
                                if isinstance(item, dict) and item.get("request_id")
                            ),
                            "",
                        ),
                        "service_area": next(
                            (
                                item.get("service_area")
                                for item in state.get("tool_results", [])
                                if isinstance(item, dict) and item.get("request_id")
                            ),
                            department,
                        ),
                        "request_id": next(
                            (
                                item.get("request_id")
                                for item in state.get("tool_results", [])
                                if isinstance(item, dict) and item.get("request_id")
                            ),
                            "",
                        ),
                    },
                )

            if approval and any(
                isinstance(item, dict) and item.get("tool") == "leave_management"
                and item.get("request_id")
                for item in state.get("tool_results", [])
            ):
                from company.leave_service import attach_approval
                attach_approval(
                    company_id=company_id,
                    workflow_id=workflow_id,
                    approval_id=int(approval["approval_id"]),
                    approver_user_id=str(approval.get("approver_user_id") or ""),
                )
                approver_name = ""
                if approval.get("approver_user_id"):
                    from company.store import get_user
                    approver_name = str(get_user(str(approval["approver_user_id"])).get("name") or "")
                for item in state.get("tool_results", []):
                    if isinstance(item, dict) and item.get("tool") == "leave_management" and item.get("request_id"):
                        item["approval_id"] = approval["approval_id"]
                        item["approver_user_id"] = approval.get("approver_user_id", "")
                        item["approver_name"] = approver_name

            if approval and any(
                isinstance(item, dict) and item.get("request_id")
                and item.get("tool") != "leave_management"
                for item in state.get("tool_results", [])
            ):
                from company.request_service import attach_department_approval
                attach_department_approval(
                    company_id, workflow_id, int(approval["approval_id"]),
                    str(approval.get("approver_user_id") or ""),
                )
                for item in state.get("tool_results", []):
                    if isinstance(item, dict) and item.get("request_id") and item.get("tool") != "leave_management":
                        item["approval_id"] = approval["approval_id"]
                        item["approver_user_id"] = approval.get("approver_user_id", "")

            decision = {
                "action": "HUMAN_REVIEW",
                "reason": (
                    "Company policy requires "
                    f"{approval_level or 'additional'} "
                    "approval before completing this action."
                ),
                "approval_id": (
                    approval.get("approval_id")
                    if approval
                    else None
                ),
                "approval_status": (
                    approval.get("status")
                    if approval
                    else "pending"
                ),
            }

        else:

            decision = {
                "action": "CONTINUE",
                "reason": (
                    "The requested enterprise actions "
                    "were executed and validated."
                ),
            }

    else:

        decision = {
            "action": "INFORMATION",
            "reason": (
                "The request only required information."
            ),
        }

    return {
        "policy_evaluation": policy_evaluation,
        "decision": decision,
    }


# =========================================================
# RESPONSE
# =========================================================

def response_node(
    state: WorkflowState,
) -> Dict[str, Any]:

    validation = state.get(
        "validation",
        {},
    )

    tool_results = state.get(
        "tool_results",
        [],
    )

    message = state.get(
        "raw_message",
        "",
    )

    # Format authoritative HR request history directly from tool results.
    # Do not ask the LLM to rediscover records already returned by the service.
    hr_history_results = [
        item for item in tool_results
        if isinstance(item, dict)
        and str(
            item.get("tool")
            or item.get("executed_tool")
            or item.get("requested_tool")
            or ""
        ).strip() == "hr_general_request_service"
        and isinstance(item.get("records"), list)
    ]

    if hr_history_results:
        records_by_id = {}

        for result_item in hr_history_results:
            for record in result_item.get("records") or []:
                if not isinstance(record, dict):
                    continue

                request_id = str(
                    record.get("request_id")
                    or record.get("record_id")
                    or ""
                ).strip()

                if not request_id:
                    continue

                # Deduplicate records without changing their returned statuses.
                if request_id not in records_by_id:
                    request_type = str(
                        record.get("service_type")
                        or record.get("request_type")
                        or record.get("action_type")
                        or "HR request"
                    ).strip()

                    raw_status = str(
                        record.get("status")
                        or record.get("current_status")
                        or "Unknown"
                    ).strip()

                    records_by_id[request_id] = (
                        request_id,
                        request_type,
                        raw_status.replace("_", " ").title(),
                    )

        if records_by_id:
            response_lines = [
                f"Found {len(records_by_id)} existing HR request(s):",
                "",
                "| Request ID | Request type | Current status |",
                "|---|---|---|",
            ]

            for request_id, request_type, status in records_by_id.values():
                request_id = request_id.replace("|", "/")
                request_type = request_type.replace("|", "/")
                status = status.replace("|", "/")
                response_lines.append(
                    f"| {request_id} | {request_type} | {status} |"
                )

            return {"response": "\n".join(response_lines)}

        empty_message = next(
            (
                str(item.get("message") or "").strip()
                for item in hr_history_results
                if item.get("message")
            ),
            "The HR history service returned no identifiable request records.",
        )
        return {"response": empty_message}

    # Answer the recent-ticket follow-up from the authoritative request row;
    # do not ask the LLM to guess where the ticket lives or its current status.
    it_ticket_reads = [
        item for item in tool_results
        if isinstance(item, dict)
        and str(item.get("tool") or item.get("executed_tool") or item.get("requested_tool") or "").strip() == "create_ticket"
        and item.get("read_only") is True
    ]
    if it_ticket_reads:
        item = it_ticket_reads[0]
        record = item.get("record")
        if isinstance(record, dict) and record.get("request_id"):
            ticket_id = str(record.get("request_id"))
            status = str(record.get("status") or "unknown").replace("_", " ").title()
            title = str(record.get("title") or "IT support request")
            return {"response": f"Your IT request is {ticket_id}. Current status: {status}. Title: {title}. You can find it in the employee portal under **My IT Tickets**. The current status is retrieved from your saved request record."}
        records = item.get("records")
        if isinstance(records, list):
            rows = [row for row in records if isinstance(row, dict) and row.get("request_id")]
            if rows:
                lines = ["Your saved IT requests:", "", "| Request ID | Title | Status |", "|---|---|---|"]
                for row in rows[:50]:
                    lines.append(f"| {str(row.get('request_id')).replace('|', '/')} | {str(row.get('title') or row.get('request_type') or 'IT request').replace('|', '/')} | {str(row.get('status') or 'unknown').replace('_', ' ').title()} |")
                lines.extend(["", "Open **My IT Tickets** in the employee portal to view the request details."])
                return {"response": "\n".join(lines)}
        if item.get("message"):
            return {"response": str(item["message"])}

    # General-learning questions are not HR/IT business actions. Give a useful
    # fallback if tenant knowledge has no course/tutorial document.
    if str(state.get("intent") or "").casefold() == "general_learning_guidance":
        return {"response": (
            "To learn Python, start with beginner syntax and short exercises: variables and data types, conditions, loops, functions, lists/dictionaries, files and exceptions. "
            "Use the official Python tutorial as a reference, and practise in VS Code or a browser notebook such as Jupyter/Colab. Build small projects (calculator, file organiser, API reader) and solve a few problems regularly. "
            "This is general learning guidance; no HR request or IT ticket was created."
        )}

    # Use the tool's grounded safe steps for troubleshooting rather than
    # letting a response model turn a not-configured KB into a dead end.
    troubleshooting_results = [
        item for item in tool_results
        if isinstance(item, dict)
        and str(item.get("tool") or item.get("executed_tool") or "").strip() == "knowledge_base_service"
        and str(item.get("request_type") or "").casefold() == "troubleshooting"
        and item.get("message")
    ]
    if troubleshooting_results:
        return {"response": str(troubleshooting_results[0]["message"])}

    # -----------------------------------------------------
    # FAST CONFIRMED WORKFLOW RESPONSE
    # -----------------------------------------------------
    # After the user explicitly confirms an action, the tool
    # has already produced the authoritative result. Do not
    # spend another LLM call just to summarize it.
    confirmed = bool(
        state.get(
            "confirmation_received",
            False,
        )
    )

    if (
        confirmed
        and tool_results
        and validation.get("status") not in {
            "failed",
            "pending_confirmation",
        }
    ):
        messages = []

        for item in tool_results:
            if isinstance(item, dict):
                if item.get("tool") == "leave_management" and item.get("request_id"):
                    messages.append(
                        "Your leave request was submitted.\n"
                        f"Request ID: {item['request_id']}\n"
                        f"Leave type: {item.get('leave_type', 'Not specified')}\n"
                        f"Dates: {item.get('start_date', '')} to {item.get('end_date', '')}\n"
                        f"Days: {item.get('requested_days', '')}\n"
                        f"Status: {str(item.get('status_label', 'pending approval')).replace('_', ' ').title()}\n"
                        f"Approval ID: {item.get('approval_id', 'Not required')}\n"
                        f"Approver: {item.get('approver_name') or ('Assigned approver' if item.get('approver_user_id') else 'HR/Admin approval queue')}\n"
                        f"Available balance before approval: {item.get('leave_balance', '')} day(s)"
                    )
                    continue
                result_message = item.get("message")

                if result_message:
                    messages.append(
                        str(result_message)
                    )
                    continue

                result = item.get("result")

                if isinstance(result, dict):
                    result_message = result.get(
                        "message"
                    )

                    if result_message:
                        messages.append(
                            str(result_message)
                        )

        if messages:
            return {
                "response": " ".join(messages)
            }

        return {
            "response": (
                "The confirmed action was executed "
                "successfully."
            )
        }

    if validation.get("status") == "needs_clarification":
        return {"response": str(validation.get("message") or "Please provide the missing information so I can continue this request.")}

    # Explain tool failures and provide actionable recovery steps.
    failure_guidance = {
        "permission_denied": "This request was blocked because your account does not have permission to access the requested information or action. No approval request was created. If you believe you should have access, contact your company admin.",
        "budget_exceeded": "Next step: Reduce the requested amount or seek the required budget approval.",
        "finance_budget_exceeded": "Next step: Review the available budget with Finance or request the required approval.",
        "out_of_stock": "Next step: Choose an available alternative or ask Procurement about restocking.",
        "not_configured": "Next step: Ask the company admin to configure this service, then retry.",
        "policy_unavailable": "Next step: Ask HR/Admin to verify and publish the relevant company policy.",
        "policy_invalid": "Next step: Ask HR/Admin to correct the policy settings before retrying.",
        "invalid": "Next step: Review the required fields, correct the details, and submit again.",
        "not_found": "Next step: Verify the request ID or employee details and try again.",
        "insufficient_balance": "Next step: Check your available balance or choose different dates.",
        "failed": "Next step: Review the request details and retry. If it fails again, contact the responsible department.",
        "error": "Next step: Retry once. If the issue continues, contact the responsible department.",
        "failure": "Next step: Review the request details and retry. If it fails again, contact the responsible department.",
    }

    actionable_errors = []
    failure_statuses = set(failure_guidance)

    for item in tool_results:
        if not isinstance(item, dict):
            continue

        status = str(item.get("status") or "").strip().lower()
        message = str(item.get("message") or "").strip()

        if status in failure_statuses and message:
            suggestion = failure_guidance[status]
            actionable_errors.append(f"{message} {suggestion}")

    if actionable_errors:
        return {"response": " ".join(dict.fromkeys(actionable_errors))}

    # FAILED / PENDING
    # -----------------------------------------------------

    if validation.get(
        "status"
    ) in {
        "failed",
        "pending_confirmation",
    }:

        # A pending action must clearly ask the employee
        # for confirmation. Do not execute anything here.
        if validation.get("status") == "pending_confirmation":
            pending = validation.get("pending", [])
            pending_tools = []

            for item in pending:
                if isinstance(item, dict):
                    tool_name = (
                        item.get("executed_tool")
                        or item.get("requested_tool")
                    )
                    if tool_name and tool_name not in pending_tools:
                        pending_tools.append(tool_name)

            tool_text = (
                ", ".join(pending_tools)
                if pending_tools
                else "the requested action"
            )

            if "purchase_request" in pending_tools:
                candidates = []
                for item in tool_results:
                    if not isinstance(item, dict):
                        continue
                    candidates.extend(item.get("available_items") or item.get("products") or [])
                candidates = [item for item in candidates if isinstance(item, dict) and int(item.get("quantity_available") or 0) > 0]
                purpose = str((state.get("details") or {}).get("use_case") or "").casefold()
                if candidates:
                    if purpose:
                        purpose_terms = set(__import__("re").findall(r"[a-z0-9]+", purpose))
                        ranked = []
                        for candidate in candidates:
                            searchable = " ".join([str(candidate.get("model") or ""), *(str(value) for value in (candidate.get("specifications") or {}).values())]).casefold()
                            score = len(purpose_terms & set(__import__("re").findall(r"[a-z0-9]+", searchable)))
                            ranked.append((score, candidate))
                        candidates = [item for score, item in ranked if score == max(value[0] for value in ranked)]
                    candidate = candidates[0]
                    price = candidate.get("unit_price")
                    currency = candidate.get("currency") or ""
                    price_text = f"{currency} {float(price):,.0f}" if price is not None else "price not configured"
                    return {"response": f"I found {candidate.get('model') or 'an available laptop'} at {price_text}, with {int(candidate.get('quantity_available') or 0)} available. Would you like me to submit the purchase request? Reply yes to confirm."}

            return {
                "response": (
                    f"The action requires your confirmation before it can be executed. "
                    f"Pending action: {tool_text}. "
                    "Please reply 'Yes, proceed' to continue."
                ),
            }

        # Failure path: let the response layer explain the
        # actual tool results when available.
        try:

            response = chat_with_gemini(
                message,
                tool_results=tool_results,
                conversation_history=state.get(
                    "conversation_history",
                    [],
                ),
                company_context=state.get("company_context", {}),
            )

        except Exception:

            response = validation.get(
                "message",
                "The requested operation could not be completed.",
            )

        return {
            "response": response,
        }

    # -----------------------------------------------------
    # COMPANY UPDATES / IMPORTANT LINKS
    # -----------------------------------------------------
    # Company updates are authoritative records already
    # retrieved by the Knowledge tool. Format them directly
    # instead of asking the LLM to rediscover them.
    company_updates = []

    for item in tool_results:

        if not isinstance(item, dict):
            continue

        # Current knowledge search returns company updates
        # directly at the tool-result level.
        if item.get("result_type") == "company_update":
            company_updates.append(item)

        # Compatibility with nested result structures.
        nested_results = item.get("results")

        if isinstance(nested_results, list):

            for nested in nested_results:

                if (
                    isinstance(nested, dict)
                    and nested.get("result_type")
                    == "company_update"
                ):
                    company_updates.append(nested)

    if company_updates:

        lines = [
            "Here are the latest company updates:"
        ]

        for update in company_updates[:8]:

            title = str(
                update.get("title")
                or "Company Update"
            ).strip()

            description = str(
                update.get("description")
                or ""
            ).strip()

            priority = str(
                update.get("priority")
                or "normal"
            ).strip().lower()

            category = str(
                update.get("category")
                or ""
            ).strip()

            link_url = str(
                update.get("link_url")
                or ""
            ).strip()

            lines.append("")
            lines.append(
                f"**{title}**"
            )

            if priority:
                lines.append(
                    f"- Priority: **{priority.title()}**"
                )

            if category:
                lines.append(
                    f"- Category: **{category}**"
                )

            if description:
                lines.append(
                    f"- {description}"
                )

            if link_url:
                lines.append(
                    f"- Link: {link_url}"
                )

        return {
            "response": "\n".join(lines)
        }

    # -----------------------------------------------------
    # TOOL RESULTS
    # -----------------------------------------------------

    if tool_results:

        try:

            response = chat_with_gemini(
                message,
                tool_results=tool_results,
                conversation_history=state.get(
                    "conversation_history",
                    [],
                ),
                company_context=state.get("company_context", {}),
            )

        except Exception:

            response = (
                "The requested enterprise operation "
                "was processed using the available tools."
            )

        return {
            "response": response,
        }

    # -----------------------------------------------------
    # INFORMATION REQUEST
    # -----------------------------------------------------

    try:

        response = chat_with_gemini(
            message,
            tool_results=[],
            conversation_history=state.get(
                "conversation_history",
                [],
            ),
            company_context=state.get("company_context", {}),
        )

    except Exception:

        response = (
            "I couldn't complete the requested operation "
            "because the AI response service is "
            "temporarily unavailable."
        )

    return {
        "response": response,
    }


# =========================================================
# BUILD WORKFLOW
# =========================================================

def build_workflow():

    graph = StateGraph(
        WorkflowState
    )

    graph.add_node(
        "understand",
        understand_node,
    )

    graph.add_node(
        "planning",
        planning_node,
    )

    graph.add_node(
        "execute",
        execute_node,
    )

    graph.add_node(
        "validation",
        validation_node,
    )

    graph.add_node(
        "decision",
        decision_node,
    )

    graph.add_node(
        "response",
        response_node,
    )

    # -----------------------------------------------------
    # GRAPH FLOW
    # -----------------------------------------------------

    graph.add_edge(
        START,
        "understand",
    )

    graph.add_edge(
        "understand",
        "planning",
    )

    graph.add_edge(
        "planning",
        "execute",
    )

    graph.add_edge(
        "execute",
        "validation",
    )

    graph.add_edge(
        "validation",
        "decision",
    )

    graph.add_edge(
        "decision",
        "response",
    )

    graph.add_edge(
        "response",
        END,
    )

    return graph.compile()


workflow = build_workflow()


# =========================================================
# PUBLIC FUNCTION
# =========================================================

def run_workflow(
    message: str,
    conversation_history: List[Dict[str, Any]] | None = None,
    company_id: str | None = None,
    user_id: str | None = None,
    user_role: str | None = None,
    workflow_id: str | None = None,
    confirmation_received: bool = False,
) -> Dict[str, Any]:

    tenant = load_tenant_context(
        company_id=company_id,
        user_id=user_id,
        user_role=user_role,
    )

    if workflow_id is None:
        import uuid
        workflow_id = str(uuid.uuid4())

    initial_state = {
        "raw_message": message,
        "workflow_id": workflow_id,

        "confirmation_requested": False,
        "confirmation_received": confirmation_received,

        "company_id": tenant.get("company_id", ""),
        "user_id": tenant.get("user_id", ""),
        "user_role": tenant.get("user_role", ""),
        "company_context": tenant.get("context", {}),

        "conversation_history": (
            conversation_history or []
        ),

        "trace": [],

        "analysis": {},

        "request_category": "",
        "request_type": "",
        "intent": "",

        "department": "",
        "departments": [],

        "assigned_agent": "",
        "assigned_agents": [],

        "tools": [],
        "tool_names": [],
        "tool_plan": [],

        "details": {},
        "extracted_details": {},

        "requires_action": False,
        "confidence": None,

        "agent_results": [],
        "tool_result": None,
        "tool_results": [],

        "validation": {},
        "decision": {},

        "response": "",
    }

    try:
        result = workflow.invoke(initial_state)
    except Exception as exc:
        result = {
            **initial_state,
            "request_category": "workflow_error",
            "decision": {"action": "ERROR", "reason": str(exc)},
            "validation": {"status": "error", "errors": [str(exc)]},
            "tool_results": [],
            "trace": [{"stage": "error", "message": "Workflow execution failed."}],
            "response": "I couldn't complete this request because the workflow encountered an error. Please try again or contact your administrator.",
        }

    _persist_workflow_result(result)

    public_result = dict(result)
    public_result.pop("company_context", None)
    return public_result


def _workflow_request_status(result: Dict[str, Any]) -> str:
    """Map workflow state to a precise lifecycle label for pending-list queries."""
    validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
    decision = result.get("decision") if isinstance(result.get("decision"), dict) else {}
    tool_results = result.get("tool_results") if isinstance(result.get("tool_results"), list) else []
    request_category = str(result.get("request_category") or "").casefold()
    has_saved_action_record = any(
        isinstance(item, dict) and (item.get("request_id") or item.get("approval_id"))
        for item in tool_results
    )
    if validation.get("status") == "error" or decision.get("action") == "ERROR":
        return "failed"
    if validation.get("status") == "cancelled" or decision.get("action") == "CANCELLED":
        return "cancelled"
    if validation.get("status") == "needs_clarification":
        return "awaiting_clarification"
    if validation.get("status") == "pending_confirmation":
        return "awaiting_confirmation"
    if request_category in {"information_request", "general_information", "read_only"}:
        # Read-only retrieval (including a ticket detail lookup) must never
        # become an approval row even if a provider selected HUMAN_REVIEW.
        return "completed"
    if decision.get("action") == "HUMAN_REVIEW" and has_saved_action_record:
        return "pending_approval"
    return "completed"


def _persist_workflow_result(result: Dict[str, Any]) -> None:
    """Persist the request and execution trail for tenant-scoped history."""
    company_id = str(result.get("company_id") or "")
    user_id = str(result.get("user_id") or "")
    workflow_id = str(result.get("workflow_id") or "")
    if not (company_id and user_id and workflow_id):
        return
    try:
        from company.memory_service import save_workflow_request, save_workflow_execution
        validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
        tool_results = result.get("tool_results") if isinstance(result.get("tool_results"), list) else []
        status = _workflow_request_status(result)
        save_workflow_request(
            workflow_id=workflow_id, company_id=company_id, user_id=user_id,
            request_text=str(result.get("raw_message") or ""),
            request_category=str(result.get("request_category") or ""),
            intent=str(result.get("intent") or ""), status=status,
            decision=decision, assigned_agents=result.get("assigned_agents") or [],
            selected_tools=result.get("tool_names") or result.get("tools") or [],
            context={"departments": result.get("departments") or [], "validation": validation, "tool_results": tool_results, "response": result.get("response", "")},
        )
        for entry in result.get("trace") or []:
            if isinstance(entry, dict):
                save_workflow_execution(company_id, workflow_id, str(entry.get("stage") or "workflow"), agent_key=str(entry.get("agent") or ""), tool_key=str(entry.get("tool") or ""), input_data={"message": entry.get("message", "")}, output_data=entry, status="failed" if status == "failed" else "completed")
        for item in tool_results:
            if isinstance(item, dict):
                save_workflow_execution(company_id, workflow_id, "tool_execution", tool_key=str(item.get("tool") or item.get("executed_tool") or ""), input_data={"request": result.get("raw_message", ""), "details": result.get("details") or {}}, output_data=item, status="failed" if str(item.get("status", "")).lower() in {"error", "failed"} else "completed")
    except Exception:
        # Business operations have already completed; history persistence
        # failures must not turn a successful tool action into a false error.
        return


# =========================================================
# CANCEL PENDING CONFIRMATION
# =========================================================

def cancel_pending_workflow(
    previous_result: Dict[str, Any],
    cancellation_message: str = "no, cancel",
) -> Dict[str, Any]:
    """Cancel a pending action before any business tool is executed."""
    if not isinstance(previous_result, dict):
        raise ValueError("previous_result must be a dictionary.")
    validation = previous_result.get("validation", {})
    if not isinstance(validation, dict) or validation.get("status") != "pending_confirmation":
        raise ValueError("This workflow is not waiting for user confirmation.")

    state: Dict[str, Any] = dict(previous_result)
    cancelled_validation = dict(validation)
    cancelled_validation.update({
        "status": "cancelled",
        "message": "The employee cancelled before the action was executed.",
        "executed": False,
    })
    state["validation"] = cancelled_validation

    decision = state.get("decision")
    decision = dict(decision) if isinstance(decision, dict) else {}
    decision.update({
        "action": "CANCELLED",
        "confirmation_required": False,
        "reason": "The employee cancelled before execution.",
    })
    state["decision"] = decision
    state["confirmation_requested"] = True
    state["confirmation_received"] = False
    state["response"] = (
        "Cancelled. The pending request was not submitted and no business action was executed. "
        "You can start a new request whenever you are ready."
    )
    trace = list(state.get("trace") or [])
    trace.append({
        "stage": "confirmation_cancelled",
        "message": "The employee cancelled the pending action before execution.",
        "cancellation_message": cancellation_message,
    })
    state["trace"] = trace
    state.pop("company_context", None)
    _persist_workflow_result(state)
    return state


# =========================================================
# RESUME CONFIRMED WORKFLOW
# =========================================================

def resume_workflow(
    previous_result: Dict[str, Any],
    confirmation_message: str = "yes, proceed",
) -> Dict[str, Any]:
    """
    Resume a workflow that stopped at pending_confirmation.

    The original workflow state is reused so the coordinator does
    not have to reinterpret the user's confirmation message as a
    brand-new enterprise request.

    The confirmation message itself is recorded in the trace, but
    the original request remains the message sent to enterprise tools.
    """

    if not isinstance(previous_result, dict):
        raise ValueError("previous_result must be a dictionary.")

    validation = previous_result.get("validation", {})

    if validation.get("status") != "pending_confirmation":
        raise ValueError(
            "This workflow is not waiting for user confirmation."
        )

    company_id = previous_result.get("company_id", "")
    user_id = previous_result.get("user_id", "")
    user_role = previous_result.get("user_role", "")

    if not company_id or not user_id:
        raise ValueError(
            "Cannot resume workflow without company_id and user_id."
        )

    tenant = load_tenant_context(
        company_id=company_id,
        user_id=user_id,
        user_role=user_role,
    )

    # Reconstruct the original state. Do NOT replace raw_message with
    # 'yes' because the enterprise tools need the original request.
    state: Dict[str, Any] = dict(previous_result)
    state["company_context"] = tenant.get("context", {})
    state["confirmation_requested"] = True
    state["confirmation_received"] = True

    trace = list(
        state.get(
            "trace",
            [],
        )
    )

    trace.append(
        {
            "stage": "confirmation",
            "message": "User confirmed the pending enterprise action.",
            "confirmation_message": confirmation_message,
        }
    )

    state["trace"] = trace

    # Resume only from execution onward. This preserves the original
    # AI-generated plan and prevents a confirmation message from being
    # interpreted as a new request.
    execution_update = execute_node(state)
    state.update(execution_update)

    validation_update = validation_node(state)
    state.update(validation_update)

    decision_update = decision_node(state)
    state.update(decision_update)

    response_update = response_node(state)
    state.update(response_update)

    state.pop("company_context", None)
    _persist_workflow_result(state)
    return state


# =========================================================
# DIRECT TEST
# =========================================================

if __name__ == "__main__":

    import pprint

    test_message = (
        "Onboard 8 new employees with HR onboarding, "
        "laptops, software access, and required accounts"
    )

    result = run_workflow(
        test_message
    )

    print("\n--- AGENTS ---")
    pprint.pp(
        result.get(
            "assigned_agents"
        )
    )

    print("\n--- PLAN ---")
    pprint.pp(
        result.get(
            "tool_plan"
        )
    )

    print("\n--- AGENT RESULTS ---")
    pprint.pp(
        result.get(
            "agent_results"
        )
    )

    print("\n--- TOOL RESULTS ---")
    pprint.pp(
        result.get(
            "tool_results"
        )
    )

    print("\n--- VALIDATION ---")
    pprint.pp(
        result.get(
            "validation"
        )
    )

    print("\n--- DECISION ---")
    pprint.pp(
        result.get(
            "decision"
        )
    )

    print("\n--- RESPONSE ---")
    print(
        result.get(
            "response"
        )
    )
