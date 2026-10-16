import json
import os
import re
import time
import threading
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
try:
    # Groq is an optional runtime provider when Gemini is configured as the
    # primary/fallback provider. Keep module import and provider failover alive
    # even in deployments where the Groq SDK is not installed.
    from groq import Groq
except ImportError:  # pragma: no cover - exercised in minimal deployments
    Groq = None  # type: ignore[assignment,misc]


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    "",
).strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
).strip()

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/{model}:generateContent"
)


# ============================================================
# GROQ CONFIGURATION
# ============================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    "",
).strip()

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b",
).strip()

LLM_PROVIDER = os.getenv(
    "LLM_PROVIDER",
    "groq",
).strip().lower()

# Remote-provider circuit breaker. When a provider is rate-limited or has a
# transient outage, keep it out of the request path temporarily rather than
# waiting through the same failing call on every workflow stage. This state is
# process-local and resets when Streamlit restarts.
try:
    _LLM_REQUEST_TIMEOUT_SECONDS = int(
        os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "6")
    )
except (TypeError, ValueError):
    _LLM_REQUEST_TIMEOUT_SECONDS = 6
_LLM_REQUEST_TIMEOUT_SECONDS = max(2, min(_LLM_REQUEST_TIMEOUT_SECONDS, 15))
_PROVIDER_COOLDOWNS: Dict[str, Dict[str, Any]] = {}
_PROVIDER_COOLDOWN_LOCK = threading.Lock()


def _safe_provider_failure_kind(provider: str, error: Exception) -> str:
    """Return a concise, non-sensitive failure label for logs and fallback."""
    text = str(error or "").casefold()
    if "429" in text or "rate limit" in text or "rate_limit" in text:
        return "rate limited (429)"
    if "503" in text or "high demand" in text or "temporarily unavailable" in text:
        return "temporarily unavailable (503)"
    if "timeout" in text or "timed out" in text or "connection" in text:
        return "network/timeout error"
    if "401" in text or "403" in text or "api key" in text or "unauthorized" in text:
        return "authentication/configuration error"
    return "request failed"


def _provider_cooldown_seconds(provider: str, error: Exception) -> int:
    """Choose a cooldown long enough to avoid repeating a known outage."""
    text = str(error or "").casefold()
    kind = _safe_provider_failure_kind(provider, error)

    if provider == "groq" and ("429" in text or "rate limit" in text or "rate_limit" in text):
        # Respect Groq's explicit server-supplied "try again in 11m19.9s"
        # guidance for quota limits when it is present.
        match = re.search(
            r"try again in\s+(?:(\d+)h)?\s*(?:(\d+)m)?\s*([\d.]+)s",
            text,
            re.IGNORECASE,
        )
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = float(match.group(3) or 0)
            return max(60, hours * 3600 + minutes * 60 + int(seconds) + 2)
        if "tokens per day" in text or "token per day" in text or "tpd" in text:
            return 15 * 60
        return 90

    if "503" in text or "high demand" in text:
        return 60
    if "429" in text or "rate limit" in text:
        return 90
    if kind == "network/timeout error":
        return 30
    if kind == "authentication/configuration error":
        return 180
    return 30


def _provider_in_cooldown(provider: str) -> tuple[bool, int, str]:
    now = time.monotonic()
    with _PROVIDER_COOLDOWN_LOCK:
        state = _PROVIDER_COOLDOWNS.get(provider)
        if not state:
            return False, 0, ""
        remaining = int(state.get("until", 0) - now)
        if remaining <= 0:
            _PROVIDER_COOLDOWNS.pop(provider, None)
            return False, 0, ""
        return True, remaining, str(state.get("kind") or "temporarily unavailable")


def _set_provider_cooldown(provider: str, error: Exception) -> tuple[int, str]:
    seconds = _provider_cooldown_seconds(provider, error)
    kind = _safe_provider_failure_kind(provider, error)
    with _PROVIDER_COOLDOWN_LOCK:
        _PROVIDER_COOLDOWNS[provider] = {
            "until": time.monotonic() + seconds,
            "kind": kind,
        }
    return seconds, kind


def _effective_llm_timeout(requested: int) -> int:
    try:
        asked = max(1, int(requested))
    except (TypeError, ValueError):
        asked = _LLM_REQUEST_TIMEOUT_SECONDS
    return min(asked, _LLM_REQUEST_TIMEOUT_SECONDS)


# ============================================================
# TOOL CAPABILITY CATALOG
# ============================================================

