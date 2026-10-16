
import sys
from pathlib import Path
from datetime import datetime
from html import escape as html_escape

# ============================================================
# PROJECT PATH
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from company.store import initialize_company_store, get_company, get_user, get_company_context, authorize_user, list_company_users
from company.auth import authenticate_user_by_email
from company.registration_service import register_employee
from company.onboarding_service import create_company_workspace
from company.resource_service import list_resources
from company.agent_registry_service import list_agent_runtime_status
from company.notification_service import mark_notification_read
from company.admin_portal import render_admin_portal
from core.workflow import run_workflow, resume_workflow, cancel_pending_workflow
from core.pending_confirmation import (
    classify_pending_confirmation_reply,
    hold_pending_confirmation_result,
)
from core.conversation_intent import (
    is_clear_new_request_during_clarification,
    is_simple_greeting,
    pending_lookup_requested,
)

from company.employee_portfolio_service import (
    create_project,
    get_project,
    update_project,
    list_projects,
    create_milestone,
    list_milestones,
    create_achievement,
    list_achievements,
    create_participation,
    list_participations,
    get_performance,
    create_project_module,
    list_project_modules,
    save_project_file,
    list_project_files,
    get_project_file,
    delete_project_file,
    create_project_submission,
    list_my_project_submissions,
)

from company.memory_service import (
    create_conversation,
    save_conversation_message,
    set_short_term_memory,
    get_short_term_memory,
    search_long_term_memory,
    list_user_conversations,
    get_user_conversation_messages,
    delete_user_conversation,
)
from company.leave_service import get_leave_summary, list_my_notifications, cancel_leave_request
from company.approval_service import list_pending_approvals, approve_request, reject_request, respond_to_approval_clarification, reconcile_pending_approval_records
from company.employee_service import get_user_service_history, get_employee_id, get_employee_profile, update_my_employee_profile
from company.request_service import list_my_department_requests, list_my_pending_requests
from company.pending_query_service import get_pending_lookup_result
from company.memory_service import get_my_workflow_details
from company.updates_service import list_updates, mark_update_read
from company.policy_service import get_active_policies, get_policy_rules
from company.email_service import create_email_draft, list_emails, send_email, mark_email_read, search_emails
from tools.knowledge_tools import list_accessible_documents, read_accessible_document, search_knowledge
from company.employee_document_service import (
    submit_employee_document,
    list_user_documents,
    get_employee_document,
    mark_employee_document_read,
)
from company.document_preview import render_document_preview
from company.profile_ui import render_user_profile_page
from company.user_profile_service import get_user_profile_settings


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Enterprise Workflow Platform",
    page_icon="AI",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "request_count" not in st.session_state:
    st.session_state.request_count = 0

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "clarification_context" not in st.session_state:
    st.session_state.clarification_context = None

if "view" not in st.session_state:
    st.session_state.view = "dashboard"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Initialize schema only. Company tenants and development seed data are
# provisioned explicitly, never silently created during a user login.
initialize_company_store()
if "company_id" not in st.session_state:
    st.session_state.company_id = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = ""


def current_role():
    user = get_user(st.session_state.user_id)
    if user and user.get("company_id") == st.session_state.company_id:
        return str(user.get("role", "employee")).lower()
    return ""


def render_login_screen():
    """Professional login screen using native Streamlit components."""
    st.markdown(
        """
        <style>
        .login-title {
            font-size: 38px;
            font-weight: 800;
            color: #30263c;
            margin-bottom: 4px;
        }

        .login-subtitle {
            color: #7b7088;
            font-size: 14px;
            margin-bottom: 30px;
        }

        .login-card {
            background: linear-gradient(135deg, #F0F8FF 0%, #FFF6FC 55%, #FFF5EC 100%);
            border: 1px solid #D4E3F3;
            border-radius: 22px;
            padding: 28px;
            box-shadow: 0 14px 40px rgba(90, 65, 120, 0.10);
        }

        .login-feature {
            background: linear-gradient(120deg, #EDF6FF, #FFF1FC);
            border: 1px solid #D9E5F3;
            border-radius: 14px;
            padding: 15px;
            margin: 10px 0;
        }

        .login-feature-title {
            color: #4a3a5c;
            font-size: 13px;
            font-weight: 800;
        }

        .login-feature-text {
            color: #81758f;
            font-size: 11px;
            margin-top: 4px;
            line-height: 1.5;
        }

        .login-security {
            background: linear-gradient(120deg, #EAF7FF, #FFF0FB, #FFF2E7);
            border: 1px solid #D6E4F3;
            border-radius: 12px;
            padding: 12px;
            color: #6546a1;
            font-size: 11px;
            margin-top: 18px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="login-title">Enterprise Workflow Platform</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="login-subtitle">'
        'AI Agent Coordination & Decision Engine  |  Secure enterprise workspace'
        '</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.25, 0.85], gap="large")

    # --------------------------------------------------------
    # LEFT SIDE
    # --------------------------------------------------------
    with left:
        st.markdown("### One intelligent workspace for your company")

        st.write(
            "Connect employees with the right AI agents, company information, "
            "enterprise tools, approval rules and business actions."
        )

        st.markdown(
            """
            <div class="login-feature">
                <div class="login-feature-title">* AI Agent Coordination</div>
                <div class="login-feature-text">
                    Understands natural enterprise requests and coordinates
                    the relevant specialist agents.
                </div>
            </div>

            <div class="login-feature">
                <div class="login-feature-title">[ORG] Company Context</div>
                <div class="login-feature-text">
                    Uses the latest company policies, employee information
                    and approved organizational data.
                </div>
            </div>

            <div class="login-feature">
                <div class="login-feature-title">! Intelligent Actions</div>
                <div class="login-feature-text">
                    Connects agents with enterprise tools and validates results
                    before important actions are completed.
                </div>
            </div>

            <div class="login-feature">
                <div class="login-feature-title">[SECURE]Â Secure Access</div>
                <div class="login-feature-text">
                    Your company, identity and role are verified by the backend.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="login-security">
                <b>Secure workspace</b><br>
                Your role and company permissions are resolved by the
                authentication backend after successful sign-in.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------
    # RIGHT SIDE
    # --------------------------------------------------------
    with right:
        with st.container(border=True):
            st.markdown("### Welcome back")
            st.caption("Sign in to EnterpriseFlow")
            login_mode = st.radio("Account", ["Sign in", "Create Account"], horizontal=True, key="login_mode")
            if login_mode == "Create Account":
                account_type = st.selectbox("Account type", ["Employee", "Admin"], key="registration_account_type")
                if account_type == "Admin":
                    st.info(
                        "Admin accounts cannot be created through public self-registration. "
                        "Ask an existing authorized Company Admin to create your account from "
                        "Company Administration → Employees. This prevents unauthorized privilege escalation."
                    )
                    return

                with st.form("employee_self_registration_form"):
                    reg_name = st.text_input("Full name", key="registration_name")
                    reg_email = st.text_input("Company work email", placeholder="name@company.com", key="registration_email")
                    reg_phone = st.text_input("Phone number", key="registration_phone")
                    reg_department = st.text_input("Department (optional)", key="registration_department")
                    reg_designation = st.text_input("Designation (optional)", key="registration_designation")
                    reg_employee_id = st.text_input("Employee ID (optional)", key="registration_employee_id")
                    reg_password = st.text_input("Create password", type="password", key="registration_password")
                    reg_confirm = st.text_input("Confirm password", type="password", key="registration_confirm_password")
                    register_clicked = st.form_submit_button("Create employee account", type="primary", use_container_width=True)
                if register_clicked:
                    if reg_password != reg_confirm:
                        st.error("Passwords do not match.")
                    else:
                        try:
                            created = register_employee(
                                reg_name, reg_email, reg_password, reg_department,
                                phone=reg_phone, designation=reg_designation,
                                employee_id=reg_employee_id,
                            )
                            st.success(f"Account created for {created['email']} (Employee ID: {created['employee_id']}). You can now sign in.")
                        except (ValueError, PermissionError) as exc:
                            st.error(str(exc))
                        except Exception:
                            st.error("Account creation failed. Please verify your company work email or contact your administrator.")
                return

            email_input = st.text_input(
                "Work email",
                placeholder="name@company.com",
                key="login_email",
            ).strip()

            password_input = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password",
                key="login_password",
            )

            st.caption(
                "Your role and permissions are automatically resolved after sign-in."
            )

            sign_in = st.button(
                "Sign in",
                type="primary",
                width="stretch",
                key="login_button",
            )

            if sign_in:
                if not email_input or not password_input:
                    st.error("Please enter your work email and password.")
                else:
                    try:
                        user = authenticate_user_by_email(
                            email_input,
                            password_input,
                        )

                        st.session_state.company_id = user["company_id"]
                        st.session_state.user_id = user["user_id"]
                        st.session_state.authenticated = True
                        st.session_state.view = "dashboard"
                        st.session_state.messages = []
                        st.session_state.last_result = None
                        st.session_state.request_count = 0
                        st.session_state.conversation_id = None
                        st.session_state.clarification_context = None

                        st.rerun()

                    except PermissionError as exc:
                        st.error(str(exc))

                    except Exception:
                        st.error(
                            "Unable to sign in. Please verify your "
                            "work email and password."
                        )
# ============================================================
# HELPERS
# ============================================================

def pretty(value):
    if value is None:
        return "-"
    if isinstance(value, dict):
        action = value.get("action") or value.get("status")
        return str(action or value)
    if isinstance(value, list):
        return ", ".join(str(x) for x in value) if value else "-"
    text = str(value)
    return text.replace("_", " ").strip()


def decision_text(decision):
    if isinstance(decision, dict):
        return str(decision.get("action", "-")).upper()
    return str(decision or "-").upper()


def validation_text(validation):
    if not isinstance(validation, dict):
        return "-"
    return str(validation.get("status", "-")).upper()


def get_agents(result):
    agents = result.get("assigned_agents") or []
    if not agents and result.get("assigned_agent"):
        agents = [result["assigned_agent"]]
    return agents


def get_tools(result):
    tools = result.get("tool_names") or result.get("tools") or []
    if not tools and result.get("selected_tool"):
        tools = [result["selected_tool"]]
    return tools


def get_message_result(message):
    """Return current workflow metadata, including from persisted chat history."""
    result = message.get("result")
    if isinstance(result, dict):
        return result

    metadata = message.get("metadata")
    if not isinstance(metadata, dict):
        return None

    # Older persisted messages only stored workflow_id/intent. Do not invent
    # agent/tool values for those records; render cards only when routing data exists.
    routing_keys = ("department", "assigned_agents", "tool_names", "workflow_status", "decision")
    if not any(key in metadata for key in routing_keys):
        return None

    validation_status = metadata.get("validation_status")
    return {
        "department": metadata.get("department"),
        "assigned_agents": metadata.get("assigned_agents") or [],
        "tool_names": metadata.get("tool_names") or [],
        "status": metadata.get("workflow_status"),
        "validation": {"status": validation_status} if validation_status else {},
        "decision": metadata.get("decision"),
        "request_category": metadata.get("request_category"),
        "intent": metadata.get("intent"),
    }


def render_result_metadata(result):
    """Show the selected route and validation beneath each assistant response."""
    if not isinstance(result, dict):
        return

    agents = get_agents(result)
    tools = get_tools(result)
    validation_data = result.get("validation")
    validation = validation_text(validation_data)
    if isinstance(validation_data, dict):
        workflow_status = validation_data.get("status") or result.get("status") or "-"
    else:
        workflow_status = result.get("status") or validation or "-"

    values = [
        ("DEPARTMENT", pretty(result.get("department") or result.get("primary_department"))),
        ("AGENT" if len(agents) == 1 else "AGENTS", ", ".join(str(x) for x in agents) if agents else "-"),
        ("TOOL SELECTION", ", ".join(str(x) for x in tools) if tools else "-"),
        ("STATUS", workflow_status),
        ("VALIDATION", validation),
        ("DECISION", decision_text(result.get("decision"))),
    ]

    cards = []
    for label, value in values:
        cards.append(
            '<div class="mini-card">'
            f'<div class="mini-label">{html_escape(str(label))}</div>'
            f'<div class="mini-value">{html_escape(str(value if value is not None else "-"))}</div>'
            '</div>'
        )

    st.markdown(
        '<div class="result-mini-grid">' + "".join(cards) + '</div>',
        unsafe_allow_html=True,
    )


def render_markdown_response(text):
    if not text:
        return "No response generated."
    st.markdown(text)


