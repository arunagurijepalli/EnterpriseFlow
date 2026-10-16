from tools.hr_tools import (
    employee_information,
    leave_management,
    attendance_service,
    benefits_service,
    hr_policy_service,
    employee_document_service,
    onboarding_service,
    performance_service,
    hr_grievance_service,
    hr_training_service,
    hr_general_request_service,
)

from tools.it_tools import (
    create_ticket,
    device_service,
    password_access_service,
    software_service,
    knowledge_base_service,
)

from tools.procurement_tools import (
    inventory_check,
    purchase_order,
    purchase_request,
    vendor_service,
    hardware_catalog,
)

from tools.finance_tools import (
    budget_service,
    expense_service,
    invoice_service,
    payment_service,
    payroll_service,
)


from tools.knowledge_tools import search_knowledge
from tools.portfolio_tools import employee_portfolio_service
from tools.feedback_tools import my_performance_feedback
from tools.communication_tools import email_draft, send_email_tool, search_email


# ============================================================
# ENTERPRISE TOOL REGISTRY
# ============================================================

TOOL_REGISTRY = {

    # ---------------- HR ----------------

    "employee_information": employee_information,
    "leave_management": leave_management,
    "attendance_service": attendance_service,
    "benefits_service": benefits_service,
    "hr_policy_service": hr_policy_service,
    "employee_document_service": employee_document_service,
    "onboarding_service": onboarding_service,
    "performance_service": performance_service,
    "hr_grievance_service": hr_grievance_service,
    "hr_training_service": hr_training_service,
    "hr_general_request_service": hr_general_request_service,

    # ---------------- IT ----------------

    "create_ticket": create_ticket,
    "device_service": device_service,
    "password_access_service": password_access_service,
    "software_service": software_service,
    "knowledge_base_service": knowledge_base_service,

    # ---------------- Procurement ----------------

    "inventory_check": inventory_check,
    "hardware_catalog": hardware_catalog,
    "purchase_order": purchase_order,
    "purchase_request": purchase_request,
    "vendor_service": vendor_service,

    # ---------------- Finance ----------------

    "budget_service": budget_service,
    "expense_service": expense_service,
    "invoice_service": invoice_service,
    "payment_service": payment_service,
    "payroll_service": payroll_service,


    # ---------------- Knowledge ----------------

    "search_knowledge": search_knowledge,
    "employee_portfolio_service": employee_portfolio_service,
    "my_performance_feedback": my_performance_feedback,
    "email_draft": email_draft,
    "send_email": send_email_tool,
    "search_email": search_email,
}


# ============================================================
# DYNAMIC TOOL DESCRIPTIONS
# ============================================================
#
# Gemini/Coordinator uses these descriptions to understand
# WHICH tool is relevant to a user's request.
#
# This is NOT a list of hardcoded user questions.
# These are semantic capabilities of the enterprise tools.
# ============================================================