TOOL_CAPABILITIES: Dict[str, Dict[str, Any]] = {

    # ========================================================
    # HR
    # ========================================================

    "employee_information": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Retrieve or check employee-related information."
        ),
        "actions": [
            "employee information",
            "employee details",
            "employee records",
        ],
    },

    "leave_management": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Handle employee leave-related operations "
            "such as leave requests and leave information."
        ),
        "actions": [
            "leave",
            "vacation",
            "time off",
            "leave request",
        ],
    },

    "attendance_service": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Check or manage employee attendance information."
        ),
        "actions": [
            "attendance",
            "presence",
            "absent",
            "working days",
        ],
    },

    "benefits_service": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Provide or manage employee benefits information."
        ),
        "actions": [
            "benefits",
            "employee benefits",
            "insurance benefits",
        ],
    },

    "hr_policy_service": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Check HR policies and policy-related information."
        ),
        "actions": [
            "HR policy",
            "company HR policy",
            "policy information",
        ],
    },

    "employee_document_service": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Handle employee HR documents."
        ),
        "actions": [
            "employee document",
            "HR document",
            "employee certificate",
        ],
    },

    "onboarding_service": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Handle employee onboarding workflows."
        ),
        "actions": [
            "onboarding",
            "new employee onboarding",
            "joiner process",
        ],
    },

    "performance_service": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Handle employee performance-related information."
        ),
        "actions": [
            "performance",
            "performance review",
            "employee evaluation",
        ],
    },

    "hr_grievance_service": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Submit a new employee HR grievance or workplace concern."
        ),
        "actions": [
            "HR grievance",
            "workplace grievance",
            "raise a workplace concern",
            "employee complaint",
        ],
    },

    "hr_training_service": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Submit a new employee training or learning request."
        ),
        "actions": [
            "request training",
            "training request",
            "Python training",
            "AI training",
            "learning request",
            "skill development",
        ],
    },

    "hr_general_request_service": {
        "department": "Human Resources",
        "agent": "HR Agent",
        "description": (
            "Submit a new general HR service request."
        ),
        "actions": [
            "general HR request",
            "HR assistance request",
            "other HR request",
            "submit an HR request",
        ],
    },

    # ========================================================
    # IT
    # ========================================================

    "create_ticket": {
        "department": "IT Support",
        "agent": "IT Support Agent",
        "description": (
            "Create an IT support ticket when the user "
            "requests or authorizes ticket creation."
        ),
        "actions": [
            "create IT ticket",
            "open support ticket",
            "raise IT ticket",
        ],
    },

    "device_service": {
        "department": "IT Support",
        "agent": "IT Support Agent",
        "description": (
            "Handle IT device-related checks and support."
        ),
        "actions": [
            "computer problem",
            "laptop problem",
            "device problem",
            "hardware troubleshooting",
        ],
    },

    "password_access_service": {
        "department": "IT Support",
        "agent": "IT Support Agent",
        "description": (
            "Handle password, account access, and access-related "
            "IT operations."
        ),
        "actions": [
            "password",
            "account access",
            "login access",
            "access problem",
        ],
    },

    "software_service": {
        "department": "IT Support",
        "agent": "IT Support Agent",
        "description": (
            "Handle software installation, software access, "
            "software licensing, and application-related requests."
        ),
        "actions": [
            "software",
            "software license",
            "application",
            "license",
            "Adobe Acrobat",
            "Microsoft Office",
            "software installation",
        ],
    },

    "knowledge_base_service": {
        "department": "IT Support",
        "agent": "IT Support Agent",
        "description": (
            "Provide IT troubleshooting and technical knowledge "
            "for issues such as VPN, network, connectivity, "
            "authentication, and technical problems."
        ),
        "actions": [
            "IT troubleshooting",
            "VPN",
            "network problem",
            "connectivity",
            "technical issue",
            "Duo",
            "Wi-Fi",
        ],
    },

    # ========================================================
    # PROCUREMENT
    # ========================================================

    "inventory_check": {
        "department": "Procurement",
        "agent": "Procurement Agent",
        "description": (
            "Check inventory and availability of procurement items."
        ),
        "actions": [
            "inventory",
            "stock",
            "availability",
        ],
    },

    "hardware_catalog": {
        "department": "Procurement",
        "agent": "Procurement Agent",
        "description": (
            "Check the currently available hardware catalog "
            "and product specifications."
        ),
        "actions": [
            "hardware catalog",
            "laptop catalog",
            "hardware options",
            "available hardware",
        ],
    },

    "purchase_request": {
        "department": "Procurement",
        "agent": "Procurement Agent",
        "description": (
            "Create a procurement purchase request. "
            "This is an action and may require explicit confirmation."
        ),
        "actions": [
            "purchase request",
            "request purchase",
            "buy equipment",
        ],
    },

    "purchase_order": {
        "department": "Procurement",
        "agent": "Procurement Agent",
        "description": (
            "Create or process a purchase order."
        ),
        "actions": [
            "purchase order",
            "PO",
            "order equipment",
        ],
    },

    "vendor_service": {
        "department": "Procurement",
        "agent": "Procurement Agent",
        "description": (
            "Check vendor and supplier information for "
            "procurement and hardware suppliers."
        ),
        "actions": [
            "vendor",
            "supplier",
            "hardware supplier",
            "vendor information",
            "supplier information",
        ],
    },

    # ========================================================
    # FINANCE
    # ========================================================

    "budget_service": {
        "department": "Finance",
        "agent": "Finance Agent",
        "description": (
            "Check budgets, available budget, or budget allocation."
        ),
        "actions": [
            "budget",
            "available budget",
            "budget allocation",
        ],
    },

    "expense_service": {
        "department": "Finance",
        "agent": "Finance Agent",
        "description": (
            "Handle employee expense and reimbursement information."
        ),
        "actions": [
            "expense",
            "expense claim",
            "reimbursement",
        ],
    },

    "invoice_service": {
        "department": "Finance",
        "agent": "Finance Agent",
        "description": (
            "Handle invoice-related operations."
        ),
        "actions": [
            "invoice",
            "invoice status",
            "invoice processing",
        ],
    },

    "payment_service": {
        "department": "Finance",
        "agent": "Finance Agent",
        "description": (
            "Handle payment-related operations."
        ),
        "actions": [
            "payment",
            "payment status",
            "make payment",
        ],
    },

    "payroll_service": {
        "department": "Finance",
        "agent": "Finance Agent",
        "description": (
            "Handle payroll-related information and operations."
        ),
        "actions": [
            "payroll",
            "salary",
            "pay slip",
        ],
    },

    # ========================================================
    # KNOWLEDGE
    # ========================================================

    "search_knowledge": {
        "department": "Knowledge Services",
        "agent": "Knowledge Agent",
        "description": (
            "Search tenant-scoped enterprise documents, uploaded company "
            "knowledge, employee handbooks, internal guides, FAQs, "
            "organizational information, and other stored knowledge "
            "when no specialized operational tool is more appropriate. "
            "Use this for document retrieval and company knowledge lookup, "
            "not for executing operational actions."
        ),
        "actions": [
            "knowledge search",
            "company information",
            "general enterprise information",
            "company documents",
            "document search",
            "search documents",
            "employee handbook",
            "internal guide",
            "company FAQ",
            "organizational information",
            "knowledge base search",
            "uploaded documents",
        ],
    },
}


# ============================================================
# GEMINI CALL
# ============================================================