def render_workflow_trace(result):
    trace = result.get("trace") or []

    if not trace:
        st.markdown(
            """
            <div class="empty-trace">
                <div class="trace-icon">*Å’</div>
                <div class="trace-title">Workflow ready</div>
                <div class="trace-text">
                    Submit an enterprise request to see the live execution trace.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    stage_labels = {
        "understanding": ("01", "AI Understanding"),
        "coordination": ("02", "Agent Coordination"),
        "planning": ("03", "Tool Planning"),
        "execution": ("04", "Tool Execution"),
        "validation": ("05", "Validation"),
        "decision": ("06", "Decision"),
        "response": ("07", "Response"),
    }

    for item in trace:
        stage = str(item.get("stage", "workflow")).lower()
        number, label = stage_labels.get(
            stage,
            ("*", pretty(stage).title()),
        )

        detail = item.get("message", "")

        if stage == "execution":
            agent = item.get("agent")
            tools = item.get("tools") or []
            if agent:
                detail = f"{agent}"
                if tools:
                    detail += "  |  " + ", ".join(tools)

        st.markdown(
            f"""
            <div class="trace-item">
                <div class="trace-number">{number}</div>
                <div>
                    <div class="trace-label">{label}</div>
                    <div class="trace-detail">{detail}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_message(role, content, result=None, timestamp=None):
    if role == "user":
        st.markdown(
            f"""
            <div class="message-row user-row">
                <div class="message-bubble user-bubble">
                    <div class="message-label">YOU</div>
                    <div class="message-content">{content}</div>
                    <div class="message-time">{timestamp or ""}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        """
        <div class="message-row assistant-row">
            <div class="assistant-avatar">*</div>
            <div class="message-bubble assistant-bubble">
                <div class="message-label">ENTERPRISE AI</div>
        """,
        unsafe_allow_html=True,
    )

    render_markdown_response(content)

    st.markdown(
        f"""
                <div class="message-time">{timestamp or ""}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if result:
        agents = get_agents(result)
        tools = get_tools(result)
        decision = decision_text(result.get("decision"))
        validation = validation_text(result.get("validation"))

        st.markdown(
            f"""
            <div class="result-mini-grid">
                <div class="mini-card">
                    <div class="mini-label">DEPARTMENT</div>
                    <div class="mini-value">{pretty(result.get("department"))}</div>
                </div>
                <div class="mini-card">
                    <div class="mini-label">AGENT{"" if len(agents) == 1 else "S"}</div>
                    <div class="mini-value">{", ".join(agents) if agents else "-"}</div>
                </div>
                <div class="mini-card">
                    <div class="mini-label">TOOLS</div>
                    <div class="mini-value">{", ".join(tools) if tools else "-"}</div>
                </div>
                <div class="mini-card">
                    <div class="mini-label">VALIDATION</div>
                    <div class="mini-value status-ok">{validation}</div>
                </div>
                <div class="mini-card">
                    <div class="mini-label">DECISION</div>
                    <div class="mini-value">{decision}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def process_request(prompt):
    prompt = prompt.strip()

    if not prompt:
        return

    now = datetime.now().strftime("%I:%M %p").lstrip("0")
    company_id = st.session_state.company_id
    user_id = st.session_state.user_id

    if not st.session_state.conversation_id:
        try:
            conversation = create_conversation(company_id, user_id, title=prompt[:100])
            st.session_state.conversation_id = str(conversation.get("conversation_id") or "")
        except Exception:
            st.session_state.conversation_id = None

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt,
            "time": now,
        }
    )
    if st.session_state.conversation_id:
        try:
            save_conversation_message(company_id, st.session_state.conversation_id, user_id, "user", prompt)
        except Exception:
            pass

    # ---------------------------------------------------------
    # CHECK WHETHER THIS IS A CONFIRMATION
    # ---------------------------------------------------------
    normalized = (
        prompt.lower()
        .replace(",", " ")
        .replace(".", " ")
        .replace("!", " ")
        .replace("?", " ")
    )

    normalized = " ".join(normalized.split())

    confirmation_phrases = {
        "yes",
        "yes proceed",
        "yes please proceed",
        "proceed",
        "confirm",
        "confirmed",
        "go ahead",
        "okay proceed",
        "ok proceed",
        "ok",
        "yes go ahead",
    }

    is_confirmation = normalized in confirmation_phrases

    previous_result = st.session_state.get(
        "last_result"
    )
    current_memory = {}
    if st.session_state.conversation_id:
        try:
            current_memory = get_short_term_memory(company_id, user_id, st.session_state.conversation_id).get("current_workflow", {})
        except Exception:
            current_memory = {}
    if isinstance(current_memory, dict) and isinstance(current_memory.get("workflow_state"), dict):
        remembered_result = current_memory["workflow_state"]
        if not isinstance(previous_result, dict) or str(previous_result.get("workflow_id") or "") != str(remembered_result.get("workflow_id") or ""):
            previous_result = remembered_result
            st.session_state.last_result = remembered_result

    pending_reply_state = classify_pending_confirmation_reply(prompt, previous_result)
    should_resume = pending_reply_state == "confirm"
    should_cancel_pending = pending_reply_state == "cancel"
    should_hold_pending = pending_reply_state == "hold"
    should_continue_clarification = False
    has_new_request = False

    clarification_state = previous_result.get("validation", {}) if isinstance(previous_result, dict) else {}
    if isinstance(clarification_state, dict) and clarification_state.get("status") == "needs_clarification":
        # Short replies are interpreted against the active request; an
        # explicit new question/action starts a separate workflow.
        has_new_request = is_clear_new_request_during_clarification(
            prompt,
            str(previous_result.get("raw_message") or ""),
        )
        previous_validation = (
            previous_result.get("validation", {})
            if isinstance(previous_result, dict)
            else {}
        )

        awaiting_clarification = (
            isinstance(previous_validation, dict)
            and previous_validation.get("status") == "needs_clarification"
        )

        should_continue_clarification = (
            awaiting_clarification
            and len(prompt.split()) <= 16
            and not has_new_request
        )

    # ---------------------------------------------------------
    # RUN OR RESUME WORKFLOW
    # ---------------------------------------------------------
    try:
        with st.spinner(
            "Coordinating agents and enterprise tools..."
        ):

            if should_resume:

                # Reuse the existing workflow.
                result = resume_workflow(
                    previous_result=previous_result,
                    confirmation_message=prompt,
                )

            elif should_cancel_pending:
                result = cancel_pending_workflow(
                    previous_result=previous_result,
                    cancellation_message=prompt,
                )

            elif should_hold_pending:
                # An unconfirmed write always takes precedence over a new query.
                result = hold_pending_confirmation_result(previous_result)

            elif is_simple_greeting(prompt):
                result = {
                    "response": "Hi! I can help with HR requests, IT support, company information, pending requests, projects and documents. Tell me what you need.",
                    "raw_message": prompt,
                    "company_id": company_id,
                    "user_id": user_id,
                    "user_role": current_role(),
                    "workflow_id": "",
                    "status": "completed",
                    "validation": {"status": "success"},
                    "decision": {"action": "CONTINUE", "reason": "Greeting handled locally."},
                    "request_category": "information_request",
                    "intent": "greeting",
                    "department": "Enterprise",
                    "departments": ["Enterprise"],
                    "assigned_agents": ["AI Coordinator"],
                    "tool_names": ["local_greeting"],
                    "tools": ["local_greeting"],
                    "tool_plan": [{"tool": "local_greeting", "agent": "AI Coordinator", "purpose": "Respond to a greeting without external AI providers."}],
                    "tool_results": [{"tool": "local_greeting", "status": "success", "executed": False}],
                }

            elif pending_lookup_requested(prompt):
                result = get_pending_lookup_result(
                    prompt, company_id, user_id, current_role()
                )

            elif should_continue_clarification and isinstance(previous_result, dict):
                base_message = str(previous_result.get("raw_message") or "").strip()
                combined_message = f"{base_message}\nAdditional information: {prompt}".strip()
                result = run_workflow(
                    combined_message,
                    conversation_history=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]],
                    company_id=company_id,
                    user_id=user_id,
                    user_role=current_role(),
                    workflow_id=str(previous_result.get("workflow_id") or "") or None,
                )

            else:
                history_for_run = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ]
                if (
                    has_new_request
                    and isinstance(clarification_state, dict)
                    and clarification_state.get("status") == "needs_clarification"
                ):
                    # The active clarification pair is about the old request.
                    # Exclude that final user/assistant pair so the model cannot
                    # reinterpret a fresh IT/HR task as a slot value for it.
                    history_for_run = history_for_run[:-2] if len(history_for_run) >= 2 else []

                result = run_workflow(
                    prompt,
                    conversation_history=history_for_run,
                    company_id=company_id,
                    user_id=user_id,
                    user_role=current_role(),
                )

        response = result.get(
            "response",
            "The workflow completed, but no final response was generated.",
        )

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response,
                "time": datetime.now().strftime("%I:%M %p").lstrip("0"),
                "result": result,
            }
        )

        st.session_state.last_result = result
        st.session_state.request_count += 1
        validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
        if validation.get("status") == "needs_clarification":
            st.session_state.clarification_context = {
                "workflow_id": result.get("workflow_id"),
                "raw_message": result.get("raw_message"),
                "intent": result.get("intent"),
            }
        else:
            st.session_state.clarification_context = None
        if st.session_state.conversation_id:
            try:
                save_conversation_message(
                    company_id, st.session_state.conversation_id, user_id, "assistant", str(response),
                    metadata={
                        "workflow_id": result.get("workflow_id"),
                        "validation_status": validation.get("status"),
                        "intent": result.get("intent"),
                        "request_category": result.get("request_category"),
                        "department": result.get("department") or result.get("primary_department"),
                        "assigned_agents": get_agents(result),
                        "tool_names": get_tools(result),
                        "workflow_status": result.get("status"),
                        "decision": result.get("decision"),
                    },
                )
                set_short_term_memory(
                    company_id, user_id, "current_workflow",
                    {
                        "workflow_id": result.get("workflow_id"),
                        "request": result.get("raw_message"),
                        "intent": result.get("intent"),
                        "status": validation.get("status"),
                        "awaiting_clarification": validation.get("status") == "needs_clarification",
                        "workflow_state": {key: result.get(key) for key in ("raw_message", "workflow_id", "company_id", "user_id", "user_role", "validation", "decision", "details", "tool_plan", "tool_results", "tool_names", "tools", "assigned_agents", "departments", "request_category", "intent", "confirmation_requested", "confirmation_received", "response")},
                    },
                    conversation_id=st.session_state.conversation_id,
                    workflow_id=str(result.get("workflow_id") or ""),
                )
            except Exception:
                pass

    except Exception as exc:

        error_text = (
            f"I couldn't complete the workflow: {exc}"
        )

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": error_text,
                "time": datetime.now().strftime("%I:%M %p").lstrip("0"),
                "result": None,
            }
        )
        if st.session_state.conversation_id:
            try:
                save_conversation_message(company_id, st.session_state.conversation_id, user_id, "assistant", error_text, metadata={"error": True})
            except Exception:
                pass

# ============================================================
# CUSTOM HTML / CSS FRONTEND
# ============================================================

st.markdown(
    """
    <style>

    /* ========================================================
       GLOBAL
       ======================================================== */

    .stApp {
        background:
            radial-gradient(circle at 15% 0%, rgba(123, 75, 214, 0.08), transparent 30%),
            radial-gradient(circle at 85% 10%, rgba(165, 109, 232, 0.08), transparent 28%),
            #f7f5fb;
        color: #30263c;
    }

    header[data-testid="stHeader"] {
        background: transparent;
    }

    #MainMenu,
    footer {
        visibility: hidden;
    }

    .block-container {
        max-width: 1500px;
        padding: 1.25rem 1.5rem 7rem 1.5rem;
    }


    .account-card {
        display: flex; align-items: center; gap: 9px; padding: 10px 11px;
        border: 1px solid #e3dced; border-radius: 13px; background: #fff;
    }
    .account-avatar {
        width: 30px; height: 30px; min-width: 30px; border-radius: 10px;
        display:flex; align-items:center; justify-content:center;
        background: #eee7ff; color: #6f46bd; font-weight: 800; font-size: 12px;
    }
    .account-info { flex: 1; min-width: 0; }
    .account-name { color:#43354f; font-weight:800; font-size:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .account-role { color:#8b7e99; font-size:8px; margin-top:2px; }
    .account-dot { color:#38a169; font-size:8px; }
    .tenant-card {
        margin-top: 8px; padding: 10px 11px; border-radius: 13px;
        border: 1px solid #e7dff0; background: #faf8fd;
    }
    .tenant-label { color:#8d809b; font-size:7px; font-weight:800; letter-spacing:1px; }
    .tenant-name { color:#4b3b5b; font-size:9px; font-weight:800; margin-top:4px; }
    .tenant-id { color:#998da6; font-size:7px; margin-top:2px; }

    /* ========================================================
       SIDEBAR
       ======================================================== */

    section[data-testid="stSidebar"] {
        background: #fbf9fe;
        border-right: 1px solid #e5dff0;
    }

    section[data-testid="stSidebar"] > div {
        padding: 1.1rem 0.9rem;
    }

    .brand {
        padding: 0.5rem 0.5rem 1.2rem 0.5rem;
        border-bottom: 1px solid #e4dff0;
        margin-bottom: 1rem;
    }

    .brand-icon {
        display: inline-flex;
        width: 38px;
        height: 38px;
        align-items: center;
        justify-content: center;
        border-radius: 11px;
        background: linear-gradient(135deg, #7b4bd6, #a56de8);
        color: #ffffff;
        font-weight: 800;
        margin-right: 9px;
    }

    .brand-text {
        display: inline-block;
        vertical-align: middle;
        color: #2e2539;
        font-weight: 750;
        line-height: 1.25;
        font-size: 14px;
    }

    .side-title {
        color: #766b86;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        margin: 18px 8px 8px;
    }

    .agent-card {
        background: #faf8ff;
        border: 1px solid #e3dced;
        border-radius: 12px;
        padding: 11px 12px;
        margin: 7px 0;
    }

    .agent-name {
        color: #3f354c;
        font-size: 12px;
        font-weight: 700;
    }

    .agent-status {
        color: #7b4bd6;
        font-size: 10px;
        margin-top: 5px;
    }

    .side-note {
        margin-top: 18px;
        padding: 12px;
        border: 1px solid #e3dced;
        background: #f8f6fc;
        border-radius: 12px;
        color: #766b86;
        font-size: 10px;
        line-height: 1.55;
    }

    /* ========================================================
       TOP HEADER
       ======================================================== */

    .topbar {
        background: #ffffff;
        border: 1px solid #ddd4ea;
        border-radius: 20px;
        padding: 22px 26px;
        margin-bottom: 18px;
        box-shadow: 0 10px 30px rgba(92, 64, 125, 0.10);
    }

    .top-title {
        font-size: 25px;
        font-weight: 800;
        color: #2f2540;
        letter-spacing: -0.5px;
    }

    .top-subtitle {
        color: #786d88;
        font-size: 12px;
        margin-top: 5px;
    }

    .online-pill {
        float: right;
        margin-top: -35px;
        border: 1px solid rgba(123, 75, 214, 0.25);
        background: rgba(123, 75, 214, 0.08);
        color: #7b4bd6;
        border-radius: 999px;
        padding: 8px 13px;
        font-size: 10px;
        font-weight: 750;
    }

    /* ========================================================
       PANELS
       ======================================================== */

    .panel {
        background: #ffffff;
        border: 1px solid #ddd5eb;
        border-radius: 18px;
        overflow: hidden;
    }

    .panel-header {
        padding: 17px 19px;
        border-bottom: 1px solid #e8e0f2;
    }

    .panel-title {
        color: #30263c;
        font-size: 14px;
        font-weight: 800;
    }

    .panel-subtitle {
        color: #81758f;
        font-size: 10px;
        margin-top: 4px;
    }

    /* ========================================================
       CHAT
       ======================================================== */

    .chat-empty {
        min-height: 360px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: #756985;
        padding: 40px;
    }

    .empty-icon {
        width: 58px;
        height: 58px;
        border-radius: 18px;
        background: linear-gradient(135deg, #eadfff, #e2d5f7);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        margin-bottom: 15px;
    }

    .empty-title {
        color: #3b304c;
        font-size: 15px;
        font-weight: 750;
    }

    .empty-text {
        max-width: 430px;
        font-size: 11px;
        line-height: 1.6;
        margin: 6px auto 0;
    }

    .message-row {
        display: flex;
        margin: 18px 0;
    }

    .user-row {
        justify-content: flex-end;
    }

    .assistant-row {
        justify-content: flex-start;
        gap: 9px;
    }

    .assistant-avatar {
        width: 30px;
        height: 30px;
        min-width: 30px;
        border-radius: 10px;
        background: linear-gradient(135deg, #7b4bd6, #9a61df);
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 13px;
    }

    .message-bubble {
        max-width: 82%;
        padding: 14px 16px;
        border-radius: 16px;
        line-height: 1.65;
        font-size: 12px;
    }

    .user-bubble {
        background: #eee7ff;
        border: 1px solid #c9b8ee;
        color: #3c314b;
        border-bottom-right-radius: 5px;
    }

    .assistant-bubble {
        background: #ffffff;
        border: 1px solid #ded6e9;
        color: #40364d;
        border-bottom-left-radius: 5px;
        width: calc(100% - 40px);
    }

    .assistant-bubble table {
        font-size: 11px;
    }

    .message-label {
        color: #756585;
        font-size: 8px;
        font-weight: 800;
        letter-spacing: 1px;
        margin-bottom: 5px;
    }

    .message-content {
        white-space: pre-wrap;
    }

    .message-time {
        color: #8d8199;
        font-size: 8px;
        margin-top: 7px;
    }

    .result-mini-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 7px;
        margin: 8px 0 18px 0;
    }

    .mini-card {
        background: #f6f3fb;
        border: 1px solid #e3dced;
        border-radius: 10px;
        padding: 9px;
        min-height: 54px;
    }

    .mini-label {
        color: #506782;
        font-size: 7px;
        letter-spacing: 0.9px;
        font-weight: 800;
    }

    .mini-value {
        color: #41374e;
        font-size: 9px;
        font-weight: 700;
        margin-top: 5px;
        word-break: break-word;
    }

    .status-ok {
        color: #7b4bd6;
    }

    /* ========================================================
       WORKFLOW TRACE
       ======================================================== */

    .trace-body {
        padding: 14px;
    }

    .trace-item {
        display: flex;
        gap: 10px;
        padding: 11px 10px;
        margin-bottom: 8px;
        border: 1px solid #e4dcef;
        border-radius: 11px;
        background: #f8f6fc;
    }

    .trace-number {
        color: #8055d6;
        font-size: 9px;
        font-weight: 800;
        min-width: 22px;
    }

    .trace-label {
        color: #3f354c;
        font-size: 10px;
        font-weight: 750;
    }

    .trace-detail {
        color: #756982;
        font-size: 9px;
        line-height: 1.4;
        margin-top: 3px;
    }

    .empty-trace {
        padding: 55px 20px;
        text-align: center;
        color: #756985;
    }

    .trace-icon {
        font-size: 28px;
        color: #9b8caf;
    }

    .trace-title {
        color: #5c5068;
        font-weight: 750;
        font-size: 12px;
        margin-top: 8px;
    }

    .trace-text {
        font-size: 10px;
        margin-top: 5px;
        line-height: 1.5;
    }

    /* ========================================================
       INPUT
       ======================================================== */


    [data-testid="stMainBlockContainer"] {
        padding-bottom: 105px !important;
    }

    [data-testid="stChatInput"] {
        left: calc(50% + 175px) !important;
        width: min(900px, calc(72vw - 175px)) !important;
    }

    div[data-testid="stChatInput"] {
        position: fixed;
        bottom: 18px;
        left: 50%;
        transform: translateX(-50%);
        width: min(900px, 72vw);
        z-index: 999;
    }

    div[data-testid="stChatInput"] > div {
        background: #ffffff !important;
        border: 1px solid #cfc4e3 !important;
        border-radius: 15px !important;
        box-shadow: 0 10px 30px rgba(92, 64, 125, 0.14);
    }

    div[data-testid="stChatInput"] textarea {
        color: #3c314b !important;
    }

    div[data-testid="stChatInput"] textarea::placeholder {
        color: #8a7d98 !important;
    }

    /* Streamlit buttons */
    .stButton > button {
        border-radius: 10px;
        border: 1px solid #d7cdea;
        background: #faf8ff;
        color: #40354f;
    }

    .stButton > button:hover {
        border-color: #8a65c7;
        color: #ffffff;
    }

    /* Hide default widget labels where appropriate */
    .stTextInput label,
    .stTextArea label {
        color: #766b86 !important;
    }

    @media (max-width: 1100px) {
        .result-mini-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }

    
    /* ========================================================
       FINAL LIGHT + PURPLE OVERRIDES
       ======================================================== */

    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {
        background: #f8f6fc !important;
        color: #332943 !important;
    }

    .topbar {
        background: linear-gradient(135deg, #ffffff 0%, #faf7ff 100%) !important;
        border: 1px solid #ded3ee !important;
        box-shadow: 0 10px 28px rgba(104, 73, 145, 0.10) !important;
    }

    .top-title {
        color: #332943 !important;
    }

    .top-subtitle {
        color: #796d89 !important;
    }

    .panel {
        background: #ffffff !important;
        border: 1px solid #e2d8ee !important;
        box-shadow: 0 8px 24px rgba(104, 73, 145, 0.07);
    }

    .panel-header {
        background: #ffffff !important;
        border-bottom: 1px solid #eee8f5 !important;
    }

    .panel-title {
        color: #3b2e4d !important;
    }

    .panel-subtitle {
        color: #887b98 !important;
    }

    .chat-empty {
        background: #ffffff !important;
    }

    .empty-title {
        color: #3b304c !important;
    }

    .assistant-bubble {
        background: #ffffff !important;
        border-color: #e0d6ec !important;
        color: #40354f !important;
        box-shadow: 0 5px 18px rgba(104, 73, 145, 0.05);
    }

    .user-bubble {
        background: #eee5ff !important;
        border-color: #cdb9ef !important;
        color: #433052 !important;
    }

    .mini-card {
        background: #faf8fd !important;
        border-color: #e5dcef !important;
    }

    .trace-item {
        background: #fbf9fe !important;
        border-color: #e5dcef !important;
    }

    .trace-label {
        color: #463758 !important;
    }

    .trace-detail {
        color: #81738f !important;
    }

    div[data-testid="stChatInput"] > div {
        background: #ffffff !important;
        border: 1px solid #cdbbe7 !important;
        box-shadow: 0 10px 30px rgba(104, 73, 145, 0.14) !important;
    }

    div[data-testid="stChatInput"] textarea {
        color: #40354f !important;
    }

    div[data-testid="stChatInput"] textarea::placeholder {
        color: #91849e !important;
    }


    /* ========================================================
       PROFESSIONAL SIGN-IN
       ======================================================== */

    .login-shell {
        min-height: 320px;
        display: grid;
        grid-template-columns: 1.35fr 0.9fr;
        gap: 18px;
        align-items: stretch;
        margin: 4vh auto 0;
    }

    .login-hero, .login-card-wrap {
        background: linear-gradient(145deg, #ffffff 0%, #faf7ff 100%);
        border: 1px solid #e1d7ef;
        border-radius: 26px;
        box-shadow: 0 18px 50px rgba(92, 64, 125, 0.11);
    }

    .login-hero {
        padding: 34px 38px;
        position: relative;
        overflow: hidden;
    }

    .login-hero::after {
        content: "";
        position: absolute;
        width: 260px;
        height: 260px;
        right: -90px;
        top: -100px;
        border-radius: 50%;
        background: rgba(131, 88, 211, 0.08);
    }

    .login-brand-row { display: flex; align-items: center; gap: 13px; position: relative; z-index: 1; }
    .login-brand-mark {
        width: 48px; height: 48px; border-radius: 15px;
        display: flex; align-items: center; justify-content: center;
        color: #fff; font-size: 19px; font-weight: 800;
        background: linear-gradient(135deg, #7044c8, #a267e7);
        box-shadow: 0 9px 22px rgba(112, 68, 200, 0.22);
    }
    .login-brand-name { font-size: 15px; font-weight: 800; color: #332943; }
    .login-brand-caption { font-size: 10px; color: #80758f; margin-top: 2px; }
    .login-kicker {
        margin-top: 52px; color: #7a4dd0; font-size: 9px; font-weight: 800; letter-spacing: 1.5px;
    }
    .login-hero-title {
        margin-top: 10px; color: #2f2540; font-size: 28px; line-height: 1.15; font-weight: 850; max-width: 660px;
        letter-spacing: -0.8px;
    }
    .login-hero-copy {
        margin-top: 12px; color: #73687f; font-size: 12px; line-height: 1.7; max-width: 640px;
    }
    .login-feature-grid {
        margin-top: 24px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
    }
    .login-feature {
        display: flex; gap: 10px; padding: 11px; border: 1px solid #e9e1f2;
        border-radius: 14px; background: rgba(255,255,255,0.72);
    }
    .login-feature-icon {
        width: 28px; height: 28px; min-width: 28px; border-radius: 9px;
        display: flex; align-items: center; justify-content: center;
        background: #f0e9ff; color: #7952c8; font-weight: 800; font-size: 11px;
    }
    .login-feature b { display: block; color: #443854; font-size: 10px; }
    .login-feature span { display: block; margin-top: 3px; color: #827691; font-size: 9px; line-height: 1.4; }
    .login-footer-note { margin-top: 20px; font-size: 8px; color: #9a8da8; position: relative; z-index: 1; }

    .login-card-wrap { padding: 30px 30px 12px; min-height: 120px; }
    .login-card-heading { color: #342845; font-size: 21px; font-weight: 820; }
    .login-card-subheading { margin-top: 5px; color: #887b98; font-size: 11px; }
    .login-panel-spacer { height: 1px; }
    .signin-panel-label { color: #7350b8; font-size: 9px; font-weight: 800; letter-spacing: 1.4px; margin: -102px 0 12px 0; }
    .signin-hint {
        font-size: 9px; line-height: 1.5; color: #8a7d97;
        padding: 9px 11px; border: 1px solid #e9e2f2; background: #faf8fd; border-radius: 11px; margin: 4px 0 12px;
    }
    .demo-access-card {
        margin-top: 18px; padding: 13px 14px; border: 1px solid #e5ddef;
        border-radius: 13px; background: #fbf9fe;
    }
    .demo-access-title { color: #4b3c5d; font-weight: 800; font-size: 9px; letter-spacing: .8px; text-transform: uppercase; margin-bottom: 8px; }
    .demo-access-row { display: flex; justify-content: space-between; gap: 10px; color: #7b6f89; font-size: 9px; padding: 4px 0; }
    .demo-access-row code { color: #63469d; background: #f0eaff; padding: 2px 6px; border-radius: 6px; font-size: 8px; }
    .demo-access-note { margin-top: 7px; color: #9b90a7; font-size: 8px; line-height: 1.45; }

    @media (max-width: 900px) {
        .login-shell { grid-template-columns: 1fr; }
        .signin-panel-label { margin: 0 0 12px 0; }
        .login-feature-grid { grid-template-columns: 1fr; }
    }


    /* EnterpriseFlow palette based on the provided color reference.
       Blue #84B9F2, lavender #F0D3FF, peach #FFD8C5, cyan #CDEFFF;
       purple #7B3CFF, red #F33737, yellow #FFBE0B, ink #171717. */
    :root {
        --ef-blue: #84B9F2;
        --ef-lavender: #F0D3FF;
        --ef-peach: #FFD8C5;
        --ef-cyan: #CDEFFF;
        --ef-purple: #7B3CFF;
        --ef-red: #F33737;
        --ef-yellow: #FFBE0B;
        --ef-ink: #171717;
        --ef-muted: #5C6170;
        --ef-border: #D7DFEA;
        --ef-paper: #FBFAF8;
    }
    .stApp {
        background: radial-gradient(circle at 8% 0%, rgba(132,185,242,.20), transparent 31%),
                    radial-gradient(circle at 92% 8%, rgba(240,211,255,.25), transparent 30%),
                    var(--ef-paper) !important;
        color: var(--ef-ink) !important;
    }
    .block-container { max-width: 1540px; }
    section[data-testid="stSidebar"] { background: #F8F7FC !important; border-right: 1px solid var(--ef-border) !important; }
    h1, h2, h3, h4, h5, h6, .top-title, .chat-heading-title { color: #17171F !important; letter-spacing: -0.02em; }
    p, li, label, div[data-testid="stMarkdownContainer"] { color: inherit; }
    .topbar, .chat-heading {
        background: linear-gradient(115deg, #FFFFFF 0%, #F0F8FF 50%, #FFF5EE 100%) !important;
        border: 1px solid var(--ef-border) !important;
        box-shadow: 0 12px 28px rgba(37, 48, 72, .07) !important;
    }
    .brand-icon { background: linear-gradient(135deg, var(--ef-purple), #84B9F2) !important; }
    .account-card, .agent-card, .side-note, .mini-card, .trace-item, .login-feature {
        border-color: var(--ef-border) !important;
    }
    .agent-card:nth-of-type(2n) { background: #F0F8FF !important; }
    .agent-card:nth-of-type(3n) { background: #FFF4ED !important; }
    .mini-card { background: #F4F8FC !important; border-radius: 12px !important; padding: 12px !important; min-height: 66px !important; }
    .mini-label { color: #51566A !important; font-size: 10px !important; font-weight: 800 !important; }
    .mini-value { color: #17171F !important; font-size: 12px !important; font-weight: 700 !important; }
    .result-mini-grid { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; gap: 9px !important; }
    .message-bubble { font-size: 14px !important; line-height: 1.65 !important; }
    .user-bubble { background: #EAF4FF !important; border-color: #B8D8FA !important; color: #17171F !important; }
    .assistant-bubble { border-color: var(--ef-border) !important; color: #22222B !important; }
    .stButton > button, div[data-testid="stFormSubmitButton"] button, div[data-testid="stDownloadButton"] button {
        border-radius: 11px !important; border: 1px solid #C8D3E3 !important;
        background: #FFFFFF !important; color: #20212A !important;
        font-weight: 700 !important; min-height: 42px !important;
        transition: all .16s ease !important;
    }
    .stButton > button:hover, div[data-testid="stDownloadButton"] button:hover {
        background: #EFF7FF !important; border-color: var(--ef-blue) !important; color: #17171F !important;
    }
    .stButton > button[kind="primary"], div[data-testid="stFormSubmitButton"] button[kind="primary"], button[kind="primary"] {
        background: var(--ef-purple) !important; border-color: var(--ef-purple) !important; color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"]:hover, div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover, button[kind="primary"]:hover {
        background: #642BE6 !important; border-color: #642BE6 !important; color: #FFFFFF !important;
    }
    div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea, div[data-testid="stNumberInput"] input,
    div[data-testid="stDateInput"] input, div[data-baseweb="select"] > div {
        background: #FFFFFF !important; color: #17171F !important; border-color: #C8D3E3 !important; border-radius: 10px !important;
    }
    div[data-testid="stTextInput"] label, div[data-testid="stTextArea"] label, div[data-testid="stNumberInput"] label,
    div[data-testid="stSelectbox"] label, div[data-testid="stDateInput"] label, div[data-testid="stFileUploader"] label {
        color: #363746 !important; font-weight: 700 !important; font-size: 13px !important;
    }
    div[data-testid="stDataFrame"], div[data-testid="stTable"] { border: 1px solid var(--ef-border) !important; border-radius: 12px !important; overflow: hidden !important; }
    div[data-testid="stAlert"] { border-radius: 12px !important; }
    div[data-testid="stTabs"] button[role="tab"] { font-weight: 700 !important; color: #505467 !important; }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color: var(--ef-purple) !important; border-bottom-color: var(--ef-purple) !important; }
    a { color: #6435D6 !important; }
    code { background: #F0D3FF !important; color: #24202B !important; border-radius: 5px !important; }
    .login-security { background: #EAF7FF !important; border-color: #BEDCF6 !important; color: #26364C !important; }

    /* ========================================================
       V9 FULL-WORKSPACE PASTEL SYSTEM
       Applied globally to login, employee, coordinator, admin,
       projects, profile, approvals, documents and settings pages.
       Accessible text contrast is retained over pastel surfaces.
       ======================================================== */
    :root {
        --ef-blue: #84B9F2;
        --ef-pink: #F0D3FF;
        --ef-orange: #FFD8C5;
        --ef-sky: #CDEFFF;
        --ef-primary: #3979D8;
        --ef-primary-dark: #285EB3;
        --ef-ink: #26334B;
        --ef-muted: #58677D;
        --ef-border: #D6E2F0;
        --ef-surface: #FFFFFF;
        --ef-blue-surface: #EDF6FF;
        --ef-pink-surface: #FFF1FC;
        --ef-orange-surface: #FFF2E9;
        --ef-sky-surface: #EAFBFF;
        --ef-shadow: 0 10px 28px rgba(63, 91, 132, .09);
    }

    html, body, [data-testid="stAppViewContainer"] {
        color: var(--ef-ink) !important;
    }
    .stApp, [data-testid="stAppViewContainer"] > .main {
        background:
            radial-gradient(ellipse at 0% 0%, rgba(132,185,242,.30) 0%, transparent 32%),
            radial-gradient(ellipse at 98% 4%, rgba(240,211,255,.34) 0%, transparent 30%),
            radial-gradient(ellipse at 100% 86%, rgba(255,216,197,.30) 0%, transparent 28%),
            radial-gradient(ellipse at 16% 100%, rgba(205,239,255,.36) 0%, transparent 32%),
            linear-gradient(135deg, #F8FBFF 0%, #FFF9FD 47%, #FFF9F3 100%) !important;
        color: var(--ef-ink) !important;
    }
    [data-testid="stMain"], [data-testid="stMainBlockContainer"] {
        background: transparent !important;
    }
    [data-testid="stMainBlockContainer"] {
        padding-top: 1.4rem !important;
        padding-bottom: 2.2rem !important;
    }
    .block-container { max-width: 1540px !important; }
    header[data-testid="stHeader"] { background: rgba(255,255,255,.50) !important; }

    /* Role-aware sidebar: a soft blue-to-pink-to-peach ribbon on every page. */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #EAF4FF 0%, #F8F1FF 37%, #FFF2E9 69%, #E9F9FF 100%) !important;
        border-right: 1px solid #D6E3F3 !important;
        box-shadow: 5px 0 24px rgba(87,116,158,.06) !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] { background: transparent !important; }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label { color: #2D3D59 !important; }
    section[data-testid="stSidebar"] div[data-testid="stButton"] button {
        background: linear-gradient(120deg, rgba(255,255,255,.96), rgba(237,246,255,.94)) !important;
        border: 1px solid #D3E2F5 !important;
        border-radius: 14px !important;
        color: #2C4164 !important;
        box-shadow: 0 3px 10px rgba(70,103,153,.06) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {
        background: linear-gradient(120deg, #DCEEFF, #F8E5FF) !important;
        border-color: #AFCBF1 !important;
        transform: translateY(-1px);
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(115deg, #5A92F4, #82B5F5) !important;
        border-color: #659AE9 !important;
        color: #FFFFFF !important;
        box-shadow: 0 7px 16px rgba(75,131,218,.20) !important;
    }

    /* Header and custom cards. */
    .topbar, .chat-heading, .login-hero, .login-card, .panel-header {
        background: linear-gradient(115deg, rgba(235,246,255,.98) 0%, rgba(255,240,252,.96) 54%, rgba(255,242,231,.98) 100%) !important;
        border: 1px solid #D7E4F4 !important;
        border-radius: 20px !important;
        box-shadow: var(--ef-shadow) !important;
    }
    .brand-icon, .login-feature-icon {
        background: linear-gradient(135deg, #6A9FF1, #DDA9F5) !important;
        color: #FFFFFF !important;
    }
    .account-card, .agent-card, .side-note, .mini-card, .trace-item,
    .login-feature, .demo-access-card, .tenant-card, .panel, .metric,
    .profile-card, .request-card, .approval-card, .document-card,
    .submission-card, .project-card, .status-card {
        border: 1px solid var(--ef-border) !important;
        border-radius: 16px !important;
        box-shadow: 0 5px 16px rgba(67,98,145,.055) !important;
    }
    .agent-card:nth-of-type(4n+1), .login-feature:nth-of-type(4n+1),
    .metric:nth-of-type(4n+1), .document-card:nth-of-type(4n+1),
    .submission-card:nth-of-type(4n+1), .project-card:nth-of-type(4n+1) {
        background: linear-gradient(135deg, #EDF6FF, #F8FBFF) !important;
        border-color: #C8DFF9 !important;
    }
    .agent-card:nth-of-type(4n+2), .login-feature:nth-of-type(4n+2),
    .metric:nth-of-type(4n+2), .document-card:nth-of-type(4n+2),
    .submission-card:nth-of-type(4n+2), .project-card:nth-of-type(4n+2) {
        background: linear-gradient(135deg, #FFF0FC, #FFFAFE) !important;
        border-color: #F0D1F2 !important;
    }
    .agent-card:nth-of-type(4n+3), .login-feature:nth-of-type(4n+3),
    .metric:nth-of-type(4n+3), .document-card:nth-of-type(4n+3),
    .submission-card:nth-of-type(4n+3), .project-card:nth-of-type(4n+3) {
        background: linear-gradient(135deg, #FFF1E7, #FFFAF6) !important;
        border-color: #F4D6C4 !important;
    }
    .agent-card:nth-of-type(4n), .login-feature:nth-of-type(4n),
    .metric:nth-of-type(4n), .document-card:nth-of-type(4n),
    .submission-card:nth-of-type(4n), .project-card:nth-of-type(4n) {
        background: linear-gradient(135deg, #E9FAFF, #F8FDFF) !important;
        border-color: #C5E8F5 !important;
    }
    .top-title, .chat-heading-title, h1, h2, h3, h4, h5, h6 {
        color: #263A63 !important;
        letter-spacing: -0.02em;
    }
    p, li, label, div[data-testid="stMarkdownContainer"] { color: inherit; }
    .mini-card { background: linear-gradient(135deg, #EFF7FF, #FFF2FB) !important; }
    .mini-label { color: #53647B !important; font-weight: 800 !important; }
    .mini-value { color: #26334B !important; font-weight: 750 !important; }
    .result-mini-grid { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; gap: 10px !important; }

    /* Consistent buttons with accessible text, including forms and downloads. */
    .stButton > button, div[data-testid="stFormSubmitButton"] button,
    div[data-testid="stDownloadButton"] button, div[data-testid="stPopover"] button {
        border-radius: 12px !important;
        border: 1px solid #BFD6F4 !important;
        background: linear-gradient(120deg, #F1F7FF, #FFFFFF) !important;
        color: #243B5D !important;
        font-weight: 750 !important;
        min-height: 42px !important;
        box-shadow: 0 3px 10px rgba(59,105,166,.07) !important;
        transition: all .16s ease !important;
    }
    .stButton > button:hover, div[data-testid="stFormSubmitButton"] button:hover,
    div[data-testid="stDownloadButton"] button:hover, div[data-testid="stPopover"] button:hover {
        background: linear-gradient(115deg, #DDEEFF, #FBE8FF) !important;
        border-color: #91B9F0 !important;
        color: #1F3454 !important;
        transform: translateY(-1px);
    }
    .stButton > button[kind="primary"],
    div[data-testid="stFormSubmitButton"] button[kind="primary"],
    button[kind="primary"] {
        background: linear-gradient(115deg, #4E8DEB, #79B5F0) !important;
        border-color: #4E8DEB !important;
        color: #FFFFFF !important;
        box-shadow: 0 6px 15px rgba(61,126,218,.22) !important;
    }
    .stButton > button[kind="primary"]:hover,
    div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
    button[kind="primary"]:hover {
        background: linear-gradient(115deg, #3475D4, #5A9FE7) !important;
        border-color: #3475D4 !important;
        color: #FFFFFF !important;
    }
    button[kind="tertiary"] { color: #3269B6 !important; }

    /* Inputs, selectors, file upload and chat composer. */
    div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea,
    div[data-testid="stNumberInput"] input, div[data-testid="stDateInput"] input,
    div[data-baseweb="select"] > div, div[data-testid="stChatInput"] textarea {
        background: linear-gradient(120deg, #FFFFFF, #F5FAFF) !important;
        color: #26334B !important;
        border: 1px solid #C7D9EF !important;
        border-radius: 11px !important;
    }
    div[data-testid="stTextInput"] input:focus, div[data-testid="stTextArea"] textarea:focus,
    div[data-testid="stNumberInput"] input:focus, div[data-testid="stDateInput"] input:focus {
        border-color: #79ADEE !important;
        box-shadow: 0 0 0 2px rgba(132,185,242,.22) !important;
    }
    div[data-testid="stTextInput"] label, div[data-testid="stTextArea"] label,
    div[data-testid="stNumberInput"] label, div[data-testid="stSelectbox"] label,
    div[data-testid="stDateInput"] label, div[data-testid="stFileUploader"] label {
        color: #344864 !important;
        font-weight: 750 !important;
        font-size: 13px !important;
    }
    div[data-testid="stFileUploader"] section {
        background: linear-gradient(120deg, #EDF6FF, #FFF0FB, #FFF2E8) !important;
        border: 1.5px dashed #A8C5EB !important;
        border-radius: 15px !important;
    }
    div[data-testid="stChatInput"] {
        background: linear-gradient(100deg, rgba(233,246,255,.98), rgba(255,240,251,.98), rgba(255,242,232,.98)) !important;
        border: 1px solid #D4E2F2 !important;
        border-radius: 17px !important;
        box-shadow: 0 8px 24px rgba(67,96,138,.12) !important;
        padding: 8px !important;
    }
    .message-bubble { font-size: 14px !important; line-height: 1.68 !important; }
    .user-bubble { background: linear-gradient(120deg, #E4F1FF, #F0F7FF) !important; border-color: #B8D8FA !important; color: #213652 !important; }
    .assistant-bubble { background: linear-gradient(120deg, #FFFFFF, #FFF4FB) !important; border-color: #EAD9F0 !important; color: #2D3342 !important; }

    /* Tabs, expanders, alerts, tables, progress and status surfaces. */
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        background: linear-gradient(90deg, #EDF6FF, #FFF1FC, #FFF2E7) !important;
        border: 1px solid #DFE6F0 !important;
        border-radius: 14px !important;
        padding: 5px !important;
        gap: 5px !important;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        color: #405571 !important; font-weight: 750 !important; border-radius: 10px !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background: #FFFFFF !important; color: #2D69BF !important;
        border: 1px solid #C9DCF5 !important;
        box-shadow: 0 3px 9px rgba(70,102,149,.08) !important;
    }
    div[data-testid="stExpander"] {
        background: rgba(255,255,255,.72) !important;
        border: 1px solid #D8E4F1 !important; border-radius: 14px !important;
        overflow: hidden !important;
    }
    div[data-testid="stExpander"] summary { background: linear-gradient(90deg, #EDF6FF, #FFF6FC) !important; color: #2B4264 !important; }
    div[data-testid="stAlert"] {
        border-radius: 13px !important; border-width: 1px !important;
        box-shadow: 0 4px 12px rgba(55,84,126,.05) !important;
    }
    div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] { color: #29384F !important; }
    div[data-testid="stDataFrame"], div[data-testid="stTable"] {
        border: 1px solid #D2E0F0 !important; border-radius: 13px !important; overflow: hidden !important;
        background: rgba(255,255,255,.85) !important;
    }
    div[data-testid="stProgress"] > div > div { background: linear-gradient(90deg, #79AEF0, #E5B4F0, #FFC9A9) !important; }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #EEF7FF, #FFF3FC) !important;
        border: 1px solid #D7E3F2 !important; border-radius: 15px !important;
        padding: 14px !important; box-shadow: 0 5px 15px rgba(65,97,143,.06) !important;
    }
    a { color: #326BC0 !important; font-weight: 650; }
    code { background: #F0DDF8 !important; color: #283650 !important; border-radius: 6px !important; }
    hr { border-color: #DCE7F3 !important; }
    ::selection { background: #D9EAFE !important; color: #22344E !important; }

    @media (max-width: 900px) { .result-mini-grid { grid-template-columns: repeat(2, minmax(0,1fr)) !important; } }
    @media (max-width: 560px) {
        .result-mini-grid { grid-template-columns: 1fr !important; }
        [data-testid="stMainBlockContainer"] { padding-left: 1rem !important; padding-right: 1rem !important; }
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIGN-IN GATE
# ============================================================

if not st.session_state.authenticated:
    render_login_screen()
    st.stop()

# Reconcile legacy pending requests into the approval queue without altering
# completed/rejected records, and ensure the demo catalog/profile defaults are
# present. Both operations are idempotent and preserve administrator edits.
try:
    from company.catalog_service import ensure_demo_company_defaults
    ensure_demo_company_defaults(st.session_state.company_id)
    reconcile_pending_approval_records(st.session_state.company_id)
except Exception as _startup_reconciliation_error:
    # Surface an actionable diagnostic without preventing employees from
    # accessing the portal when a legacy schema needs manual migration.
    st.session_state.setdefault("startup_reconciliation_warning", str(_startup_reconciliation_error))


# Legacy navigation ids should not reopen hidden employee-only pages.
if current_role() == "employee" and st.session_state.view in {"emails", "policies"}:
    st.session_state.view = "dashboard"

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(
        """
        <div class="brand">
            <span class="brand-icon">*</span>
            <span class="brand-text">
                Enterprise<br>Workflow Platform
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    company = get_company(st.session_state.company_id)
    user = get_user(st.session_state.user_id)
    role = current_role()
    role_label = role.replace("_", " ").title() if role else "Unknown role"
    user_name = (user or {}).get("name", st.session_state.user_id)

    try:
        sidebar_profile = get_user_profile_settings(st.session_state.company_id, st.session_state.user_id)
    except Exception:
        sidebar_profile = {}
    sidebar_photo = sidebar_profile.get("avatar_data")
    if sidebar_photo:
        import base64
        photo_b64 = base64.b64encode(sidebar_photo).decode("ascii")
        photo_mime = html_escape(str(sidebar_profile.get("avatar_mime") or "image/png"))
        avatar_markup = f'<img src="data:{photo_mime};base64,{photo_b64}" alt="Profile photo" style="width:42px;height:42px;border-radius:50%;object-fit:cover;">'
    else:
        avatar_markup = f'<div class="account-avatar">{html_escape(str(user_name)[:1].upper())}</div>'
    st.markdown(
        f"""
        <div class="account-card">
            {avatar_markup}
            <div class="account-info">
                <div class="account-name">{html_escape(str(user_name))}</div>
                <div class="account-role">{html_escape(role_label)}</div>
            </div>
            <div class="account-dot">●</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.view == "chat":
        # Persistent chat history: scoped to the logged-in user and company.
        st.markdown('<div class="side-title">Recent Chats</div>', unsafe_allow_html=True)
        try:
            recent_chats = list_user_conversations(
                st.session_state.company_id, st.session_state.user_id
            )
        except Exception as exc:
            recent_chats = []
            st.caption(f"Chat history unavailable: {exc}")

        for chat in recent_chats[:20]:
            cid = int(chat["conversation_id"])
            title = str(chat.get("title") or "New conversation").strip()
            if len(title) > 34:
                title = title[:31] + "..."
            left, right = st.columns([5, 1])
            with left:
                if st.button(title or "New conversation", key=f"open_chat_{cid}", width="stretch"):
                    restored = get_user_conversation_messages(
                        st.session_state.company_id,
                        st.session_state.user_id,
                        cid,
                    )
                    st.session_state.conversation_id = str(cid)
                    st.session_state.messages = [
                        {
                            "role": m["role"],
                            "content": m["content"],
                            "result": None,
                            "metadata": m.get("metadata") if isinstance(m.get("metadata"), dict) else {},
                            "time": m.get("time", ""),
                        }
                        for m in restored
                        if m.get("role") in ("user", "assistant")
                    ]
                    st.session_state.last_result = None
                    st.session_state.clarification_context = None
                    st.session_state.view = "chat"
                    st.rerun()
            with right:
                if st.button("?", key=f"delete_chat_{cid}", help="Delete this conversation"):
                    if delete_user_conversation(
                        st.session_state.company_id,
                        st.session_state.user_id,
                        cid,
                    ):
                        if str(st.session_state.conversation_id) == str(cid):
                            st.session_state.conversation_id = None
                            st.session_state.messages = []
                            st.session_state.last_result = None
                            st.session_state.clarification_context = None
                        st.rerun()


    st.markdown('<div class="side-title">Navigation</div>', unsafe_allow_html=True)

    if role == "company_admin":
        if st.button("Admin Console", width="stretch", type="primary", key="nav_admin_console"):
            st.session_state.view = "admin"
            st.rerun()
        if st.button("AI Coordinator", width="stretch"):
            st.session_state.view = "chat"
            st.rerun()
        if st.button("Admin Profile", width="stretch"):
            st.session_state.view = "profile"
            st.rerun()
        if st.button("Documents & Exchange", width="stretch"):
            st.session_state.view = "documents"
            st.rerun()
        if st.button("Company Updates", width="stretch"):
            st.session_state.view = "updates"
            st.rerun()
        if st.button("Company Links", width="stretch"):
            st.session_state.view = "links"
            st.rerun()
        if st.button("Notifications", width="stretch"):
            st.session_state.view = "notifications"
            st.rerun()
    else:
        if st.button("Dashboard", width="stretch"):
            st.session_state.view = "dashboard"
            st.rerun()
        if st.button("AI Coordinator", width="stretch"):
            st.session_state.view = "chat"
            st.rerun()
        if st.button("Company Updates", width="stretch"):
            st.session_state.view = "updates"
            st.rerun()
        if st.button("Company Links", width="stretch"):
            st.session_state.view = "links"
            st.rerun()
        if st.button("My Profile", width="stretch"):
            st.session_state.view = "profile"
            st.rerun()
        if st.button("Documents & Submissions", width="stretch"):
            st.session_state.view = "documents"
            st.rerun()
        if st.button("Projects & My Work", width="stretch", key="nav_projects_my_work"):
            st.session_state.view = "portfolio"
            st.rerun()
        if st.button("My Leave", width="stretch"):
            st.session_state.view = "leave"
            st.rerun()
        if st.button("My Requests", width="stretch"):
            st.session_state.view = "requests"
            st.rerun()
        if st.button("My IT Tickets", width="stretch", key="nav_it_tickets"):
            st.session_state.view = "department:IT"
            st.rerun()
        approvals_nav_label = "My Pending Requests" if role == "employee" else "Pending Approvals"
        if st.button(approvals_nav_label, width="stretch", key="nav_approvals_or_my_pending"):
            st.session_state.view = "approvals"
            st.rerun()
        if st.button("Notifications", width="stretch"):
            st.session_state.view = "notifications"
            st.rerun()

    st.markdown('<div class="side-title">Specialist Agents</div>', unsafe_allow_html=True)

    agents = list_agent_runtime_status(st.session_state.company_id, st.session_state.user_id)

    # Only show departments retained in the current project scope.
    visible_agent_names = {
        "hr agent",
        "it support agent",
        "knowledge agent",
    }
    agents = [
        agent for agent in agents
        if str(agent.get("name") or "").strip().casefold()
        in visible_agent_names
    ]

    for agent in agents:
        availability = "ONLINE" if agent.get("status") == "active" else "OFFLINE"
        activity = str(agent.get("last_activity") or "")
        st.markdown(
            f"""
            <div class="agent-card">
                <div class="agent-name">{agent['name']}</div>
                <div class="agent-status">â— {availability} Â· {agent['active_workflows']} active Â· {activity[:16].replace('T', ' ') or 'No activity recorded'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="side-note">
            <b style="color:#5e526c;">Workflow Engine</b><br>
            AI Understanding  ->  Coordination  ->  Tools  ->  Validation  ->  Decision
            <br><br>
            <span style="color:#7b4bd6;">*Â System Online</span>
            <br>
            Requests this session: {st.session_state.request_count}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(" ->   Sign out", width="stretch"):
        st.session_state.authenticated = False
        st.session_state.view = "chat"
        st.session_state.messages = []
        st.session_state.last_result = None
        st.session_state.conversation_id = None
        st.session_state.clarification_context = None
        st.rerun()

    if st.button("Clear conversation", width="stretch"):
        st.session_state.view = "chat"
        st.session_state.messages = []
        st.session_state.last_result = None
        st.session_state.conversation_id = None
        st.session_state.clarification_context = None
        st.rerun()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="topbar">
        <div class="top-title">Enterprise Workflow Platform</div>
        <div class="top-subtitle">
            AI Agent Coordination & Decision Engine  |  Intelligent enterprise automation
        </div>
        <div class="online-pill">WORKSPACE AUTHENTICATED</div>
    </div>
    """,
    unsafe_allow_html=True,
)



# ============================================================
# EMPLOYEE WORK & ACHIEVEMENTS
# ============================================================

if st.session_state.view == "dashboard":
    company_id, user_id = st.session_state.company_id, st.session_state.user_id
    actor = authorize_user(company_id, user_id)
    company = get_company(company_id) or {}
    history = get_user_service_history(company_id, user_id, limit=250)
    notifications = list_my_notifications(company_id, user_id)
    role = str(actor.get("role") or "").lower()
    if role == "employee":
        # Employee home shows the requests they are waiting on, not the
        # approvals they have no permission to decide.
        approvals = list_my_pending_requests(company_id, user_id)
    else:
        approvals = list_pending_approvals(company_id) if role == "company_admin" else list_pending_approvals(company_id, user_id)
        role_for_area = {"it": "it_admin", "hr": "hr_admin", "finance": "finance_admin", "procurement": "procurement_admin", "recruitment": "recruitment_admin"}
        if role != "company_admin":
            approvals = [item for item in approvals if item.get("approver_user_id") == user_id or (not item.get("approver_user_id") and role_for_area.get(str((item.get("metadata") or {}).get("service_area") or (item.get("metadata") or {}).get("department") or "").lower()) == role)]
    statuses = [str(item.get("status") or "").lower() for item in history]
    completed_count = sum(value in {"approved", "completed", "resolved", "closed"} for value in statuses)
    pending_count = sum(value in {"submitted", "pending", "pending_approval", "in_progress", "open"} for value in statuses)
    rejected_count = sum(value == "rejected" for value in statuses)
    st.title(f"Welcome, {actor.get('name') or user_id}")
    st.caption("Your workspace · AI-powered enterprise services")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("My requests", len(history))
    k2.metric("Pending requests", pending_count)
    k3.metric("Awaiting company review" if role == "employee" else "Approvals needing action", len(approvals))
    k4.metric("Completed", completed_count)
    k5.metric("Rejected", rejected_count)
    k6.metric("Unread notifications", sum(not item.get("read_at") for item in notifications))
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        st.subheader("Recent requests")
        for item in history[:6]:
            with st.container(border=True):
                st.markdown(f"**{item.get('service_type') or item.get('service_area') or 'Request'}** Â· {str(item.get('status') or 'unknown').replace('_', ' ').title()}")
                st.caption(f"{item.get('workflow_id') or item.get('record_id') or ''} Â· {item.get('service_area') or ''} Â· {str(item.get('performed_at') or '')[:10]}")
        if not history:
            st.info("Your submitted requests will appear here.")
        st.subheader("Company updates")
        try:
            announcements = list_updates(company_id, user_id=user_id)[:4]
        except Exception as exc:
            announcements = []
            st.warning(f"Company updates are unavailable: {exc}")
        if announcements:
            for item in announcements:
                st.markdown(f"**{item['title']}**  Â·  {str(item.get('priority') or 'normal').title()}")
                st.caption(item.get("description") or "")
        else:
            st.caption("No active announcements for your account.")
    with right:
        st.subheader("My pending requests" if role == "employee" else "Approvals needing action")
        if approvals:
            for item in approvals[:5]:
                if role == "employee":
                    st.markdown(f"**{item.get('request_id') or item.get('workflow_id') or 'Request'}** Â· {item.get('display_title') or item.get('title') or item.get('request_type') or 'Company request'}")
                    st.caption(f"{str(item.get('status') or 'pending_approval').replace('_', ' ').title()} Â· {item.get('service_area') or 'Company'} Â· {str(item.get('updated_at') or item.get('created_at') or '')[:10]}")
                else:
                    st.markdown(f"**Approval #{item['approval_id']}** Â· {item.get('approval_type', '').replace('_', ' ').title()}")
                    st.caption(item.get("reason") or "Waiting for your review")
            if st.button("View my pending requests" if role == "employee" else "Open approval queue", key="dashboard_approvals"):
                st.session_state.view = "approvals"
                st.rerun()
        else:
            st.caption("No requests are waiting for approval." if role == "employee" else "No approvals are waiting for your action.")
        st.subheader("Quick actions")
        if st.button("Create a request", type="primary", key="dashboard_create_request"):
            st.session_state.view = "chat"
            st.rerun()
        quick_leave, quick_it = st.columns(2)
        if quick_leave.button("Ask AI Coordinator", key="dashboard_quick_leave", width="stretch"):
            st.session_state.view = "chat"
            st.rerun()
        if quick_it.button("Open IT tickets", key="dashboard_quick_it", width="stretch"):
            st.session_state.view = "department:IT"
            st.rerun()
        st.subheader("Recent notifications")
        for notification in notifications[:4]:
            st.caption(f"{notification.get('title') or 'Update'} Â· {str(notification.get('created_at') or '')[:10]}")
        st.subheader("Company workspace")
        st.write(f"**Department:** {actor.get('department') or 'Not set'}")
        st.write(f"**Role:** {str(actor.get('role') or 'employee').replace('_', ' ').title()}")
        short_memory = get_short_term_memory(company_id, user_id, st.session_state.conversation_id or "")
        long_memory = search_long_term_memory(company_id, user_id=user_id, limit=5)
        st.caption(f"Short-term memory: {len(short_memory)} item(s) in this conversation")
        st.caption(f"Long-term memory: {len(long_memory)} permitted item(s) available")
        if st.button("Open AI Coordinator", type="primary", key="dashboard_assistant"):
            st.session_state.view = "chat"
            st.rerun()
    st.stop()

if st.session_state.view == "profile":
    render_user_profile_page(
        st.session_state.company_id,
        st.session_state.user_id,
        mode="admin" if current_role() == "company_admin" else "employee",
    )
    st.stop()

if st.session_state.view == "updates":
    company_id, user_id = st.session_state.company_id, st.session_state.user_id
    authorize_user(company_id, user_id)
    st.title("Company Updates")
    updates = list_updates(company_id, user_id=user_id)
    if not updates:
        st.info("There are no active announcements for your company or department.")
    for item in updates:
        with st.container(border=True):
            st.markdown(f"**{item['title']}** Â· {str(item.get('priority') or 'normal').title()}")
            st.caption(f"{item.get('category') or 'Company update'} Â· {str(item.get('published_at') or '')[:10]}")
            st.write(item.get("description") or "")
            if item.get("link_url"):
                st.markdown(f"[Open related resource]({item['link_url']})")
            if item.get("read_at"):
                st.caption("Read")
            elif st.button("Mark as read", key=f"read_update_{item['update_id']}"):
                mark_update_read(company_id, user_id, int(item["update_id"]))
                st.rerun()
    st.stop()

if st.session_state.view == "links":
    company_id, user_id = st.session_state.company_id, st.session_state.user_id
    authorize_user(company_id, user_id)
    st.title("Company Links")
    resources = list_resources(company_id, user_id)
    if not resources:
        st.info("Your company has not shared any links with your account yet.")
    for resource in resources:
        with st.container(border=True):
            st.markdown(f"**{resource['title']}** Â· {resource.get('category') or 'Company resource'}")
            st.write(resource.get("description") or "")
            st.link_button("Open link", resource["url"])
    st.stop()

if st.session_state.view in {"emails", "policies"}:
    st.session_state.view = "chat"
    st.rerun()

if st.session_state.view == "policies":
    company_id, user_id = st.session_state.company_id, st.session_state.user_id
    authorize_user(company_id, user_id)
    st.title("Company Policies")
    db_policies = get_active_policies(company_id)
    context = get_company_context(company_id) or {}
    context_policies = context.get("policies", {}) if isinstance(context, dict) else {}
    actor = authorize_user(company_id, user_id)
    department = str(actor.get("department") or "").casefold()
    role = str(actor.get("role") or "").casefold()
    db_policies = [item for item in db_policies if not str(item.get("department") or "").strip() or str(item.get("department") or "").casefold() == department or role in {"company_admin", "hr_admin"}]
    if db_policies:
        for policy in db_policies:
            with st.container(border=True):
                st.markdown(f"**{policy['name']}** Â· {policy.get('department') or 'Company-wide'}")
                st.write(policy.get("description") or "No description provided.")
                rules = get_policy_rules(company_id, policy_key=policy.get("policy_key"))
                for rule in rules:
                    st.caption(f"{rule.get('rule_name')}: {rule.get('description') or rule.get('actions') or ''}")
    if context_policies:
        st.subheader("Configured company policy values")
        for key, value in context_policies.items():
            if key == "finance_available_budget_inr":
                continue
            with st.container(border=True):
                st.markdown(f"**{key.replace('_', ' ').title()}**")
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        st.write(f"{str(subkey).replace('_', ' ').title()}: {subvalue}")
                elif isinstance(value, list):
                    for item in value:
                        st.markdown(f"- {item}")
                else:
                    st.write(value)
    if not db_policies and not context_policies:
        st.info("Your company has not published policies yet.")
    st.subheader("Start a workflow")
    action_leave, action_purchase = st.columns(2)
    if action_leave.button("Ask AI Coordinator", type="primary", width="stretch"):
        st.session_state.view = "chat"
        st.rerun()
    if action_purchase.button("Request a laptop or purchase", width="stretch"):
        st.session_state.view = "chat"
        st.session_state.messages = []
        st.rerun()
    st.stop()

if st.session_state.view == "emails":
    company_id, user_id = st.session_state.company_id, st.session_state.user_id
    authorize_user(company_id, user_id)

    st.title("Company Email Center")
    st.caption("Internal company messages stored in this company's system.")
    st.info(
        "This page shows internal company emails. External mailbox "
        "delivery and incoming external emails are not confirmed as configured."
    )

    history_tab, sent_tab, received_tab, drafts_tab = st.tabs(
        ["Email History", "Sent Emails", "Received Emails", "Drafts"]
    )

    def render_email_list(folder, key_prefix):
        search = st.text_input(
            "Search by subject, message, or sender",
            key=f"{key_prefix}_search",
        )
        date_filter = st.text_input(
            "Filter date (YYYY-MM-DD, optional)",
            key=f"{key_prefix}_date",
            placeholder="Example: 2026-10-05",
        ).strip()

        if folder == "history":
            outgoing = search_emails(company_id, user_id, search, "sent")
            incoming = search_emails(company_id, user_id, search, "inbox")
            messages = []
            for item in outgoing:
                entry = dict(item)
                entry["_folder"] = "sent"
                messages.append(entry)
            for item in incoming:
                entry = dict(item)
                entry["_folder"] = "inbox"
                messages.append(entry)
            messages.sort(
                key=lambda item: str(
                    item.get("sent_at") or item.get("created_at") or ""
                ),
                reverse=True,
            )
        else:
            messages = search_emails(company_id, user_id, search, folder)
            for item in messages:
                item["_folder"] = folder

        if date_filter:
            if len(date_filter) != 10 or date_filter[4:5] != "-" or date_filter[7:8] != "-":
                st.warning("Enter the date in YYYY-MM-DD format.")
                return
            messages = [
                item for item in messages
                if str(item.get("sent_at") or item.get("created_at") or "")[:10]
                == date_filter
            ]

        st.caption(f"{len(messages)} message(s)")
        if not messages:
            st.info("No emails match these filters.")
            return

        for item in messages:
            is_received = item.get("_folder") == "inbox"
            sender = item.get("sender", {}) or {}
            recipients = item.get("recipients", []) or []
            recipient_names = ", ".join(
                row.get("name", row.get("email", "Company employee"))
                for row in recipients
            )
            timestamp = item.get("sent_at") or item.get("created_at") or "Time unavailable"

            with st.container(border=True):
                if folder == "drafts":
                    st.markdown(
                        f"**{item.get('subject') or '(No subject)'}** ? Draft #{item['email_id']}"
                    )
                else:
                    st.markdown(f"**{item.get('subject') or '(No subject)'}**")
                if is_received:
                    st.write(f"From: {sender.get('name') or sender.get('email') or 'Company employee'}")
                    st.write(f"To: {user_id}")
                else:
                    st.write(f"From: {sender.get('name') or user_id}")
                    st.write(f"To: {recipient_names or 'Recipient unavailable'}")
                if folder == "drafts":
                    status_text = "Draft - not sent"
                elif is_received:
                    status_text = (
                        "Received / read"
                        if item.get("read_at")
                        else "Received / unread"
                    )
                else:
                    status_text = "Sent"
                st.caption(f"Date/time: {timestamp} | {status_text}")

                with st.expander("Open full message"):
                    st.write(item.get("body") or "Message body unavailable.")

                if folder == "drafts" and item.get("status") == "draft":
                    if st.button(
                        "Send this draft",
                        key=f"{key_prefix}_send_{item['email_id']}",
                        type="primary",
                    ):
                        result = send_email(
                            company_id, user_id, int(item["email_id"])
                        )
                        if result.get("status") == "success":
                            st.success(result.get("message", "Email sent."))
                            st.rerun()
                        else:
                            st.error(
                                result.get("message", "Draft could not be sent.")
                            )

                if is_received and not item.get("read_at"):
                    if st.button(
                        "Mark as read",
                        key=f"{key_prefix}_read_{item['email_id']}",
                    ):
                        if mark_email_read(
                            company_id, user_id, int(item["email_id"])
                        ):
                            st.success("Email marked as read.")
                        st.rerun()

    with history_tab:
        render_email_list("history", "email_history")

    with sent_tab:
        render_email_list("sent", "email_sent")

    with received_tab:
        render_email_list("inbox", "email_received")

    with drafts_tab:
        render_email_list("drafts", "email_drafts")

    st.stop()

if st.session_state.view == "documents":
    company_id, user_id = st.session_state.company_id, st.session_state.user_id
    actor = authorize_user(company_id, user_id)
    st.title("Documents & Submissions")
    st.caption("Read company documents, send a document to an authorized administrator, and receive documents shared specifically with you.")
    knowledge_tab, exchange_tab = st.tabs(["Company Knowledge", "My Document Exchange"])

    with knowledge_tab:
        documents = list_accessible_documents(company_id, user_id)
        if not documents:
            st.info("No company knowledge documents are currently available to your account.")
        for document in documents:
            with st.container(border=True):
                st.markdown(f"**{document['title']}**")
                st.caption(f"{document.get('category') or 'Company document'} · {document.get('department') or 'Company-wide'} · Updated {str(document.get('updated_at') or '')[:10]}")
                if st.button("Open / read details", key=f"open_knowledge_doc_{document['document_id']}"):
                    result = read_accessible_document(company_id, user_id, int(document["document_id"]))
                    if result.get("status") == "success":
                        st.session_state[f"knowledge_document_open_{document['document_id']}"] = result
                    else:
                        st.error(result.get("message", "Document could not be retrieved."))
                loaded = st.session_state.get(f"knowledge_document_open_{document['document_id']}")
                if loaded:
                    with st.expander("Document content", expanded=True):
                        data = loaded.get("data", b"")
                        render_document_preview(st, file_name=loaded.get("filename", document['title']), data=data, content_type=loaded.get("content_type", ""), key=f"knowledge_{document['document_id']}")
                        st.download_button("Download document", data=data, file_name=loaded.get("filename", document['title']), key=f"download_knowledge_doc_{document['document_id']}")

    with exchange_tab:
        st.subheader("Send documents to HR / company administration")
        admins = [row for row in list_company_users(company_id) if str(row.get("role") or "").casefold() in {"company_admin", "hr_admin"} and str(row.get("status") or "").casefold() == "active"]
        if not admins:
            st.warning("No active HR/company administrator account is configured for document submissions.")
        else:
            admin_options = {f"{row.get('name') or row['user_id']} · {row.get('role', '').replace('_', ' ').title()} · {row.get('email') or row['user_id']}": row["user_id"] for row in admins}
            with st.form("employee_document_submission_form", clear_on_submit=True):
                recipient_label = st.selectbox("Send to administrator", list(admin_options.keys()))
                document_title = st.text_input("Document title", placeholder="Example: Internship project report")
                purpose = st.text_input("Purpose / category", placeholder="Example: Project submission, employment letter, supporting document")
                message = st.text_area("Message to administrator (optional)", height=80)
                uploaded_document = st.file_uploader("Choose document (PDF, Office file, image, text, or ZIP; max 10 MB)", type=["pdf", "txt", "md", "csv", "json", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "png", "jpg", "jpeg", "webp", "zip"])
                submitted_document = st.form_submit_button("Send document to administrator", type="primary", use_container_width=True)
            if submitted_document:
                if uploaded_document is None:
                    st.error("Choose a document before submitting.")
                else:
                    result = submit_employee_document(
                        company_id, user_id, admin_options[recipient_label],
                        title=document_title, file_name=uploaded_document.name,
                        file_data=uploaded_document.getvalue(), purpose=purpose,
                        message=message, content_type=uploaded_document.type or "",
                    )
                    if result.get("status") == "success":
                        st.success(result.get("message", "Document submitted."))
                        st.rerun()
                    else:
                        st.error(result.get("message", "Document could not be submitted."))

        st.divider()
        st.subheader("Documents sent and received")
        exchanged = list_user_documents(company_id, user_id)
        if not exchanged:
            st.info("No documents have been sent or shared with you yet.")
        for item in exchanged:
            is_sender = item.get("sender_user_id") == user_id
            direction = "Sent by you" if is_sender else "Received from administrator"
            recipient_or_sender = (item.get("recipient_name") or "Administrator") if is_sender else (item.get("sender_name") or "Administrator")
            with st.container(border=True):
                st.markdown(f"**{item.get('title') or item.get('file_name')}**")
                st.caption(f"{direction} · {recipient_or_sender} · {str(item.get('created_at') or '')[:19]} · Status: {str(item.get('status') or 'submitted').replace('_', ' ').title()}")
                if item.get("purpose"):
                    st.write(item["purpose"])
                if item.get("message"):
                    st.write(item["message"])
                document_id = int(item["document_id"])
                file_record = get_employee_document(company_id, user_id, document_id)
                if file_record:
                    col_open, col_download = st.columns(2)
                    with col_open:
                        with st.expander("Open / read document"):
                            render_document_preview(st, file_name=file_record["file_name"], data=file_record["file_data"], content_type=file_record.get("content_type", ""), key=f"employee_doc_{document_id}")
                    with col_download:
                        st.download_button("Download", data=file_record["file_data"], file_name=file_record["file_name"], mime=file_record.get("content_type") or "application/octet-stream", key=f"download_employee_doc_{document_id}", use_container_width=True)
                    if not is_sender and item.get("status") not in {"read", "reviewed", "archived"}:
                        if st.button("Mark as read", key=f"mark_employee_doc_read_{document_id}"):
                            mark_result = mark_employee_document_read(company_id, user_id, document_id)
                            if mark_result.get("status") == "success":
                                st.success(mark_result.get("message", "Marked as read."))
                            st.rerun()
                if item.get("admin_note"):
                    st.info(f"Administrator note: {item['admin_note']}")
    st.stop()

if st.session_state.view == "knowledge":
    st.session_state.view = "home"
    st.rerun()

if st.session_state.view == "requests":
    st.title("My Requests")
    records = get_user_service_history(st.session_state.company_id, st.session_state.user_id, limit=250)
    search = st.text_input("Search requests", placeholder="Request type, department, request ID", key="my_requests_search")
    statuses = ["All"] + sorted({str(row.get("status") or "Unknown") for row in records})
    selected_status = st.selectbox("Status", statuses)
    filtered = []
    for row in records:
        searchable = " ".join(str(row.get(key) or "") for key in ("request_id", "workflow_id", "service_type", "service_area", "description", "status", "decision"))
        if search.casefold() not in searchable.casefold():
            continue
        if selected_status != "All" and str(row.get("status") or "Unknown") != selected_status:
            continue
        filtered.append(row)
    if filtered:
        for row in filtered:
            request_id = row.get("request_id") or f"ACT-{row.get('record_id')}"
            with st.container(border=True):
                st.markdown(f"**{row.get('service_type') or 'Request'}** Â· {str(row.get('status') or '').replace('_', ' ').title()}")
                st.caption(f"{request_id} Â· {row.get('service_area') or ''} Â· {str(row.get('performed_at') or '')[:19].replace('T', ' ')}")
                if row.get("description"):
                    st.write(row["description"])
                if row.get("decision"):
                    st.caption(f"Decision: {row['decision']}")
                with st.expander("Workflow details"):
                    detail = get_my_workflow_details(st.session_state.company_id, st.session_state.user_id, str(row.get("workflow_id") or "")) if row.get("workflow_id") else {}
                    if detail:
                        st.caption(f"Workflow {detail.get('workflow_id')} Â· {str(detail.get('status') or '').replace('_', ' ').title()}")
                        if detail.get("assigned_agents"):
                            st.write("Agents: " + ", ".join(detail["assigned_agents"]))
                        if detail.get("selected_tools"):
                            st.write("Services: " + ", ".join(str(value) for value in detail["selected_tools"]))
                        for execution in detail.get("executions", []):
                            st.caption(f"{execution.get('stage') or 'Step'} Â· {execution.get('tool_key') or execution.get('agent_key') or ''} Â· {str(execution.get('status') or '').title()}")
                        for approval in detail.get("approvals", []):
                            st.caption(f"Approval #{approval.get('approval_id')} Â· {str(approval.get('status') or '').title()} Â· {approval.get('reason') or ''}")
                            if approval.get("status") == "needs_clarification":
                                with st.form(f"clarification_response_{approval['approval_id']}"):
                                    response = st.text_area("Reply to approver", key=f"clarification_text_{approval['approval_id']}")
                                    submit_response = st.form_submit_button("Send clarification")
                                if submit_response:
                                    result = respond_to_approval_clarification(st.session_state.company_id, int(approval["approval_id"]), st.session_state.user_id, response)
                                    if result.get("status") == "success":
                                        st.success(result["message"])
                                        st.rerun()
                                    st.error(result.get("message", "Response could not be sent."))
                    else:
                        st.caption("Detailed workflow tracking is unavailable for this older activity record.")
    else:
        st.info("No matching request history was found for your account.")
    st.stop()

if st.session_state.view.startswith("department:"):
    area = st.session_state.view.split(":", 1)[1]
    st.title({"IT": "My IT Tickets"}.get(area, f"My {area} Requests"))
    records = list_my_department_requests(st.session_state.company_id, st.session_state.user_id, area, limit=250)
    query = st.text_input("Search", placeholder="Request ID or title")
    status_values = ["All"] + sorted({str(item.get("status") or "unknown") for item in records})
    selected = st.selectbox("Status", status_values, key=f"{area}_status")
    matching = [item for item in records if query.casefold() in f"{item.get('request_id','')} {item.get('title','')} {item.get('request_type','')}".casefold() and (selected == "All" or item.get("status") == selected)]
    if not matching:
        st.info(f"No {area.lower()} requests match these filters.")
    for item in matching:
        with st.container(border=True):
            st.markdown(f"**{item.get('title') or item.get('request_type')}**  Â·  `{item.get('request_id')}`")
            st.caption(f"{str(item.get('status') or '').replace('_', ' ').title()} Â· Submitted {str(item.get('created_at') or '')[:19].replace('T', ' ')}")
            if item.get("amount") is not None:
                st.write(f"Amount: {item.get('currency', '')} {float(item['amount']):,.2f}")
            if item.get("description"):
                st.write(item["description"])
            if item.get("decision_reason"):
                st.caption(f"Decision note: {item['decision_reason']}")
            with st.expander("Workflow details"):
                workflow = get_my_workflow_details(st.session_state.company_id, st.session_state.user_id, str(item.get("workflow_id") or "")) if item.get("workflow_id") else {}
                if workflow:
                    st.caption(f"Workflow {workflow.get('workflow_id')} Â· {str(workflow.get('status') or '').replace('_', ' ').title()}")
                    st.write(f"Request: {workflow.get('request_text') or item.get('description') or item.get('title')}")
                    if workflow.get("assigned_agents"):
                        st.write("Agents: " + ", ".join(workflow["assigned_agents"]))
                    if workflow.get("selected_tools"):
                        st.write("Tools: " + ", ".join(str(value) for value in workflow["selected_tools"]))
                    if workflow.get("executions"):
                        st.markdown("**Timeline**")
                        for execution in workflow["executions"]:
                            label = execution.get("tool_key") or execution.get("stage") or "Workflow step"
                            st.caption(f"{str(execution.get('created_at') or '')[:19].replace('T', ' ')} Â· {label} Â· {str(execution.get('status') or '').title()}")
                    for approval in workflow.get("approvals", []):
                        st.caption(f"Approval #{approval.get('approval_id')} Â· {str(approval.get('status') or '').title()} Â· {approval.get('reason') or ''}")
                else:
                    st.caption("This request predates detailed workflow tracking.")
    st.stop()

if st.session_state.view == "notifications":
    st.title("Notifications")
    notifications = list_my_notifications(st.session_state.company_id, st.session_state.user_id)
    if notifications:
        for item in notifications[:100]:
            with st.container(border=True):
                st.markdown(f"**{item.get('title') or 'Update'}**")
                st.write(item.get("body") or "")
                st.caption(str(item.get("created_at") or "")[:19].replace("T", " "))
                resource_type = str(item.get("resource_type") or "").casefold()
                resource_id = str(item.get("resource_id") or "")
                if resource_id and st.button("Open related record", key=f"open_notification_{item['notification_id']}"):
                    if not item.get("read_at"):
                        mark_notification_read(st.session_state.company_id, st.session_state.user_id, int(item["notification_id"]))
                    if resource_type == "approval":
                        st.session_state.focus_approval_id = resource_id
                        st.session_state.view = "approvals"
                    elif resource_type == "leave_request":
                        st.session_state.leave_focus_id = resource_id
                        st.session_state.view = "leave"
                    else:
                        st.session_state.my_requests_search = resource_id
                        st.session_state.view = "requests"
                    st.rerun()
                if not item.get("read_at") and st.button("Mark as read", key=f"mark_notification_{item['notification_id']}"):
                    mark_notification_read(st.session_state.company_id, st.session_state.user_id, int(item["notification_id"]))
                    st.rerun()
    else:
        st.info("You have no notifications yet.")
    st.stop()

if st.session_state.view == "leave":
    company_id = st.session_state.company_id
    user_id = st.session_state.user_id
    summary = get_leave_summary(company_id, user_id)
    st.title("My Leave")
    if summary.get("status") != "success":
        st.error(summary.get("message", "Your employee leave profile is unavailable."))
        st.stop()
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Available balance", f"{summary['leave_balance']:g} days")
    metric_col2.metric("Annual entitlement", f"{summary['leave_entitlement']:g} days")
    metric_col3.metric("Leave types", len(summary.get("leave_types", [])))
   
    st.subheader("Leave history")
    requests = summary.get("requests", [])
    leave_focus_id = str(st.session_state.get("leave_focus_id") or "")
    if requests:
        for leave_request in requests:
            with st.container(border=True):
                prefix = "**" if leave_request["leave_request_id"] == leave_focus_id else ""
                st.markdown(f"{prefix}{leave_request['leave_request_id']} Â· {leave_request['leave_type']}{'**' if prefix else ''}")
                st.caption(f"{leave_request['start_date']} to {leave_request['end_date']} Â· {leave_request['requested_days']:g} day(s) Â· {str(leave_request['status']).replace('_', ' ').title()}")
                if leave_request.get("decision_reason"):
                    st.write(f"Decision note: {leave_request['decision_reason']}")
                if leave_request.get("status") == "pending_approval":
                    if st.button("Cancel request", key=f"cancel_leave_{leave_request['leave_request_id']}"):
                        cancelled = cancel_leave_request(company_id, user_id, leave_request["leave_request_id"])
                        if cancelled.get("status") == "success":
                            st.success(cancelled["message"])
                            st.rerun()
                        else:
                            st.error(cancelled.get("message", "The request could not be cancelled."))
    else:
        st.info("You have no leave requests yet.")
    st.subheader("Notifications")
    notifications = list_my_notifications(company_id, user_id)
    if notifications:
        for notification in notifications[:10]:
            st.markdown(f"**{notification['title']}**  \n{notification['body']}")
    else:
        st.caption("No notifications yet.")
    st.stop()

if st.session_state.view == "approvals":
    role = str(current_role() or "employee").casefold()
    is_employee = role == "employee"
    if is_employee:
        st.title("My Requests Awaiting Approval")
        st.caption("These are your submitted requests that are waiting for company review or clarification. You can track them here; only authorized approvers can make decisions.")
        pending_items = list_my_pending_requests(st.session_state.company_id, st.session_state.user_id)
        if not pending_items:
            st.success("You have no requests currently waiting for approval or clarification.")
        for item in pending_items:
            request_id = str(item.get("request_id") or item.get("workflow_id") or "Request")
            title = str(item.get("display_title") or item.get("title") or item.get("request_type") or "Company request")
            status = str(item.get("status") or "pending_approval").casefold()
            status_label = status.replace("_", " ").title()
            with st.container(border=True):
                st.markdown(f"### {title}")
                st.caption(f"Request ID: {request_id} · Department: {item.get('service_area') or 'Company'} · Status: {status_label}")
                if item.get("description"):
                    st.write(str(item.get("description"))[:1600])
                if item.get("start_date") or item.get("end_date"):
                    st.write(f"Dates: {item.get('start_date') or '—'} to {item.get('end_date') or '—'} · Days: {item.get('requested_days') or '—'}")
                if item.get("approval_id"):
                    st.caption(f"Approval reference: #{item.get('approval_id')}")
                if status == "needs_clarification":
                    st.warning(item.get("decision_reason") or "The approver needs more information. Open AI Coordinator or My Requests to continue the clarification.")
                else:
                    st.info("This request is saved and waiting for an authorized company approver. Submission does not mean it has already been approved or completed.")
                st.caption(f"Last updated: {str(item.get('updated_at') or item.get('created_at') or '')[:19]}")
    else:
        st.title("Pending Approvals")
        # Company admins see all pending approvals. Department admins see only
        # their own assignments and unassigned approvals for their department.
        reconcile_pending_approval_records(st.session_state.company_id)
        approvals = list_pending_approvals(st.session_state.company_id) if role == "company_admin" else list_pending_approvals(st.session_state.company_id, st.session_state.user_id)
        area_roles = {"it": "it_admin", "hr": "hr_admin", "finance": "finance_admin", "procurement": "procurement_admin", "recruitment": "recruitment_admin"}
        if role != "company_admin":
            approvals = [
                item for item in approvals
                if item.get("approver_user_id") == st.session_state.user_id
                or (not item.get("approver_user_id") and area_roles.get(str((item.get("metadata") or {}).get("service_area") or (item.get("metadata") or {}).get("department") or "").casefold()) == role)
            ]
        focus_approval_id = str(st.session_state.get("focus_approval_id") or "")
        if focus_approval_id:
            approvals = [item for item in approvals if str(item.get("approval_id")) == focus_approval_id]
        if not approvals:
            st.success("There are no pending approvals assigned to you.")
        for approval in approvals:
            metadata = approval.get("metadata", {}) if isinstance(approval.get("metadata"), dict) else {}
            with st.container(border=True):
                st.markdown(f"### Approval #{approval['approval_id']} · {approval.get('approval_type', '').replace('_', ' ').title()}")
                requested_by = str(approval.get("requested_by") or "")
                if requested_by:
                    requester = get_user(requested_by) or {}
                    st.caption(f"Requested by: {requester.get('name') or requested_by} · {requester.get('email') or ''}")
                if metadata.get("tool") == "leave_management":
                    purpose = str(metadata.get("employee_purpose") or approval.get("reason") or "").strip()
                    st.markdown(f"**Employee leave purpose:** {purpose or 'Purpose not recorded'}")
                    st.caption(f"Leave request {metadata.get('request_id') or ''} · {metadata.get('start_date', '')} to {metadata.get('end_date', '')} · {metadata.get('requested_days', '')} day(s)")
                else:
                    st.write(approval.get("reason") or "Approval requested by company policy.")
                if metadata.get("request_id") and metadata.get("tool") != "leave_management":
                    st.markdown(f"**Request:** {metadata.get('title') or 'Department request'}")
                    st.caption(f"Request ID: {metadata.get('request_id')} | Department: {metadata.get('service_area') or metadata.get('department') or 'General'}")
                if metadata.get("amount_inr"):
                    st.caption(f"Amount: ₹{metadata.get('amount_inr')}")
                decision_reason = st.text_input("Decision note", key=f"approval_reason_{approval['approval_id']}")
                approve_col, reject_col = st.columns(2)
                if approve_col.button("Approve request", key=f"approve_{approval['approval_id']}", type="primary"):
                    result = approve_request(st.session_state.company_id, approval["approval_id"], st.session_state.user_id, decision_reason)
                    if result.get("status") == "success":
                        st.success(result.get("message") or "Approval recorded.")
                        st.rerun()
                    st.error(result.get("message") or "Approval could not be recorded.")
                if reject_col.button("Reject request", key=f"reject_{approval['approval_id']}"):
                    if not decision_reason.strip():
                        st.error("Add a reason before rejecting this request.")
                    else:
                        result = reject_request(st.session_state.company_id, approval["approval_id"], st.session_state.user_id, decision_reason)
                        if result.get("status") == "success":
                            st.success(result.get("message") or "Rejection recorded.")
                            st.rerun()
                        st.error(result.get("message") or "Rejection could not be recorded.")
                clarification = st.text_input("Clarification needed from requester", key=f"approval_clarification_{approval['approval_id']}")
                if st.button("Request clarification", key=f"request_clarification_{approval['approval_id']}"):
                    try:
                        from company.approval_service import request_approval_clarification
                        result = request_approval_clarification(st.session_state.company_id, int(approval["approval_id"]), st.session_state.user_id, clarification)
                        if result.get("status") == "success":
                            st.success(result["message"])
                            st.rerun()
                        st.error(result.get("message", "Clarification could not be requested."))
                    except (ValueError, PermissionError) as exc:
                        st.error(str(exc))
    st.stop()

if st.session_state.view == "portfolio":

    current_user = get_user(
        st.session_state.user_id
    )

    employee_id = str(
        (current_user or {}).get("employee_id")
        or ""
    ).strip()

    employee_name = str(
        (current_user or {}).get("name")
        or st.session_state.user_id
    )

    if not employee_id:

        st.error(
            "Employee ID is not available for this account."
        )

        st.stop()

    st.markdown(
        """
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">
                    [PROFILE] My Work & Achievements
                </div>
                <div class="panel-subtitle">
                    Create and manage projects, upload a complete folder or multiple files,
                    submit work directly to Admin for review, and track feedback.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        f"Employee: {employee_name}  |  Employee ID: {employee_id}"
    )

    (
        projects_tab,
        achievements_tab,
        participation_tab,
        performance_tab,
    ) = st.tabs(
        [
            "Projects & Milestones",
            "Achievements",
            "Participations",
            "Performance",
        ]
    )

    # ========================================================
    # PROJECTS + MILESTONES
    # ========================================================

    with projects_tab:

        st.markdown("### Add Project")

        with st.form("employee_project_form"):

            project_name = st.text_input(
                "Project Name",
                placeholder="Example: Enterprise Workflow Platform",
            )

            project_description = st.text_area(
                "Description",
                placeholder="Describe your project.",
                height=100,
            )

            project_role = st.text_input(
                "Role in Project",
                placeholder="Example: AI/ML Developer",
            )

            project_start = st.text_input(
                "Start Date",
                placeholder="YYYY-MM-DD",
            )

            project_end = st.text_input(
                "End Date",
                placeholder="YYYY-MM-DD",
            )

            project_status = st.selectbox(
                "Project Status",
                [
                    "in_progress",
                    "completed",
                    "on_hold",
                ],
            )

            submitted = st.form_submit_button(
                "Save Project",
                type="primary",
            )

        if submitted:

            result = create_project(
                company_id=st.session_state.company_id,
                employee_id=employee_id,
                project_name=project_name,
                description=project_description,
                role_in_project=project_role,
                start_date=project_start,
                end_date=project_end,
                status=project_status,
            )

            if result.get("status") == "success":
                st.success(
                    result.get(
                        "message",
                        "Project saved successfully.",
                    )
                )
                st.rerun()
            else:
                st.error(
                    result.get(
                        "message",
                        "Could not save project.",
                    )
                )

        st.markdown("### My Projects")

        projects = list_projects(
            st.session_state.company_id,
            employee_id,
        )

        if not projects:
            st.info(
                "No projects have been added yet."
            )
        else:

            project_options = {
                f"{item['project_name']} (ID {item['project_id']})":
                    item["project_id"]
                for item in projects
            }

            selected_label = st.selectbox(
                "Select project",
                list(project_options.keys()),
                key="selected_employee_project",
            )

            selected_project_id = project_options[
                selected_label
            ]

            selected_project = next(
                item
                for item in projects
                if item["project_id"] == selected_project_id
            )

            st.write(
                f"**{selected_project['project_name']}**"
            )

            st.caption(
                selected_project.get(
                    "description",
                    "",
                )
            )

            st.write(
                f"**Role:** "
                f"{selected_project.get('role_in_project', '')}"
            )

            st.write(
                f"**Status:** "
                f"{selected_project.get('status', '')}"
            )

            # =================================================
            # EDIT PROJECT
            # =================================================

            with st.expander("?? Edit Project"):

                with st.form(
                    f"edit_project_form_{selected_project_id}"
                ):

                    edit_project_name = st.text_input(
                        "Project Name",
                        value=selected_project.get(
                            "project_name",
                            "",
                        ),
                    )

                    edit_project_description = st.text_area(
                        "Description",
                        value=selected_project.get(
                            "description",
                            "",
                        ),
                        height=120,
                    )

                    edit_project_role = st.text_input(
                        "Role in Project",
                        value=selected_project.get(
                            "role_in_project",
                            "",
                        ),
                    )

                    edit_col1, edit_col2 = st.columns(2)

                    with edit_col1:
                        edit_project_start = st.text_input(
                            "Start Date",
                            value=selected_project.get(
                                "start_date",
                                "",
                            ),
                            placeholder="YYYY-MM-DD",
                        )

                    with edit_col2:
                        edit_project_end = st.text_input(
                            "End Date",
                            value=selected_project.get(
                                "end_date",
                                "",
                            ),
                            placeholder="YYYY-MM-DD",
                        )

                    current_status = (
                        selected_project.get(
                            "status",
                            "in_progress",
                        )
                        or "in_progress"
                    ).lower()

                    status_options = [
                        "in_progress",
                        "completed",
                        "on_hold",
                        "cancelled",
                    ]

                    if current_status not in status_options:
                        current_status = "in_progress"

                    edit_project_status = st.selectbox(
                        "Project Status",
                        status_options,
                        index=status_options.index(
                            current_status
                        ),
                    )

                    edit_project_submitted = (
                        st.form_submit_button(
                            "?? Update Project",
                            type="primary",
                        )
                    )

                if edit_project_submitted:

                    result = update_project(
                        company_id=st.session_state.company_id,
                        employee_id=employee_id,
                        project_id=selected_project_id,
                        project_name=edit_project_name,
                        description=edit_project_description,
                        role_in_project=edit_project_role,
                        start_date=edit_project_start,
                        end_date=edit_project_end,
                        status=edit_project_status,
                    )

                    if result.get("status") == "success":

                        st.success(
                            result.get(
                                "message",
                                "Project updated successfully.",
                            )
                        )

                        st.rerun()

                    else:

                        st.error(
                            result.get(
                                "message",
                                "Could not update project.",
                            )
                        )

            # =================================================
            # PROJECT FILES
            # =================================================

            st.markdown("### Submit Project Folder / Files to Admin")
            st.caption("Select a complete project folder to retain its folder structure, or choose multiple files. Files are saved to your selected project; pressing Submit Project sends the project record and files to the administrator for review.")
            folder_uploads = st.file_uploader(
                "Choose a project folder",
                type=["pdf", "ppt", "pptx", "doc", "docx", "txt", "csv", "xlsx", "zip", "png", "jpg", "jpeg", "py", "json", "md", "html", "css", "js", "ts", "java", "c", "cpp", "sql", "yaml", "yml", "toml", "ipynb"],
                accept_multiple_files="directory",
                key=f"project_folder_upload_{selected_project_id}",
                help="Folder upload is supported by this Streamlit version; relative paths are preserved inside the project submission.",
            ) or []
            separate_uploads = st.file_uploader(
                "Or choose multiple project files",
                type=["pdf", "ppt", "pptx", "doc", "docx", "txt", "csv", "xlsx", "zip", "png", "jpg", "jpeg", "py", "json", "md", "html", "css", "js", "ts", "java", "c", "cpp", "sql", "yaml", "yml", "toml", "ipynb"],
                accept_multiple_files=True,
                key=f"project_multi_upload_{selected_project_id}",
            ) or []
            submission_note = st.text_area(
                "Message to administrator (optional)",
                placeholder="What should the reviewer know about this project?",
                key=f"project_submission_note_{selected_project_id}",
                height=80,
            )
            if st.button("Submit Project to Admin", type="primary", key=f"submit_project_admin_{selected_project_id}", use_container_width=True):
                uploads = list(folder_uploads) + list(separate_uploads)
                if len(uploads) > 200:
                    st.error("Please submit no more than 200 files at a time.")
                elif sum(int(getattr(item, "size", 0) or 0) for item in uploads) > 200 * 1024 * 1024:
                    st.error("The combined project upload must be 200 MB or smaller per submission.")
                else:
                    saved_ids = []
                    upload_error = ""
                    for uploaded_item in uploads:
                        save_result = save_project_file(
                            company_id=st.session_state.company_id,
                            employee_id=employee_id,
                            project_id=selected_project_id,
                            file_name=uploaded_item.name,
                            file_data=uploaded_item.getvalue(),
                        )
                        if save_result.get("status") == "success":
                            saved_ids.append(int(save_result["file_id"]))
                        else:
                            upload_error = save_result.get("message", "A project file could not be saved.")
                            break
                    if upload_error:
                        # Remove only files inserted by this submission attempt.
                        for saved_file_id in saved_ids:
                            delete_project_file(st.session_state.company_id, employee_id, selected_project_id, saved_file_id)
                        st.error(upload_error)
                    else:
                        submission_result = create_project_submission(
                            company_id=st.session_state.company_id,
                            employee_id=employee_id,
                            submitted_by_user_id=st.session_state.user_id,
                            project_id=selected_project_id,
                            submission_note=submission_note,
                        )
                        if submission_result.get("status") in {"success", "already_submitted"}:
                            st.success(submission_result.get("message", "Project sent to the administrator."))
                            st.rerun()
                        else:
                            st.error(submission_result.get("message", "Project submission failed."))

            project_files = list_project_files(
                st.session_state.company_id,
                employee_id,
                selected_project_id,
            )

            if project_files:

                st.markdown("#### Uploaded Files")

                for project_file_record in project_files:

                    file_id = project_file_record["file_id"]
                    file_name = project_file_record.get(
                        "file_name",
                        "Unknown file",
                    )
                    file_type = project_file_record.get(
                        "file_type",
                        "",
                    ).upper()

                    file_size = project_file_record.get(
                        "file_size",
                        0,
                    )

                    if file_size:
                        if file_size >= 1024 * 1024:
                            size_text = (
                                f"{file_size / (1024 * 1024):.2f} MB"
                            )
                        else:
                            size_text = (
                                f"{file_size / 1024:.1f} KB"
                            )
                    else:
                        size_text = "Unknown size"

                    st.markdown(
                        f"**ðŸ“„ {file_name}**  "
                        f"`{file_type}` â€¢ {size_text}"
                    )

                    file_path = project_file_record.get(
                        "file_path",
                        "",
                    )

                    file_data = None

                    try:
                        if file_path and Path(file_path).exists():
                            file_data = Path(file_path).read_bytes()
                    except Exception:
                        file_data = None

                    file_col1, file_col2 = st.columns(2)

                    with file_col1:

                        if file_data is not None:

                            st.download_button(
                                "?? Download",
                                data=file_data,
                                file_name=file_name,
                                key=f"download_project_file_{file_id}",
                                use_container_width=True,
                            )

                        else:

                            st.warning(
                                "File is no longer available on disk."
                            )

                    with file_col2:

                        delete_file = st.button(
                            "??? Delete",
                            key=f"delete_project_file_{file_id}",
                            use_container_width=True,
                        )

                    if delete_file:

                        delete_result = delete_project_file(
                            company_id=st.session_state.company_id,
                            employee_id=employee_id,
                            project_id=selected_project_id,
                            file_id=file_id,
                        )

                        if delete_result.get("status") == "success":

                            st.success(
                                delete_result.get(
                                    "message",
                                    "Project file deleted successfully.",
                                )
                            )

                            st.rerun()

                        else:

                            st.error(
                                delete_result.get(
                                    "message",
                                    "Could not delete project file.",
                                )
                            )

                    st.divider()

            else:

                st.info(
                    "No files uploaded for this project yet."
                )

            st.markdown("### Project Submission History")
            my_submissions = list_my_project_submissions(st.session_state.company_id, employee_id)
            if my_submissions:
                st.dataframe(
                    [{"Submission ID": row["submission_id"], "Project": row.get("project_name"), "Files": row.get("file_count", 0), "Status": str(row.get("status") or "submitted").replace("_", " ").title(), "Submitted": str(row.get("created_at") or "")[:19], "Admin Feedback": row.get("admin_feedback") or ""} for row in my_submissions],
                    width="stretch", hide_index=True,
                )
            else:
                st.caption("No project has been submitted to the administrator yet.")


            # =================================================
            # PROJECT MODULES
            # =================================================

            st.markdown("### Project Modules")

            with st.form(
                "employee_project_module_form"
            ):

                module_name = st.text_input(
                    "Module Name",
                    placeholder="Example: AI Coordinator",
                )

                module_description = st.text_area(
                    "Module Description",
                    placeholder="Describe what this module does.",
                    height=80,
                )

                col1, col2 = st.columns(2)

                with col1:
                    module_progress = st.number_input(
                        "Completion (%)",
                        min_value=0.0,
                        max_value=100.0,
                        value=0.0,
                        step=10.0,
                        key="project_module_progress",
                    )

                with col2:
                    module_status = st.selectbox(
                        "Module Status",
                        [
                            "pending",
                            "in_progress",
                            "completed",
                        ],
                        key="project_module_status",
                    )

                module_submitted = st.form_submit_button(
                    "Save Module",
                    type="primary",
                )

            if module_submitted:

                result = create_project_module(
                    company_id=st.session_state.company_id,
                    employee_id=employee_id,
                    project_id=selected_project_id,
                    module_name=module_name,
                    description=module_description,
                    completion_percent=module_progress,
                    status=module_status,
                )

                if result.get("status") == "success":

                    st.success(
                        result.get(
                            "message",
                            "Module saved successfully.",
                        )
                    )

                    st.rerun()

                else:

                    st.error(
                        result.get(
                            "message",
                            "Could not save module.",
                        )
                    )

            modules = list_project_modules(
                st.session_state.company_id,
                employee_id,
                selected_project_id,
            )

            if modules:

                st.dataframe(
                    modules,
                    width="stretch",
                    hide_index=True,
                )

            else:

                st.info(
                    "No modules added to this project yet."
                )

            st.markdown("### Add Milestone")

            with st.form(
                "employee_milestone_form"
            ):

                milestone_name = st.text_input(
                    "Milestone Name",
                    placeholder="Example: Model Development Completed",
                )

                milestone_description = st.text_area(
                    "Milestone Description",
                    placeholder="Describe the milestone.",
                    height=80,
                )

                milestone_due = st.text_input(
                    "Due Date",
                    placeholder="YYYY-MM-DD",
                )

                milestone_progress = st.number_input(
                    "Completion (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=0.0,
                    step=10.0,
                )

                milestone_status = st.selectbox(
                    "Milestone Status",
                    [
                        "pending",
                        "in_progress",
                        "completed",
                    ],
                    key="milestone_status",
                )

                milestone_completed = st.text_input(
                    "Completed Date",
                    placeholder="YYYY-MM-DD",
                )

                milestone_submitted = st.form_submit_button(
                    "Save Milestone",
                    type="primary",
                )

            if milestone_submitted:

                result = create_milestone(
                    company_id=st.session_state.company_id,
                    employee_id=employee_id,
                    project_id=selected_project_id,
                    milestone_name=milestone_name,
                    description=milestone_description,
                    due_date=milestone_due,
                    completion_percent=milestone_progress,
                    status=milestone_status,
                    completed_date=milestone_completed,
                )

                if result.get("status") == "success":
                    st.success(
                        result.get(
                            "message",
                            "Milestone saved successfully.",
                        )
                    )
                    st.rerun()
                else:
                    st.error(
                        result.get(
                            "message",
                            "Could not save milestone.",
                        )
                    )

            st.markdown("### Project Milestones")

            milestones = list_milestones(
                st.session_state.company_id,
                employee_id,
                selected_project_id,
            )

            if milestones:
                st.dataframe(
                    milestones,
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.info(
                    "No milestones added for this project."
                )

    # ========================================================
    # ACHIEVEMENTS
    # ========================================================

    with achievements_tab:

        st.markdown("### Add Achievement")

        with st.form(
            "employee_achievement_form"
        ):

            achievement_title = st.text_input(
                "Achievement",
                placeholder="Example: Completed AI project successfully",
            )

            achievement_description = st.text_area(
                "Description",
                placeholder="Describe the achievement.",
                height=100,
            )

            achievement_category = st.text_input(
                "Category",
                placeholder="Project / Technical / Academic / Other",
            )

            achievement_date = st.text_input(
                "Date",
                placeholder="YYYY-MM-DD",
            )

            submitted = st.form_submit_button(
                "Save Achievement",
                type="primary",
            )

        if submitted:

            result = create_achievement(
                company_id=st.session_state.company_id,
                employee_id=employee_id,
                title=achievement_title,
                description=achievement_description,
                category=achievement_category,
                achievement_date=achievement_date,
            )

            if result.get("status") == "success":
                st.success(
                    result.get(
                        "message",
                        "Achievement saved successfully.",
                    )
                )
                st.rerun()
            else:
                st.error(
                    result.get(
                        "message",
                        "Could not save achievement.",
                    )
                )

        achievements = list_achievements(
            st.session_state.company_id,
            employee_id,
        )

        st.markdown("### My Achievements")

        if achievements:
            st.dataframe(
                achievements,
                width="stretch",
                hide_index=True,
            )
        else:
            st.info(
                "No achievements added yet."
            )

    # ========================================================
    # PARTICIPATIONS
    # ========================================================

    with participation_tab:

        st.markdown("### Add Participation")

        with st.form(
            "employee_participation_form"
        ):

            participation_type = st.selectbox(
                "Participation Type",
                [
                    "Hackathon",
                    "Workshop",
                    "Competition",
                    "Conference",
                    "Certification",
                    "Company Event",
                    "Other",
                ],
            )

            participation_title = st.text_input(
                "Title",
                placeholder="Example: AI Innovation Hackathon",
            )

            participation_description = st.text_area(
                "Description",
                placeholder="Describe your participation.",
                height=100,
            )

            participation_date = st.text_input(
                "Date",
                placeholder="YYYY-MM-DD",
            )

            participation_result = st.text_input(
                "Result / Outcome",
                placeholder="Example: Finalist / Completed / Winner",
            )

            submitted = st.form_submit_button(
                "Save Participation",
                type="primary",
            )

        if submitted:

            result = create_participation(
                company_id=st.session_state.company_id,
                employee_id=employee_id,
                participation_type=participation_type,
                title=participation_title,
                description=participation_description,
                participation_date=participation_date,
                result=participation_result,
            )

            if result.get("status") == "success":
                st.success(
                    result.get(
                        "message",
                        "Participation saved successfully.",
                    )
                )
                st.rerun()
            else:
                st.error(
                    result.get(
                        "message",
                        "Could not save participation.",
                    )
                )

        participations = list_participations(
            st.session_state.company_id,
            employee_id,
        )

        st.markdown("### My Participations")

        if participations:
            st.dataframe(
                participations,
                width="stretch",
                hide_index=True,
            )
        else:
            st.info(
                "No participation records added yet."
            )

    # ========================================================
    # PERFORMANCE
    # ========================================================

    with performance_tab:

        st.markdown("### My Feedback")

        from company.employee_portfolio_service import get_my_published_performance
        performance = get_my_published_performance(
            st.session_state.company_id,
            st.session_state.user_id,
        )

        if performance:

            st.dataframe(
                performance,
                width="stretch",
                hide_index=True,
            )

            latest = performance[0]

            st.markdown(
                f"""
                **Latest Review:** {latest.get('review_period', '')}

                **Rating:** {latest.get('rating', '')}

                **Strengths:** {latest.get('strengths') or 'Not recorded'}

                **Achievements:** {latest.get('achievements_summary', '')}

                **Areas for improvement:** {latest.get('areas_for_improvement') or 'Not recorded'}

                **Goals / recommendations:** {latest.get('goals', '')}

                **HR feedback:** {latest.get('manager_feedback', '')}

                **Additional comments:** {latest.get('feedback_comments') or 'Not recorded'}

                **Submitted:** {latest.get('created_at', '')}
                """,
            )

        else:

            st.info(
                "No performance records are available yet."
            )

    st.stop()


# ============================================================
# COMPANY ADMIN WORKSPACE
# ============================================================

if st.session_state.view == "admin":
    if current_role() != "company_admin":
        st.session_state.view = "chat"
        st.rerun()
    render_admin_portal(
        st.session_state.company_id,
        st.session_state.user_id,
    )
    st.stop()


# ============================================================
# MAIN 2-COLUMN WORKSPACE

if st.session_state.view == "chat":
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            padding-top: 1rem;
            padding-bottom: 6rem;
            max-width: 1500px;
        }
        .chat-heading {
            background: white;
            border: 1px solid #e2d8ee;
            border-radius: 16px;
            padding: 16px 20px;
            margin-bottom: 12px;
        }
        .chat-heading-title {
            font-size: 20px;
            font-weight: 750;
            color: #332943;
        }
        .chat-heading-subtitle {
            font-size: 12px;
            color: #796d89;
            margin-top: 4px;
        }
        div[data-testid="stChatMessage"] {
            border-radius: 16px;
            padding: 12px 16px;
        }
        div[data-testid="stChatInput"] {
            position: fixed;
            bottom: 12px;
            left: max(25%, 370px);
            width: min(70%, 1000px);
            z-index: 999;
            background: #f8f6fc;
            padding: 8px 10px;
        }
        @media (max-width: 700px) {
            div[data-testid="stChatInput"] {
                left: 2%;
                width: 96%;
            }
        }
        </style>
        <div class="chat-heading">
            <div class="chat-heading-title">AI Coordinator</div>
            <div class="chat-heading-subtitle">
                Your enterprise requests, conversations and follow-ups
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.messages:
        st.markdown(
            """
            <div style="text-align:center;padding:70px 20px 35px;color:#796d89">
                <div style="font-size:24px;font-weight:750;color:#3b304c">
                    How can I help with your enterprise request?
                </div>
                <p>Ask about HR, IT support, or company policies.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        examples = st.columns(3)
        if examples[0].button("Check my attendance", key="chat_example_hr", width="stretch"):
            st.session_state.pending_chat_prompt = "Check my attendance"
            st.rerun()
        if examples[1].button("My Wi-Fi is not working", key="chat_example_it", width="stretch"):
            st.session_state.pending_chat_prompt = "My Wi-Fi is not working"
            st.rerun()
    else:
        for message in st.session_state.messages:
            is_user = message.get("role") == "user"
            with st.chat_message("user" if is_user else "assistant"):
                st.markdown(str(message.get("content") or ""))
                if not is_user:
                    render_result_metadata(get_message_result(message))

# CHAT INPUT
# ============================================================

if st.session_state.view == "chat":
    prompt = st.chat_input("Message AI Coordinator...")
    pending_prompt = st.session_state.pop("pending_chat_prompt", None)
    prompt = prompt or pending_prompt
    if prompt:
        process_request(prompt)
        st.rerun()