TOOL_DESCRIPTIONS = {

    # ========================================================
    # HR
    # ========================================================

    "employee_information": {
        "department": "HR",
        "purpose": "Retrieve employee profile, employee ID, role, department, or employment information.",
        "use_when": "The user needs information about an employee or employee profile."
    },

    "leave_management": {
        "department": "HR",
        "purpose": "Handle employee leave requests, leave balances, and leave-related actions.",
        "use_when": "The user wants to request, check, or manage employee leave or time off."
    },

    "attendance_service": {
        "department": "HR",
        "purpose": "Check or manage employee attendance information.",
        "use_when": "The user asks about attendance, presence, absence, or attendance records."
    },

    "benefits_service": {
        "department": "HR",
        "purpose": "Provide employee benefits information and benefit-related services.",
        "use_when": "The user asks about employee benefits or benefit eligibility."
    },

    "hr_policy_service": {
        "department": "HR",
        "purpose": "Retrieve or explain HR policies and employee policy information.",
        "use_when": "The user asks about company HR rules, policies, eligibility, or procedures."
    },

    "employee_document_service": {
        "department": "HR",
        "purpose": "Handle employee-related documents and document requests.",
        "use_when": "The user needs an employee document, employment document, or HR document."
    },

    "onboarding_service": {
        "department": "HR",
        "purpose": "Support employee onboarding workflows and onboarding requirements.",
        "use_when": "The user is onboarding a new employee or asking about onboarding tasks."
    },

    "performance_service": {
        "department": "HR",
        "purpose": "Handle employee performance-related information and workflows.",
        "use_when": "The user asks about performance reviews, goals, or employee performance processes."
    },

    "hr_grievance_service": {
        "department": "HR",
        "purpose": "Submit an employee grievance for HR review.",
        "use_when": "The employee reports a workplace concern, complaint, or grievance."
    },

    "hr_training_service": {
        "department": "HR",
        "purpose": "Submit a training or professional-development request.",
        "use_when": "The employee requests training, upskilling, or professional development."
    },

    "hr_general_request_service": {
        "department": "HR",
        "purpose": "Retrieve existing HR request history/status or submit a tracked, approval-gated HR request. Supported tracked categories include employment verification and salary certificates, expense reimbursement, relocation, medical accommodations, visa/immigration, confidential ethics reports, payroll/tax/bank-detail corrections, appraisal/promotion support, attendance corrections, insurance claims/enrollment, onboarding/offboarding support, and HR documents.",
        "use_when": "Use for a genuine HR submission not handled by leave, policy, benefits, grievance or training tools, and for read-only HR request history/status. A new request is persisted to the tenant request store and requires approval; it does not itself execute payroll, insurer, visa, bank, or other external operations. History questions must be read-only and must never create a new request."
    },


    # ========================================================
    # IT
    # ========================================================

    "create_ticket": {
        "department": "IT",
        "purpose": "Create or retrieve a tenant-scoped IT support request/ticket and track its status. The ticket queue supports security incidents, data recovery, change requests, BYOD/MDM, offboarding access removal, office equipment, hardware peripherals and other IT follow-up work.",
        "use_when": "Use when the employee explicitly asks to open/raise/report an IT ticket, or for read-only ticket ID/status/history follow-up. General troubleshooting should use knowledge_base_service first. Ticket submission requires user confirmation, and this tool records the request; it does not by itself reset credentials, restore data, change MDM, whitelist domains, revoke access, or deploy changes."
    },

    "device_service": {
        "department": "IT",
        "purpose": "Check or manage company devices, device information, and device-related services.",
        "use_when": "The user has a device-specific issue or needs device information/support."
    },

    "password_access_service": {
        "department": "IT",
        "purpose": "Handle password reset, account access, and credential-related support.",
        "use_when": "The user cannot access an account, forgot a password, or needs access reset."
    },

    "software_service": {
        "department": "IT",
        "purpose": "Handle software installation, software access, licensing, and software-related support.",
        "use_when": "The user needs software installed, software access, application support, or a software license."
    },

    "knowledge_base_service": {
        "department": "IT",
        "purpose": "Search access-controlled tenant IT knowledge documents and provide safe general troubleshooting guidance if no matching company instructions exist.",
        "use_when": "Use for network, internet, VPN, device, printer, software and technical troubleshooting questions. Search company-uploaded documents first; when none match, provide general safe steps and transparently disclose that company-specific guidance was not found. Do not create a ticket unless the employee asks to submit one."
    },


    # ========================================================
    # PROCUREMENT
    # ========================================================

    "inventory_check": {
        "department": "Procurement",
        "purpose": "Check current inventory and available stock of enterprise equipment or products.",
        "use_when": "The user asks whether an item, equipment, hardware, or product is currently available."
    },

    "hardware_catalog": {
        "department": "Procurement",
        "purpose": "Show available enterprise hardware and product specifications, prices, and options.",
        "use_when": "The user wants to compare hardware options, product models, specifications, or prices."
    },

    "purchase_request": {
        "department": "Procurement",
        "purpose": "Create and submit a procurement request for a selected item.",
        "use_when": "The user explicitly wants to request or purchase an item after the required product details are known."
    },

    "purchase_order": {
        "department": "Procurement",
        "purpose": "Process a purchase order for an approved procurement requirement.",
        "use_when": "The workflow has reached the purchase-order stage for an approved procurement."
    },

    "vendor_service": {
        "department": "Procurement",
        "purpose": "Retrieve information about enterprise vendors, suppliers, dealers, and hardware suppliers.",
        "use_when": "The user asks about suppliers, vendors, dealers, supplier information, vendor details, or approved hardware suppliers."
    },


    # ========================================================
    # FINANCE
    # ========================================================

    "budget_service": {
        "department": "Finance",
        "purpose": "Check available budget, budget limits, and whether an expense fits within the available budget.",
        "use_when": "The user asks about budget availability, spending limits, or budget verification."
    },

    "expense_service": {
        "department": "Finance",
        "purpose": "Handle business expenses and employee expense reimbursement workflows.",
        "use_when": "The user submits, checks, or asks about an expense or reimbursement."
    },

    "invoice_service": {
        "department": "Finance",
        "purpose": "Handle invoice information, invoice verification, and invoice-related processing.",
        "use_when": "The user asks about invoices, invoice status, or invoice processing."
    },

    "payment_service": {
        "department": "Finance",
        "purpose": "Handle payment-related enterprise financial workflows.",
        "use_when": "The user asks about payments, payment status, or payment processing."
    },

    "payroll_service": {
        "department": "Finance",
        "purpose": "Handle employee payroll-related information and workflows.",
        "use_when": "The user asks about payroll, salary processing, or payroll status."
    },



    # ========================================================
    # KNOWLEDGE
    # ========================================================

    "employee_portfolio_service": {
        "department": "HR",
        "purpose": "Retrieve the logged-in employee's projects, project modules, milestones, achievements, participations, performance, and project files.",
        "use_when": "The employee asks to view their projects, project details, project progress, milestones, achievements, work history, performance, or files associated with their projects."
    },
    "my_performance_feedback": {
        "department": "HR",
        "purpose": "Retrieve only the authenticated employee's published performance feedback from the company database.",
        "use_when": "The employee asks to see, summarize, explain, or get strengths/improvement areas from their own performance feedback or latest review. Never use a chat-supplied employee ID as authorization."
    },
    "search_knowledge": {
        "department": "Knowledge",
        "purpose": "Search enterprise knowledge and general organizational information.",
        "use_when": "The user asks an informational question that does not require an operational enterprise action."
    },

    "email_draft": {
        "department": "Communications",
        "purpose": "Save an internal company email draft addressed to a company employee or department.",
        "use_when": "The user asks to draft or compose an internal company message. Never claim it was sent until the sender confirms from the draft." 
    },
    "send_email": {
        "department": "Communications",
        "purpose": "Send a saved internal company email draft after explicit sender confirmation.",
        "use_when": "The user explicitly confirms sending an existing draft by its email ID."
    },
    "search_email": {
        "department": "Communications",
        "purpose": "Search the authenticated employee's internal company inbox or sent mail.",
        "use_when": "The user asks to find, read, or search internal company messages."
    },
}


# ============================================================
# TOOL ACCESS HELPERS
# ============================================================

def get_tool(tool_name: str):
    """Return the actual executable tool by name."""
    return TOOL_REGISTRY.get(tool_name)


def list_tools():
    """Return all registered tool names."""
    return list(TOOL_REGISTRY.keys())


def get_tool_description(tool_name: str):
    """Return semantic metadata for a tool."""
    return TOOL_DESCRIPTIONS.get(tool_name)


def get_all_tool_descriptions():
    """Return semantic metadata for all registered tools."""
    return TOOL_DESCRIPTIONS


def get_tools_for_department(department: str):
    """
    Return tools that belong to a specific department.
    """
    department = str(department).strip().lower()

    return [
        tool_name
        for tool_name, metadata in TOOL_DESCRIPTIONS.items()
        if metadata.get("department", "").lower() == department
    ]