def _call_gemini(
    prompt: str,
    timeout: int = 30,
    temperature: float = 0.1,
) -> str:

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    url = GEMINI_URL.format(
        model=GEMINI_MODEL,
    )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt,
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=timeout,
    )

    if response.status_code == 429:
        raise RuntimeError(
            "Gemini rate limit exceeded."
        )

    if response.status_code >= 400:

        try:
            error_data = response.json()

            error_message = (
                error_data
                .get("error", {})
                .get("message", response.text)
            )

        except Exception:
            error_message = response.text

        raise RuntimeError(
            f"Gemini API error {response.status_code}: "
            f"{error_message}"
        )

    data = response.json()

    candidates = data.get(
        "candidates",
        [],
    )

    if not candidates:
        raise RuntimeError(
            "Gemini returned no candidates."
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    text_parts = []

    for part in parts:

        text = part.get("text")

        if text:
            text_parts.append(text)

    result = "\n".join(
        text_parts
    ).strip()

    if not result:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    return result


# ============================================================
# GROQ CALL
# ============================================================

def _call_groq(
    prompt: str,
    timeout: int = 30,
    temperature: float = 0.1,
    max_completion_tokens: int = 256,
) -> str:

    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    if Groq is None:
        raise RuntimeError(
            "Groq provider is unavailable because the optional groq SDK is not installed."
        )

    client = Groq(
        api_key=GROQ_API_KEY,
        timeout=timeout,
        max_retries=0,
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=temperature,
        reasoning_effort="low",
        include_reasoning=False,
        max_completion_tokens=max_completion_tokens,
    )

    if not response.choices:
        raise RuntimeError(
            "Groq returned no choices."
        )

    content = (
        response
        .choices[0]
        .message
        .content
    )

    if not content:
        raise RuntimeError(
            "Groq returned an empty response."
        )

    return content.strip()


# ============================================================
# LLM PROVIDER FALLBACK
# ============================================================

def _call_llm(
    prompt: str,
    timeout: int = 30,
    temperature: float = 0.1,
    max_completion_tokens: int = 512,
) -> Tuple[str, str]:
    """Call configured providers with bounded timeouts and an outage circuit breaker.

    A failed provider is not retried on every subsequent workflow stage while
    it is in cooldown. If every configured provider is cooling down or fails,
    the caller immediately switches to deterministic, permission-safe logic.
    """
    effective_timeout = _effective_llm_timeout(timeout)

    if LLM_PROVIDER == "gemini":
        order = ("gemini", "groq")
    elif LLM_PROVIDER == "groq":
        order = ("groq", "gemini")
    else:
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")

    configured = {
        "groq": bool(GROQ_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
    }
    if not any(configured.values()):
        raise RuntimeError("No AI provider configured; use deterministic fallback.")

    errors: list[str] = []
    attempted = 0
    skipped = 0

    for provider in order:
        if not configured[provider]:
            continue

        is_cooling, remaining, kind = _provider_in_cooldown(provider)
        if is_cooling:
            skipped += 1
            errors.append(f"{provider.title()} {kind} (cooldown ~{remaining}s)")
            continue

        attempted += 1
        try:
            if provider == "groq":
                result = _call_groq(
                    prompt=prompt,
                    timeout=effective_timeout,
                    temperature=temperature,
                    max_completion_tokens=max_completion_tokens,
                )
            else:
                result = _call_gemini(
                    prompt=prompt,
                    timeout=effective_timeout,
                    temperature=temperature,
                )

            if not result or not str(result).strip():
                raise RuntimeError(f"{provider} returned an empty response")

            with _PROVIDER_COOLDOWN_LOCK:
                _PROVIDER_COOLDOWNS.pop(provider, None)
            return str(result).strip(), provider

        except Exception as error:
            _, kind = _set_provider_cooldown(provider, error)
            errors.append(f"{provider.title()} {kind}")

    # Deliberately keep the raised message concise: never print provider
    # organization identifiers, token usage, or full upstream error payloads.
    if attempted == 0 and skipped:
        raise RuntimeError(
            "All configured AI providers are in temporary cooldown; "
            "deterministic fallback is active."
        )
    if errors:
        raise RuntimeError(
            "AI providers unavailable (" + "; ".join(errors) + "); "
            "deterministic fallback is active."
        )
    raise RuntimeError("No configured AI provider could be called; deterministic fallback is active.")


# ============================================================
# JSON EXTRACTION
# ============================================================

def _extract_json(
    text: str,
) -> Dict[str, Any]:

    if not text:
        raise ValueError(
            "Empty LLM response."
        )

    cleaned = text.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = cleaned.strip()

    try:

        data = json.loads(
            cleaned
        )

        if isinstance(
            data,
            dict,
        ):
            return data

    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")

    if start != -1:

        depth = 0
        in_string = False
        escaped = False

        for index in range(
            start,
            len(cleaned),
        ):

            char = cleaned[index]

            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1

            elif char == "}":

                depth -= 1

                if depth == 0:

                    candidate = cleaned[
                        start:index + 1
                    ]

                    try:

                        data = json.loads(
                            candidate
                        )

                        if isinstance(
                            data,
                            dict,
                        ):
                            return data

                    except json.JSONDecodeError:
                        break

    raise ValueError(
        "LLM response did not contain valid JSON."
    )


# ============================================================
# TOOL CATALOG FOR PROMPT
# ============================================================

def _build_tool_catalog_text() -> str:

    lines = []

    for name, capability in (
        TOOL_CAPABILITIES.items()
    ):

        department = capability.get(
            "department",
            "",
        )

        agent = capability.get(
            "agent",
            "",
        )

        description = capability.get(
            "description",
            "",
        )

        actions = capability.get(
            "actions",
            [],
        )

        lines.append(
            f"- TOOL: {name}\n"
            f"  DEPARTMENT: {department}\n"
            f"  AGENT: {agent}\n"
            f"  DESCRIPTION: {description}\n"
            f"  EXAMPLES OF CAPABILITY: "
            f"{', '.join(actions)}"
        )

    return "\n".join(lines)


# ============================================================
# CONVERSATION HISTORY
# ============================================================

def _history_text(
    conversation_history: Optional[
        List[Dict[str, Any]]
    ],
) -> str:

    if not conversation_history:
        return "No previous conversation."

    lines = []

    history = conversation_history[-12:]

    for item in history:

        if not isinstance(
            item,
            dict,
        ):
            continue

        role = item.get(
            "role",
            "user",
        )

        content = (
            item.get("content")
            or item.get("message")
            or ""
        )

        if not content:
            continue

        lines.append(
            f"{str(role).upper()}: {content}"
        )

    return (
        "\n".join(lines)
        or "No previous conversation."
    )


# ============================================================
# NORMALIZATION HELPERS
# ============================================================

def _as_string_list(
    value: Any,
) -> List[str]:

    if isinstance(
        value,
        str,
    ):
        value = [value]

    if not isinstance(
        value,
        list,
    ):
        return []

    result = []

    for item in value:

        if item is None:
            continue

        value_str = str(
            item
        ).strip()

        if (
            value_str
            and value_str not in result
        ):
            result.append(
                value_str
            )

    return result


def _normalize_analysis(
    analysis: Dict[str, Any],
) -> Dict[str, Any]:

    if not isinstance(
        analysis,
        dict,
    ):
        analysis = {}

    request_category = str(
        analysis.get(
            "request_category",
            "general_inquiry",
        )
        or "general_inquiry"
    ).strip()

    intent = str(
        analysis.get(
            "intent",
            "",
        )
        or ""
    ).strip()

    department = str(
        analysis.get(
            "department",
            "",
        )
        or ""
    ).strip()

    departments = _as_string_list(
        analysis.get(
            "departments",
            [],
        )
    )

    if (
        department
        and department not in departments
    ):
        departments.insert(
            0,
            department,
        )

    agents = _as_string_list(
        analysis.get(
            "agents",
            [],
        )
    )

    tools = _as_string_list(
        analysis.get(
            "tools",
            [],
        )
    )

    details = analysis.get(
        "details",
        {},
    )

    if not isinstance(
        details,
        dict,
    ):
        details = {
            "important": details
        }

    requires_action = bool(
        analysis.get(
            "requires_action",
            False,
        )
    )

    confidence = analysis.get(
        "confidence"
    )

    try:

        if confidence is not None:

            confidence = float(
                confidence
            )

            confidence = max(
                0.0,
                min(
                    1.0,
                    confidence,
                ),
            )

    except (
        TypeError,
        ValueError,
    ):

        confidence = None

    # --------------------------------------------------------
    # TOOL PLAN
    # --------------------------------------------------------

    raw_tool_plan = analysis.get(
        "tool_plan",
        [],
    )

    if not isinstance(
        raw_tool_plan,
        list,
    ):
        raw_tool_plan = []

    tool_plan = []

    for item in raw_tool_plan:

        if not isinstance(
            item,
            dict,
        ):
            continue

        tool = str(
            item.get(
                "tool",
                "",
            )
            or ""
        ).strip()

        agent = str(
            item.get(
                "agent",
                "",
            )
            or ""
        ).strip()

        purpose = str(
            item.get(
                "purpose",
                "",
            )
            or ""
        ).strip()

        if not tool:
            continue

        if tool not in TOOL_CAPABILITIES:
            continue

        tool_plan.append(
            {
                "tool": tool,
                "agent": agent,
                "purpose": purpose,
            }
        )

        if tool not in tools:
            tools.append(
                tool
            )

    # --------------------------------------------------------
    # VALIDATE TOOLS
    # --------------------------------------------------------

    tools = [
        tool
        for tool in tools
        if tool in TOOL_CAPABILITIES
    ]

    # --------------------------------------------------------
    # BUILD TOOL PLAN IF NECESSARY
    # --------------------------------------------------------

    if tools and not tool_plan:

        for tool in tools:

            capability = (
                TOOL_CAPABILITIES[
                    tool
                ]
            )

            tool_plan.append(
                {
                    "tool": tool,
                    "agent": capability.get(
                        "agent",
                        "",
                    ),
                    "purpose": capability.get(
                        "description",
                        "",
                    ),
                }
            )

    # --------------------------------------------------------
    # DERIVE AGENTS
    # --------------------------------------------------------

    for item in tool_plan:

        agent = item.get(
            "agent",
            "",
        )

        if (
            agent
            and agent not in agents
        ):
            agents.append(
                agent
            )

    # --------------------------------------------------------
    # DERIVE DEPARTMENTS
    # --------------------------------------------------------

    for tool in tools:

        capability = (
            TOOL_CAPABILITIES.get(
                tool,
                {},
            )
        )

        tool_department = (
            capability.get(
                "department",
                "",
            )
        )

        if (
            tool_department
            and tool_department
            not in departments
        ):
            departments.append(
                tool_department
            )

    if (
        not department
        and departments
    ):
        department = departments[0]

    return {
        "request_category": request_category,
        "intent": intent,
        "department": department,
        "departments": departments,
        "agents": agents,
        "tools": tools,
        "tool_plan": tool_plan,
        "details": details,
        "requires_action": requires_action,
        "confidence": confidence,
    }


# ============================================================
# AI REQUEST ANALYSIS
# ============================================================

def _gemini_analyze_request(
    message: str,
    conversation_history: Optional[
        List[Dict[str, Any]]
    ] = None,
    company_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    tool_catalog = (
        _build_tool_catalog_text()
    )

    history = _history_text(
        conversation_history
    )

    tenant_context = json.dumps(
        company_context or {},
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    prompt = f"""
You are the intelligent request-understanding engine
of a general enterprise workflow platform.

Your job is to understand ANY valid enterprise request.

Do NOT classify requests using fixed keyword rules.

Instead, reason from:

1. The user's actual intent.
2. The requested outcome.
3. The available tool capabilities.
4. Previous conversation.
5. Information contained in the request.
6. The current company context supplied below.

COMPANY CONTEXT (AUTHORITATIVE AND TENANT-SCOPED):
{tenant_context}

Treat this company context as the current approved organization data.
Use only information relevant to this request. Do not infer or invent
company policies, limits, departments, employees, or approval rules.

AVAILABLE ENTERPRISE TOOLS:

{tool_catalog}

IMPORTANT RULES:

1. Select a tool only when its capability genuinely
   matches the user's requested operation.

2. Do not select a tool merely because a word happens
   to appear in the request.

3. Select the department and agent associated with
   the actual required capability.

4. A request may require multiple departments.

5. A request may require multiple agents.

6. A request may require multiple tools.

7. When multiple tools are required, create an ordered
   tool_plan.

8. Every tool_plan item must contain:
   - tool
   - agent
   - purpose

9. Never invent a tool.

10. Only use tools from the supplied catalog.

11. Never invent a capability that is not represented
    by the available tools.

12. Distinguish between:
    - information/check requests
    - action requests

13. requires_action=true only when the user wants the
    system to perform or initiate an operational action.

14. A request for information/checking normally has
    requires_action=false.

15. Never claim that an action already happened.

16. Use previous conversation for follow-up requests.

17. If information is missing or ambiguous, capture it
    in details.

18. If no specialized operational tool is appropriate,
    use search_knowledge only when appropriate.

19. Do not use Knowledge Agent merely because a request
    contains a general business word.

20. Vendor or supplier information related to company
    hardware/procurement should use vendor_service.

21. Software licensing or application access should use
    software_service.

22. IT troubleshooting should use knowledge_base_service
    when troubleshooting information is requested.

23. Do not automatically create a ticket just because
    an IT problem exists.

24. create_ticket should be selected when the user
    requests or authorizes ticket creation.

29. Finance tools should be selected when the actual
    operation is financial.

30. Procurement tools should be selected for purchasing,
    inventory, hardware catalog, vendors, and procurement.

31. HR tools should be selected for employee HR operations.

32. IT tools should be selected for technology, software,
    access, connectivity, and IT support operations.

33. Do not add Finance merely because a purchase has a price.

34. Do not add Procurement merely because software costs money.

35. For several independent tasks, select all relevant
    tools and agents.

36. Confidence must represent confidence in the
    interpretation from 0.0 to 1.0.

37. Think through the request before producing JSON,
    but return ONLY JSON.

PREVIOUS CONVERSATION:

{history}

CURRENT USER REQUEST:

{message}

Return exactly this structure:

{{
  "request_category": "enterprise_action | information_request | troubleshooting | general_inquiry | follow_up",
  "intent": "short description of what the user wants",
  "department": "primary department or empty string",
  "departments": [
    "department names"
  ],
  "agents": [
    "agent names"
  ],
  "tools": [
    "tool names from the catalog"
  ],
  "tool_plan": [
    {{
      "tool": "exact tool name",
      "agent": "agent responsible",
      "purpose": "why this tool is required"
    }}
  ],
  "details": {{
    "important": "structured information extracted from the request"
  }},
  "requires_action": false,
  "confidence": 0.0
}}
"""

    raw_response, provider = _call_llm(
        prompt=prompt,
        timeout=30,
        temperature=0.0,
        max_completion_tokens=1024,
    )

    analysis = _extract_json(
        raw_response
    )

    result = _normalize_analysis(
        analysis
    )

    result["llm_provider"] = provider

    return result


# ============================================================
# SAFE FALLBACK ANALYSIS
# ============================================================

def local_fallback_analyze(
    message: str,
    conversation_history: Optional[
        List[Dict[str, Any]]
    ] = None,
    company_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Route common requests deterministically when remote models are absent."""
    import re
    from datetime import date, timedelta

    text = str(message or "").strip()
    lowered = text.casefold()
    context = company_context if isinstance(company_context, dict) else {}
    history_text = _history_text(conversation_history)
    # When the last assistant turn asked for a missing slot, interpret the
    # employee's short reply in that request's context instead of starting a
    # new unrelated workflow. The provider-backed coordinator gets the same
    # conversation history through its prompt when configured.
    prior_user = next((str(item.get("content") or item.get("message") or "").strip()
                       for item in reversed(conversation_history or [])
                       if isinstance(item, dict) and str(item.get("role") or "user").lower() == "user"
                       and str(item.get("content") or item.get("message") or "").strip()), "")
    prior_assistant = next((str(item.get("content") or item.get("message") or "").strip()
                            for item in reversed(conversation_history or [])
                            if isinstance(item, dict) and str(item.get("role") or "").lower() == "assistant"
                            and str(item.get("content") or item.get("message") or "").strip()), "")
    from core.conversation_intent import is_clear_new_request_during_clarification
    awaiting_slot = bool(prior_user and prior_assistant and re.search(
        r"\b(what|which|when|please provide|include|specify|missing|need more information|what type|what dates|model|select a configured|use it for|purpose)\b",
        prior_assistant, re.IGNORECASE,
    ))
    followup = awaiting_slot and not is_clear_new_request_during_clarification(
        text, prior_user
    ) and (len(text.split()) <= 16 or bool(re.search(
        r"\b(next week|next monday|next tuesday|development|developer|ai|monday|tuesday|wednesday|thursday|friday)\b",
        lowered,
    )))
    effective_text = f"{prior_user} {text}" if followup else text
    effective_lowered = effective_text.casefold()
    details: Dict[str, Any] = {}
    routes: list[tuple[str, str, str]] = []
    category = "information_request"
    intent = "company_information"

    def add(tool: str, agent: str, department: str, purpose: str) -> None:
        routes.append((tool, agent, department))

    leave_subject = bool(re.search(r"\b(leave|vacation|time off|day off|personal days?|maternity|paternity|parental leave)\b", effective_lowered))
    action_verb = bool(re.search(r"\b(apply|request|submit|take|book|want|need|can i|could i|like to|schedule)\b", effective_lowered))
    leave_request = leave_subject and action_verb and not bool(re.search(r"\b(policy|balance|allowance|how many|what is|who approves)\b", lowered))
    leave_balance_query = bool(re.search(r"\b(leave balance|leave days|leave history|leave allowance|time off balance|how many leave|who approves leave)\b", lowered))
    leave_policy_query = bool(re.search(r"\b(leave policy|annual leave policy|vacation policy)\b", lowered))
    laptop_subject = bool(re.search(r"\b(laptop|computer|developer machine|workstation)\b", effective_lowered))
    support_context = bool(re.search(
        r"\b(trouble|problem|issue|broken|not working|isn't working|isnt working|"
        r"not connecting|can't connect|cannot connect|doesn't work|doesnt work)\b",
        effective_lowered,
    ))
    laptop_request = laptop_subject and not support_context and bool(re.search(r"\b(need|want|get|request|purchase|buy|order|replace|replacement|not enough|upgrade|like a|new)\b", effective_lowered))
    inventory_question = laptop_subject and bool(re.search(r"\b(do we have|is there|available|in stock|what models|catalog)\b", lowered)) and not laptop_request
    it_issue = support_context or bool(re.search(r"\b(wifi|wi-fi|network|connect(?:ing|ivity)?|error|having trouble|won't start|slow)\b", effective_lowered))

    email_draft_request = (
        any(word in lowered for word in ("email", "e-mail", "message"))
        and any(word in lowered for word in ("draft", "compose", "write"))
    )

    # Deterministic service catalog for specialized HR and IT requests.
    # The same catalog is also applied at the workflow boundary so provider
    # model guesses cannot silently route these requests elsewhere.
    from core.service_catalog import classify_read_only_route, classify_specialized_request
    catalog_route = classify_read_only_route(effective_text, conversation_history)
    if catalog_route is None:
        catalog_route = classify_specialized_request(effective_text)

    if catalog_route:
        details.update(catalog_route.get("details") or {})
        category = catalog_route.get("request_category", "enterprise_action")
        intent = catalog_route.get("intent", "specialized_service_request")
        tool = (catalog_route.get("tools") or [""])[0]
        agent = (catalog_route.get("agents") or [""])[0]
        department = (catalog_route.get("departments") or [""])[0]
        if tool and agent and department:
            routes.append((tool, agent, department))

    if catalog_route:
        pass  # The specialized HR/IT catalog route above is authoritative.
    elif email_draft_request:
        category, intent = "enterprise_action", "internal_email_draft"
        routes.append(("email_draft", "Communications Agent", "Communications"))

    elif leave_request:
        category, intent = "enterprise_action", "leave_request"
        dates = _fallback_leave_date_range(effective_text)
        if dates:
            details.update({"start_date": dates[0], "end_date": dates[1]})
        else:
            single_date = re.search(
                r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b",
                effective_text,
            )
            if single_date:
                parsed_date = _fallback_leave_date_range(single_date.group(1))
                if parsed_date:
                    details["start_date"] = parsed_date[0]

        reason_match = re.search(
            r"\bfor\s+(?:my\s+)?((?:personal|medical|health|family|emergency|vacation|wedding)\s+(?:reasons?|leave|purposes?|function|functions|event|events|work|matter|matters))\b",
            effective_text,
            re.IGNORECASE,
        )
        if reason_match:
            details["reason"] = reason_match.group(1).strip()

        leave_type = next((name for name in (
            "maternity leave", "paternity leave", "parental leave", "annual leave",
            "sick leave", "personal leave", "casual leave", "unpaid leave", "vacation"
        ) if name in effective_lowered), "")
        if leave_type:
            details["leave_type"] = "Annual Leave" if leave_type == "vacation" else leave_type.title()
        routes.append(("leave_management", "HR Agent", "HR"))
    elif laptop_request:
        category, intent = "enterprise_action", "laptop_purchase_request"
        details["item_type"] = "laptop"
        purpose = next((value for term, value in (("ai", "AI development"), ("machine learning", "AI development"), ("development", "software development"), ("developer", "software development"), ("design", "design")) if term in effective_lowered), "")
        if purpose:
            details["use_case"] = purpose
        routes.extend([
            ("hardware_catalog", "Procurement Agent", "Procurement"),
            ("inventory_check", "Procurement Agent", "Procurement"),
            ("budget_service", "Finance Agent", "Finance"),
            ("purchase_request", "Procurement Agent", "Procurement"),
        ])
    elif it_issue:
        category, intent = "enterprise_action", "it_support_ticket"
        details.update({"priority": "medium", "category": "connectivity" if re.search(r"wifi|wi-fi|network|connect", effective_lowered) else "support"})
        routes.append(("create_ticket", "IT Support Agent", "IT"))
    elif inventory_question:
        category, intent = "information_request", "inventory_availability"
        details["item_type"] = "laptop"
        routes.extend([("hardware_catalog", "Procurement Agent", "Procurement"), ("inventory_check", "Procurement Agent", "Procurement")])
    elif re.search(r"\b(install|installation|software|application|app|github|access to|account access)\b", lowered):
        category, intent = "enterprise_action", "software_or_access_request"
        routes.append(("software_service", "IT Support Agent", "IT"))
    elif any(term in lowered for term in ("expense", "reimbursement", "expense claim")) and any(term in lowered for term in ("submit", "file", "claim", "expense of", "expense for", "₹", "inr")):
        category, intent = "enterprise_action", "expense_reimbursement"
        amount_match = re.search(r"(?:₹|\binr\s*)\s*([\d,]+(?:\.\d{1,2})?)|\b(?:expense|amount)\s+(?:of\s+)?₹?\s*([\d,]+(?:\.\d{1,2})?)", lowered, re.IGNORECASE)
        if amount_match:
            details["amount"] = float((amount_match.group(1) or amount_match.group(2)).replace(",", ""))
            details["currency"] = "INR"
        routes.append(("expense_service", "Finance Agent", "Finance"))
    elif ((re.search(r"\b(transfer|send|wire|move)\b", lowered) and re.search(r"\b(bank|account|money|funds)\b|₹|\binr\b|\b\d[\d,]*(?:\.\d+)?\b", lowered)) or re.search(r"\b(payment processing|make a payment)\b", lowered)):
        category, intent = "enterprise_action", "payment_processing"
        routes.append(("payment_service", "Finance Agent", "Finance"))
    elif "payroll" in lowered or "payslip" in lowered or "salary slip" in lowered:
        category, intent = "information_request", "payroll_information"
        routes.append(("payroll_service", "Finance Agent", "Finance"))
    elif (
        any(term in effective_lowered for term in (
            "training", "python course", "ai course", "skill development",
            "upskilling", "learning request", "technical course",
        ))
        and any(term in effective_lowered for term in (
            "request", "submit", "apply", "need", "want", "training",
            "course", "learn",
        ))
    ):
        category, intent = "enterprise_action", "hr_training_request"
        routes.append(("hr_training_service", "HR Agent", "HR"))
    elif any(term in lowered for term in (
        "grievance", "workplace complaint", "employee complaint",
    )):
        category, intent = "enterprise_action", "hr_grievance"
        routes.append(("hr_grievance_service", "HR Agent", "HR"))
    elif (
        bool(re.search(
            r"\b(?:show|list|display|view|retrieve|get|check|find)\b",
            lowered,
        ))
        and bool(re.search(r"\b(?:hr\s+)?requests?\b", lowered))
        and bool(re.search(
            r"\b(?:history|status|approval|approved|rejected|pending|records?)\b",
            lowered,
        ))
    ):
        category, intent = "information_request", "hr_request_history"
        routes.append(("hr_general_request_service", "HR Agent", "HR"))
    elif any(term in lowered for term in (
        "general hr request", "hr assistance", "other hr request",
    )):
        category, intent = "enterprise_action", "general_hr_request"
        routes.append(("hr_general_request_service", "HR Agent", "HR"))
    elif any(word in lowered for word in ("benefit", "insurance", "wellness")):
        routes.append(("benefits_service", "HR Agent", "HR"))
    elif leave_subject and (leave_balance_query or "approv" in lowered or "balance" in lowered):
        routes.append(("leave_management", "HR Agent", "HR"))
    elif leave_policy_query:
        routes.append(("hr_policy_service", "HR Agent", "HR"))
    elif any(term in lowered for term in ("policy", "purchase limit", "laptop budget", "leave allowance")):
        routes.append(("hr_policy_service", "HR Agent", "HR"))
    elif any(word in lowered for word in ("inventory", "in stock", "available laptop", "hardware catalog", "laptop models", "developer laptops")):
        routes.extend([("hardware_catalog", "Procurement Agent", "Procurement"), ("inventory_check", "Procurement Agent", "Procurement")])
    elif any(word in lowered for word in ("vendor", "supplier")):
        routes.append(("vendor_service", "Procurement Agent", "Procurement"))
    elif any(word in lowered for word in ("email", "message")) and any(word in lowered for word in ("draft", "compose", "write")):
        category, intent = "enterprise_action", "internal_email_draft"
        routes.append(("email_draft", "Communications Agent", "Communications"))
    else:
        routes.append(("search_knowledge", "Knowledge Agent", "Knowledge"))

    plans = [{"tool": tool, "agent": agent, "purpose": f"Run the {department} workflow using tenant data."} for tool, agent, department in routes]
    departments = list(dict.fromkeys(department for _, _, department in routes))
    agents = list(dict.fromkeys(agent for _, agent, _ in routes))
    return {
        "request_category": category,
        "intent": intent,
        "department": departments[0] if departments else "",
        "departments": departments,
        "agents": agents,
        "tools": list(dict.fromkeys(tool for tool, _, _ in routes)),
        "tool_plan": plans,
        "details": {**details, "message": effective_text, "analysis_status": "deterministic_fallback", "previous_context_available": bool(history_text and history_text != "No previous conversation."), "follow_up_applied": followup},
        "requires_action": category == "enterprise_action",
        "confidence": 0.65 if intent != "company_information" else 0.35,
        "llm_provider": "deterministic_fallback",
    }


def _fallback_leave_date_range(text: str) -> tuple[str, str] | None:
    """Parse common explicit leave date ranges without external dependencies."""
    import re
    from datetime import date, datetime, timedelta

    current_year = date.today().year
    # Parse Indian numeric dates: DD-MM-YYYY or DD/MM/YYYY
    numeric_range = re.search(
        r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\s*"
        r"(?:,|and|&|to|through|until|\s-\s)\s*"
        r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if numeric_range:
        try:
            first = date(int(numeric_range.group(3)), int(numeric_range.group(2)), int(numeric_range.group(1)))
            second = date(int(numeric_range.group(6)), int(numeric_range.group(5)), int(numeric_range.group(4)))
            return first.isoformat(), second.isoformat()
        except ValueError:
            return None

    # A single explicit date is only a start date, not a date range.
    # The caller should ask the employee for the missing end date.
    single_date = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", text)
    if single_date:
        try:
            parsed = date(int(single_date.group(3)), int(single_date.group(2)), int(single_date.group(1)))
            return parsed.isoformat(), ""
        except ValueError:
            return None

    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\s+(?:to|through|until|-)\s+(20\d{2}-\d{2}-\d{2})\b", text, re.IGNORECASE)
    if iso:
        try:
            first, second = date.fromisoformat(iso.group(1)), date.fromisoformat(iso.group(2))
            return first.isoformat(), second.isoformat()
        except ValueError:
            return None
    months = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    named = re.search(rf"\b(?:from\s+)?({months})\s+(\d{{1,2}})(?:,?\s+(20\d{{2}}))?\s+(?:to|through|until|-)\s+({months})\s+(\d{{1,2}})(?:,?\s+(20\d{{2}}))?\b", text, re.IGNORECASE)
    if named:
        first_year = int(named.group(3) or current_year)
        second_year = int(named.group(6) or first_year)
        try:
            first = datetime.strptime(f"{named.group(1)} {named.group(2)} {first_year}", "%B %d %Y").date()
        except ValueError:
            try:
                first = datetime.strptime(f"{named.group(1)} {named.group(2)} {first_year}", "%b %d %Y").date()
            except ValueError:
                return None
        try:
            second = datetime.strptime(f"{named.group(4)} {named.group(5)} {second_year}", "%B %d %Y").date()
        except ValueError:
            try:
                second = datetime.strptime(f"{named.group(4)} {named.group(5)} {second_year}", "%b %d %Y").date()
            except ValueError:
                return None
        return first.isoformat(), second.isoformat()
    weekdays = {name: index for index, name in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))}
    day_words = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    named_weekdays = re.findall(rf"\b({day_words})\b", text, re.IGNORECASE)
    if len(named_weekdays) > 1 and re.search(r"\bnext\b", text, re.IGNORECASE):
        first_day = weekdays[named_weekdays[0].lower()]
        start = date.today() + timedelta(days=(first_day - date.today().weekday()) % 7 or 7)
        dates = [start]
        previous_offset = first_day
        for value in named_weekdays[1:]:
            offset = weekdays[value.lower()]
            if offset <= previous_offset:
                offset += 7
            dates.append(start + timedelta(days=offset - first_day))
            previous_offset = offset
        return dates[0].isoformat(), dates[-1].isoformat()
    if re.search(r"\bnext\s+week\b", text, re.IGNORECASE):
        monday = date.today() + timedelta(days=7 - date.today().weekday())
        requested_weekdays = re.findall(rf"\b({day_words})\b", text, re.IGNORECASE)
        if requested_weekdays:
            dates = sorted({monday + timedelta(days=weekdays[value.lower()]) for value in requested_weekdays})
            return dates[0].isoformat(), dates[-1].isoformat()
        duration = re.search(r"\b(?:for\s+)?(\d+|one|two|three|four|five)\s+days?\b", text, re.IGNORECASE)
        number_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        if duration:
            count = int(duration.group(1)) if duration.group(1).isdigit() else number_words[duration.group(1).lower()]
            return monday.isoformat(), (monday + timedelta(days=count - 1)).isoformat()
        return None
    relative = re.search(rf"\b(?:next\s+)?({day_words})\b", text, re.IGNORECASE)
    if relative:
        start = date.today() + timedelta(days=(weekdays[relative.group(1).lower()] - date.today().weekday()) % 7 or 7)
        end = start
        duration = re.search(r"\b(?:for|from)\s+(\d+|one|two|three|four|five)\s+days?\b", text, re.IGNORECASE)
        number_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        if duration:
            count = int(duration.group(1)) if duration.group(1).isdigit() else number_words[duration.group(1).lower()]
            end += timedelta(days=count - 1)
        return start.isoformat(), end.isoformat()
    return None


# ============================================================
# PUBLIC ANALYSIS FUNCTION
# ============================================================

def analyze_request(
    message: str,
    conversation_history: Optional[
        List[Dict[str, Any]]
    ] = None,
    company_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    message = str(
        message or ""
    ).strip()

    if not message:

        return {
            "request_category": "general_inquiry",
            "intent": "",
            "department": "",
            "departments": [],
            "agents": [],
            "tools": [],
            "tool_plan": [],
            "details": {},
            "requires_action": False,
            "confidence": None,
            "llm_provider": "none",
            "analysis_status": "empty",
        }

    # Skip guaranteed provider failures (and network delays) when no
    # credentials are configured; use the deterministic enterprise router.
    if not GEMINI_API_KEY and not GROQ_API_KEY:
        result = local_fallback_analyze(
            message=message,
            conversation_history=conversation_history,
            company_context=company_context,
        )
        result["analysis_status"] = "deterministic_fallback"
        return result

    try:

        result = _gemini_analyze_request(
            message=message,
            conversation_history=conversation_history,
            company_context=company_context,
        )

        result["analysis_status"] = (
            result.get(
                "llm_provider",
                "unknown",
            )
        )

        # Enforce the configured capability boundary when an LLM interprets
        # an external bank transfer as a status question or selects no tool.
        # The tool returns the authoritative not-configured state and never
        # performs a transaction.
        requires_transfer_capability = bool(re.search(
            r"\b(transfer|send|wire|move)\b",
            message,
            re.IGNORECASE,
        ) and re.search(r"\b(bank|account|money|funds)\b|₹|\binr\b", message, re.IGNORECASE))
        if requires_transfer_capability and "payment_service" not in (result.get("tools") or []):
            guarded = local_fallback_analyze(message, conversation_history, company_context)
            for key in ("request_category", "intent", "department", "departments", "agents", "tools", "tool_plan", "details", "requires_action", "confidence"):
                result[key] = guarded.get(key)
            result["capability_guard"] = "unconfigured_payment_service"

        # Ensure explicit email-draft requests use the communications tool.
        if (
            re.search(r"\b(email|e-mail|message)\b", message, re.IGNORECASE)
            and re.search(r"\b(draft|compose|write)\b", message, re.IGNORECASE)
            and not result.get("tools")
        ):
            guarded = local_fallback_analyze(
                message=message,
                conversation_history=conversation_history,
                company_context=company_context,
            )
            for key in (
                "request_category", "intent", "department", "departments",
                "agents", "tools", "tool_plan", "details",
                "requires_action", "confidence",
            ):
                result[key] = guarded.get(key)

        return result

    except Exception as error:

        # Log only the short circuit-breaker summary, not full upstream quota
        # payloads/organization details. This also avoids flooding the terminal
        # every time a provider is already known to be unavailable.
        print("AI analysis used deterministic fallback; remote provider unavailable or cooling down.")

        result = local_fallback_analyze(
            message=message,
            conversation_history=conversation_history,
            company_context=company_context,
        )

        result["analysis_error"] = "Remote AI providers unavailable; deterministic fallback used."
        result["analysis_status"] = "deterministic_fallback"

        return result


# ============================================================
# TOOL RESULT FORMATTER
# ============================================================

def _format_tool_result(
    result: Any,
) -> str:

    if result is None:

        return (
            "The selected tool did not return a result."
        )

    if isinstance(
        result,
        str,
    ):
        return result

    try:

        return json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    except Exception:

        return str(result)


# ============================================================
# TOOL SUCCESS CHECK
# ============================================================

def _tool_execution_is_successful(
    item: Any,
) -> bool:

    if not isinstance(
        item,
        dict,
    ):
        return False

    status = str(
        item.get(
            "status",
            "",
        )
        or ""
    ).lower()

    if status in {
        "error",
        "failed",
        "failure",
        "pending_confirmation",
        "no_result",
    }:
        return False

    if item.get(
        "executed"
    ) is False:
        return False

    if (
        "result" in item
        and item.get("result") is None
    ):
        return False

    return status == "success"


# ============================================================
# RESULT MESSAGE EXTRACTION
# ============================================================

def _extract_result_message(
    item: Any,
) -> str:

    if not isinstance(
        item,
        dict,
    ):
        return ""

    # Direct tool result
    direct_message = item.get(
        "message"
    )

    if direct_message:
        return str(
            direct_message
        )

    # Nested tool result
    nested = item.get(
        "result"
    )

    if isinstance(
        nested,
        dict,
    ):

        nested_message = (
            nested.get("message")
            or nested.get("reason")
            or nested.get("error")
        )

        if nested_message:
            return str(
                nested_message
            )

    elif nested not in (
        None,
        "",
        [],
        {},
    ):

        return str(
            nested
        )

    return ""


# ============================================================
# SAFE LOCAL RESPONSE
# ============================================================

def local_fallback_response(
    message: str,
    intent: str = "",
    department: str = "",
    agent: str = "",
    tool_results: Optional[
        List[Any]
    ] = None,
    validation: Optional[
        Dict[str, Any]
    ] = None,
    decision: Optional[
        Dict[str, Any]
    ] = None,
    conversation_history: Optional[
        List[Dict[str, Any]]
    ] = None,
) -> str:

    results = tool_results or []

    if not results:
        message_text = str(message or "").strip()
        lower_message = message_text.casefold()

        if (
            "python" in lower_message
            and any(term in lower_message for term in ("learn", "learning", "beginner", "start"))
        ):
            return (
                "To learn Python, start with variables, data types, conditions, loops, "
                "functions, lists/dictionaries, files and exceptions. Use the official "
                "Python tutorial as a reference, practise in VS Code or a notebook, "
                "and build small projects such as a calculator or file organiser. "
                "This is general guidance; no company request was submitted."
            )

        if "?" in message_text and not any(
            word in lower_message for word in ("company", "our policy", "my request", "my ticket", "approval", "leave balance")
        ):
            return (
                "The AI providers are temporarily unavailable, so I cannot generate a full answer right now. "
                "Please retry shortly. No business action was performed by this response."
            )

        return (
            "I could not verify the requested information because the AI response service is temporarily unavailable. "
            "No business action was performed by this response. Please retry shortly."
        )

    successful = []
    pending = []
    failed = []
    unknown = []

    for item in results:

        if not isinstance(
            item,
            dict,
        ):
            unknown.append(
                item
            )
            continue

        status = str(
            item.get(
                "status",
                "",
            )
            or ""
        ).lower()

        if status == "pending_confirmation":

            pending.append(
                item
            )

        elif status in {
            "error",
            "failed",
            "failure",
        }:

            failed.append(
                item
            )

        elif status == "success":

            # IMPORTANT:
            # A successful tool may return its useful fields
            # directly without a nested "result" key.
            #
            # Example:
            # {
            #     "status": "success",
            #     "action": "Inventory check",
            #     "available": True,
            #     "available_items": [...]
            # }
            #
            # This is still a valid successful result.

            if item.get("executed") is False:
                unknown.append(
                    item
                )
            else:
                successful.append(
                    item
                )

        elif status == "no_result":

            unknown.append(
                item
            )

        else:

            unknown.append(
                item
            )

    # --------------------------------------------------------
    # PENDING CONFIRMATION
    # --------------------------------------------------------

    if pending:

        messages = []

        for item in pending:

            message_text = _extract_result_message(
                item
            )

            if message_text:
                messages.append(
                    message_text
                )

        if messages:

            return "\n".join(
                messages
            )

        return (
            "This action requires your confirmation "
            "before it can be performed."
        )

    # --------------------------------------------------------
    # FAILED
    # --------------------------------------------------------

    if failed:

        messages = []

        for item in failed:

            message_text = _extract_result_message(
                item
            )

            if message_text:
                messages.append(
                    message_text
                )

        if messages:

            return (
                "I couldn't complete the requested "
                "operation.\n\n"
                + "\n".join(
                    messages
                )
            )

        return (
            "I couldn't complete the requested operation "
            "because the selected service reported an error."
        )

    # --------------------------------------------------------
    # UNKNOWN / NO RESULT
    # --------------------------------------------------------

    if unknown and not successful:

        return (
            "I wasn't able to confirm the requested operation "
            "because the selected service did not return a "
            "usable result. No completion was claimed."
        )

    # --------------------------------------------------------
    # SUCCESSFUL RESULTS
    # --------------------------------------------------------

    if successful:

        messages = []

        for item in successful:

            message_text = _extract_result_message(
                item
            )

            if message_text:
                messages.append(
                    message_text
                )
                continue

            # If there is no message, return the actual
            # structured result instead of claiming that
            # no result exists.
            messages.append(
                _format_tool_result(
                    item
                )
            )

        if messages:

            return "\n\n".join(
                messages
            )

    return (
        "I could not confirm a completed result "
        "from the available services."
    )


# ============================================================
# GEMINI/GROQ FINAL RESPONSE
# ============================================================

def chat_with_gemini(
    message: str,
    intent: str = "",
    department: str = "",
    agent: str = "",
    tool_results: Optional[
        List[Any]
    ] = None,
    validation: Optional[
        Dict[str, Any]
    ] = None,
    decision: Optional[
        Dict[str, Any]
    ] = None,
    conversation_history: Optional[
        List[Dict[str, Any]]
    ] = None,
    company_context: Optional[Dict[str, Any]] = None,
) -> str:

    tool_results = tool_results or []

    history = _history_text(
        conversation_history
    )

    result_text = "\n".join(
        _format_tool_result(item)
        for item in tool_results
    )

    validation_text = json.dumps(
        validation or {},
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    decision_text = json.dumps(
        decision or {},
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    tenant_context = json.dumps(
        company_context or {},
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    prompt = f"""
You are the final response agent for a general enterprise workflow platform.

Your job is to answer the user using ONLY facts supported by the workflow
analysis and actual tool results.

USER REQUEST:
{message}

USER INTENT:
{intent}

DEPARTMENT:
{department}

ASSIGNED AGENT:
{agent}

ACTUAL TOOL RESULTS:
{result_text or "No tool result was returned."}

VALIDATION:
{validation_text}

DECISION:
{decision_text}

CURRENT COMPANY CONTEXT (TENANT-SCOPED):
{tenant_context}

Use company context only to explain or interpret the actual workflow results.
Do not invent an operational result from policy or company context alone.

PREVIOUS CONVERSATION:
{history}

ANSWERING MODE:

The user may ask either enterprise-specific questions or general questions.

A. COMPANY-SPECIFIC QUESTIONS
When the user asks about this company's:
- policies
- budgets
- leave limits
- approvals
- employees
- departments
- company processes
- requests
- workflow status
- operational data

use only tenant-scoped company context, policy data, validated tool results,
and previous conversation context supplied to you.

Never guess or invent company-specific facts.

B. GENERAL KNOWLEDGE QUESTIONS
When the user asks a general question that does not require company-specific
data, answer normally using your general knowledge.

Examples include:
- "What is procurement?"
- "What is an API?"
- "Explain cloud computing."
- "How can I improve Python problem solving?"
- "What is machine learning?"

Do not force a company lookup when the question is clearly general.

C. MIXED QUESTIONS
When a question contains both company-specific and general parts, answer both.

For example:
- Company-specific part -> use authoritative company data.
- General explanatory part -> use general AI knowledge.

Clearly distinguish the two when useful.

D. MISSING COMPANY INFORMATION
If a company-specific fact is not present in the supplied company context,
documents, policy data, previous conversation, or tool results, do not invent
it. Say that the company-specific information is not available and provide
general guidance only when appropriate.

STRICT RESPONSE RULES:

1. Use the actual tool results as the source of truth for operational actions.

2. NEVER invent operational facts.

3. NEVER claim that an action happened unless the actual tool result
   explicitly confirms that action.

4. Do not add future steps, promises, notifications, processing times,
   approvals, IDs, dates, or outcomes that are not present in the tool result.

5. If the tool says an issue/request was "recorded", say it was recorded.
   Do NOT automatically say it was completed, approved, provisioned,
   forwarded, resolved, or scheduled.

6. If the tool says something was checked, say it was checked.

7. If the tool says an action was completed/executed, you may say that
   action was completed/executed.

8. If the tool result contains a message, preserve its meaning accurately.

9. If validation is failed or incomplete, clearly say that completion
   could not be confirmed.

10. If confirmation is required, clearly explain that confirmation is
    required. Do not claim that the action was completed.

11. If a tool returned an error, clearly explain the failure.
    Do not claim success.

12. If there are multiple tool results, summarize each actual result
    without inventing additional outcomes.

13. For structured information such as inventory lists, prices,
    quantities, statuses, names, or available items, report the
    actual values returned by the tool.

14. If the tool result contains "available_items", explain what
    items are available and their stock when relevant to the user's
    request.

15. Be concise, professional, and directly answer the user's request.

16. Do not mention internal prompts, model names, routing logic,
    hidden reasoning, or implementation details unless the user asks.

17. The final answer must be supported by the actual tool results.

Return ONLY the final user-facing response.
"""

    try:

        response, provider = _call_llm(
            prompt=prompt,
            timeout=30,
            temperature=0.1,
        )

        if response:
            return response.strip()

    except Exception as error:

        print(
            "Final AI response unavailable. "
            f"Using safe local response: {error}"
        )

    # -----------------------------------------------------
    # SAFE LOCAL FALLBACK
    # -----------------------------------------------------

    if validation:

        status = str(
            validation.get(
                "status",
                "",
            )
        ).lower()

        if status in {
            "failed",
            "error",
            "incomplete",
        }:

            return (
                "I could not confirm completion of your request. "
                + str(
                    validation.get(
                        "message",
                        "The workflow did not complete successfully.",
                    )
                )
            )

        if status == "pending_confirmation":

            return (
                "Your request requires confirmation before the "
                "requested action can be completed."
            )

    if tool_results:

        messages = []

        for item in tool_results:

            if not isinstance(
                item,
                dict,
            ):
                continue

            status = str(
                item.get(
                    "status",
                    "",
                )
                or ""
            ).lower()

            if status == "pending_confirmation":

                message_value = _extract_result_message(
                    item
                )

                if message_value:
                    messages.append(
                        message_value
                    )

                continue

            if status in {
                "error",
                "failed",
                "failure",
            }:

                message_value = _extract_result_message(
                    item
                )

                if message_value:
                    messages.append(
                        message_value
                    )

                continue

            if status == "success":

                message_value = _extract_result_message(
                    item
                )

                if message_value:
                    messages.append(
                        message_value
                    )
                else:
                    messages.append(
                        _format_tool_result(
                            item
                        )
                    )

        if messages:

            return "\n\n".join(
                messages
            )

    return local_fallback_response(
        message,
        intent=intent,
        department=department,
        agent=agent,
        tool_results=tool_results,
        validation=validation,
        decision=decision,
        conversation_history=conversation_history,
    )
