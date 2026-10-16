from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from company.employee_portfolio_service import (
    create_performance,
    DB_PATH as PORTFOLIO_DB_PATH,
    list_project_submissions_for_admin,
    list_project_files_for_admin,
    read_project_file_for_admin,
    update_project_submission_status,
)
from company.employee_document_service import (
    submit_employee_document,
    list_company_documents_for_admin,
    get_employee_document,
    update_employee_document_status,
)
from company.document_preview import render_document_preview
from company.profile_ui import render_user_profile_page

from company.admin import (
    add_or_update_user_as_admin,
    change_user_status_as_admin,
    set_role_permissions_as_admin,
    update_company_as_admin,
)
from company.store import (
    DEFAULT_ROLE_PERMISSIONS,
    get_company,
    list_company_users,
    list_role_permissions,
)

from company.approval_service import (
    list_pending_approvals,
    approve_request,
    reject_request,
)

from company.document_service import (
    ingest_document,
    list_documents,
)

from company.updates_service import (
    create_update,
    list_updates,
    update_company_update,
    archive_update,
)
from company.catalog_service import list_inventory, list_vendors, upsert_inventory_as_admin, upsert_vendor_as_admin, seed_demo_catalog
from company.resource_service import create_resource, list_resources, archive_resource
from company.workflow_monitor_service import list_company_workflows, get_company_workflow_details
from company.operations_service import list_it_tickets, update_it_ticket, list_procurement_queue, assign_purchase_vendor
from company.request_service import (
    create_purchase_order_from_request,
    list_service_requests_for_admin,
    update_service_request_status_as_admin,
)
from company.policy_service import get_active_policies, save_policy_configuration
ROLES = list(DEFAULT_ROLE_PERMISSIONS.keys())


# ============================================================
# HELPERS
# ============================================================

def _parse_json_object(
    raw: str,
    label: str,
) -> Dict[str, Any]:

    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{label} must be valid JSON: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise ValueError(
            f"{label} must be a JSON object"
        )

    return value


def _lines(
    text: str,
) -> List[str]:

    return [
        line.strip()
        for line in text.replace(",", "\n").splitlines()
        if line.strip()
    ]


# ============================================================
# ADMIN PORTAL
# ============================================================

def render_admin_portal(
    company_id: str,
    admin_user_id: str,
) -> None:

    company = get_company(company_id)

    if not company:
        st.error(
            f"Company '{company_id}' was not found."
        )
        return

    context = company.get("context") or {}

    # ========================================================
    # ADMIN PAGE CSS
    # ========================================================

    st.markdown(
        """
        <style>

        /* ====================================================
           ADMIN PAGE
           ==================================================== */

        .admin-title {
            color: #30263c !important;
            font-size: 34px !important;
            font-weight: 850 !important;
            margin-bottom: 4px !important;
        }

        .admin-subtitle {
            color: #796d89 !important;
            font-size: 11px !important;
            line-height: 1.6 !important;
            margin-bottom: 18px !important;
        }

        /* ====================================================
           TABS
           ==================================================== */

        button[data-baseweb="tab"] {
            color: #554866 !important;
            font-weight: 700 !important;
            font-size: 11px !important;
            opacity: 1 !important;
        }

        button[data-baseweb="tab"]:hover {
            color: #7449ce !important;
        }

        button[data-baseweb="tab"][aria-selected="true"] {
            color: #7449ce !important;
            font-weight: 800 !important;
        }

        [data-baseweb="tab-list"] {
            border-bottom: 1px solid #ded5e9 !important;
        }

        /* ====================================================
           ALL INPUTS / TEXT AREAS
           ==================================================== */

        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-baseweb="base-input"] input,
        div[data-baseweb="textarea"] textarea,
        textarea {

            background-color: #ffffff !important;
            color: #30263c !important;

            -webkit-text-fill-color: #30263c !important;

            border: 1px solid #d7cce6 !important;
            border-radius: 10px !important;

            caret-color: #7449ce !important;
            opacity: 1 !important;
        }

        div[data-testid="stTextInput"] input::placeholder,
        div[data-testid="stTextArea"] textarea::placeholder,
        textarea::placeholder {

            color: #968aa2 !important;

            -webkit-text-fill-color: #968aa2 !important;

            opacity: 1 !important;
        }

        div[data-testid="stTextInput"] input:focus,
        div[data-testid="stTextArea"] textarea:focus,
        textarea:focus {

            border-color: #8060b3 !important;

            box-shadow:
                0 0 0 1px #8060b3 !important;

            outline: none !important;
        }

        /* ====================================================
           LABELS
           ==================================================== */

        div[data-testid="stTextInput"] label,
        div[data-testid="stTextArea"] label {

            color: #574a68 !important;
            font-weight: 700 !important;
            font-size: 12px !important;
        }

        div[data-testid="stTextInput"] label p,
        div[data-testid="stTextArea"] label p {

            color: #574a68 !important;
        }

        /* ====================================================
           SELECTBOX
           ==================================================== */

        div[data-testid="stSelectbox"] label {

            color: #574a68 !important;
            font-weight: 700 !important;
            font-size: 12px !important;
        }

        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {

            background: #ffffff !important;

            color: #30263c !important;

            border:
                1px solid #d7cce6 !important;

            border-radius: 10px !important;
        }

        div[data-testid="stSelectbox"] div[data-baseweb="select"] * {

            color: #30263c !important;
        }

        /* ====================================================
           FORM BUTTONS
           ==================================================== */

        div[data-testid="stFormSubmitButton"] button {

            border-radius: 10px !important;

            border:
                1px solid #7449ce !important;

            background:
                linear-gradient(
                    135deg,
                    #7449ce,
                    #8b5ad8
                ) !important;

            color: #ffffff !important;

            font-weight: 750 !important;
        }

        div[data-testid="stFormSubmitButton"] button:hover {

            border-color: #6239ae !important;

            background:
                linear-gradient(
                    135deg,
                    #663db7,
                    #8050ce
                ) !important;

            color: #ffffff !important;
        }

        /* ====================================================
           NORMAL BUTTONS
           ==================================================== */

        .stButton > button {

            border-radius: 10px !important;

            border:
                1px solid #d7cce6 !important;

            background: #ffffff !important;

            color: #443854 !important;

            font-weight: 650 !important;
        }

        .stButton > button:hover {

            border-color: #8057c2 !important;

            color: #6b43b0 !important;
        }

        /* ====================================================
           DATAFRAME
           ==================================================== */

        div[data-testid="stDataFrame"] {

            border:
                1px solid #e1d8eb !important;

            border-radius: 12px !important;

            overflow: hidden !important;
        }

        /* ====================================================
           JSON / CODE
           ==================================================== */

        div[data-testid="stJson"] {

            background: #ffffff !important;

            border:
                1px solid #e1d8eb !important;

            border-radius: 10px !important;
        }

        /* ====================================================
           INFO / SUCCESS / WARNING
           ==================================================== */

        div[data-testid="stAlert"] {

            border-radius: 11px !important;
        }

        /* ====================================================
           GENERAL TEXT
           ==================================================== */

        .stMarkdown,
        .stCaption,
        .stText {

            color: #40354f;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )

    # Override legacy admin colors with the shared accessible palette.
    st.markdown("""
    <style>
      .admin-title { color:#17171F !important; }
      .admin-subtitle { color:#555B6D !important; }
      div[data-testid="stFormSubmitButton"] button[kind="primary"], button[kind="primary"] { background:#7B3CFF !important; border-color:#7B3CFF !important; color:#FFFFFF !important; }
      .stButton > button { border-radius:11px !important; font-weight:700 !important; min-height:40px !important; }
      div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea, div[data-testid="stNumberInput"] input { color:#17171F !important; background:#FFFFFF !important; }
      div[data-testid="stSelectbox"] div[data-baseweb="select"] > div { color:#17171F !important; background:#FFFFFF !important; }
      div[data-testid="stTextInput"] label, div[data-testid="stTextArea"] label, div[data-testid="stNumberInput"] label, div[data-testid="stSelectbox"] label { color:#363746 !important; font-weight:700 !important; }
      div[data-testid="stDataFrame"] { border:1px solid #D7DFEA !important; border-radius:12px !important; overflow:hidden !important; }
      div[data-testid="stAlert"] { border-radius:12px !important; }
    </style>
    """, unsafe_allow_html=True)

    # ========================================================
    # HEADER
    # ========================================================

    st.markdown(
        '<div class="admin-title">'
        '⚙ Company Administration'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="admin-subtitle">'
        'Manage your company information, organization, policies, '
        'employees and permissions. Changes are stored in the '
        'company database and become available to the workflow '
        'after refresh.'
        '</div>',
        unsafe_allow_html=True,
    )

    # ========================================================
    # TABS
    # ========================================================

    (
        profile_tab,
        admin_profile_tab,
        org_tab,
        policy_tab,
        employees_tab,
        documents_tab,
        employee_documents_tab,
        updates_tab,
        performance_tab,
        project_submissions_tab,
        inventory_tab,
        workflow_tab,
        hr_desk_tab,
        it_desk_tab,
        procurement_tab,
    ) = st.tabs(
        [
            "Company Profile",
            "Admin Profile",
            "Organization",
            "Policies",
            "Employees",
            "Knowledge Documents",
            "Employee Documents",
            "Important Links & Updates",
            "Performance Management",
            "Project Submissions",
            "Procurement Inventory",
            "Workflow Monitor",
            "HR Service Desk",
            "IT Ticket Desk",
            "Procurement Desk",
        ]
    )

    with admin_profile_tab:
        render_user_profile_page(company_id, admin_user_id, mode="admin")

    with project_submissions_tab:
        st.subheader("Employee project submissions")
        st.caption("Review submitted project details and files. Employees can see the status and feedback after you save a decision.")
        available_statuses = ["All", "submitted", "under_review", "needs_information", "approved", "declined"]
        selected_status = st.selectbox("Submission status", available_statuses, key="admin_project_submission_status_filter")
        try:
            project_submissions = list_project_submissions_for_admin(company_id, admin_user_id, status=selected_status)
        except Exception as exc:
            project_submissions = []
            st.error(f"Project submissions could not be loaded: {exc}")
        if project_submissions:
            st.dataframe([
                {"Submission": row["submission_id"], "Project": row.get("project_name"), "Employee": row.get("employee_name") or row.get("employee_id"), "Employee ID": row.get("employee_id"), "Files": row.get("file_count", 0), "Status": str(row.get("status") or "submitted").replace("_", " ").title(), "Submitted": str(row.get("created_at") or "")[:19]}
                for row in project_submissions
            ], width="stretch", hide_index=True)
            submission_options = {
                f"#{row['submission_id']} · {row.get('project_name') or 'Project'} · {row.get('employee_name') or row.get('employee_id')} · {str(row.get('status') or 'submitted').title()}": row["submission_id"]
                for row in project_submissions
            }
            chosen_submission_label = st.selectbox("Open submission", list(submission_options.keys()), key="admin_project_submission_selected")
            chosen_submission_id = submission_options[chosen_submission_label]
            chosen_submission = next(row for row in project_submissions if int(row["submission_id"]) == int(chosen_submission_id))
            with st.container(border=True):
                st.markdown(f"### {chosen_submission.get('project_name') or 'Project submission'}")
                st.write(chosen_submission.get("project_description") or "No project description provided.")
                st.caption(f"Employee: {chosen_submission.get('employee_name') or chosen_submission.get('employee_id')} · Role: {chosen_submission.get('role_in_project') or 'Not specified'} · Dates: {chosen_submission.get('start_date') or '—'} to {chosen_submission.get('end_date') or '—'}")
                if chosen_submission.get("submission_note"):
                    st.info(f"Employee note: {chosen_submission['submission_note']}")
                project_file_records = list_project_files_for_admin(company_id, admin_user_id, int(chosen_submission["project_id"]))
                if not project_file_records:
                    st.warning("The project submission has no files available.")
                for file_record in project_file_records:
                    file_id = int(file_record["file_id"])
                    st.markdown(f"**{file_record.get('file_name') or 'Project file'}** · {int(file_record.get('file_size') or 0):,} bytes · {str(file_record.get('uploaded_at') or '')[:19]}")
                    data_result = read_project_file_for_admin(company_id, admin_user_id, file_id)
                    if data_result.get("status") == "success":
                        col_preview, col_download = st.columns(2)
                        with col_preview:
                            with st.expander("Open / read preview"):
                                render_document_preview(st, file_name=data_result["file_name"], data=data_result["data"], content_type="", key=f"admin_project_{file_id}")
                        with col_download:
                            st.download_button("Download file", data=data_result["data"], file_name=Path(data_result["file_name"]).name, key=f"admin_project_download_{file_id}", use_container_width=True)
                    else:
                        st.warning(data_result.get("message", "File is unavailable."))
                st.divider()
                with st.form(f"admin_project_review_form_{chosen_submission_id}"):
                    current_state = str(chosen_submission.get("status") or "submitted")
                    submission_states = ["submitted", "under_review", "needs_information", "approved", "declined"]
                    state = st.selectbox("Review decision", submission_states, index=submission_states.index(current_state) if current_state in submission_states else 0)
                    feedback = st.text_area("Feedback to employee", value=chosen_submission.get("admin_feedback") or "")
                    save_review = st.form_submit_button("Save project review", type="primary")
                if save_review:
                    update_result = update_project_submission_status(company_id, admin_user_id, int(chosen_submission_id), status=state, admin_feedback=feedback)
                    if update_result.get("status") == "success":
                        st.success(update_result.get("message", "Project review saved."))
                        st.rerun()
                    st.error(update_result.get("message", "Project review could not be saved."))
        else:
            st.info("No employee projects have been submitted for review yet.")

    with employee_documents_tab:
        st.subheader("Employee document exchange")
        st.caption("Documents uploaded by employees appear here. Administrators can review, download, and send documents to a selected employee.")
        employees = [row for row in list_company_users(company_id) if str(row.get("status") or "").casefold() == "active" and str(row.get("role") or "").casefold() not in {"company_admin", "hr_admin", "it_admin", "finance_admin", "procurement_admin", "recruitment_admin"}]
        if employees:
            employee_options = {f"{row.get('name') or row['user_id']} · {row.get('employee_id') or row['user_id']} · {row.get('email') or ''}": row["user_id"] for row in employees}
            with st.form("admin_send_document_to_employee_form", clear_on_submit=True):
                target_label = st.selectbox("Select employee recipient", list(employee_options.keys()))
                outbound_title = st.text_input("Document title", placeholder="Example: Reviewed project feedback")
                outbound_purpose = st.text_input("Purpose / category", placeholder="Example: HR document, project feedback, onboarding form")
                outbound_message = st.text_area("Message to employee (optional)", height=80)
                outbound_file = st.file_uploader("Choose document (max 10 MB)", type=["pdf", "txt", "md", "csv", "json", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "png", "jpg", "jpeg", "webp", "zip"], key="admin_document_upload_file")
                outbound_submit = st.form_submit_button("Send document to selected employee", type="primary", use_container_width=True)
            if outbound_submit:
                if outbound_file is None:
                    st.error("Choose a document before sending.")
                else:
                    send_result = submit_employee_document(company_id, admin_user_id, employee_options[target_label], title=outbound_title, file_name=outbound_file.name, file_data=outbound_file.getvalue(), purpose=outbound_purpose, message=outbound_message, content_type=outbound_file.type or "")
                    if send_result.get("status") == "success":
                        st.success(send_result.get("message", "Document sent."))
                        st.rerun()
                    else:
                        st.error(send_result.get("message", "Document could not be sent."))
        else:
            st.info("No active employee accounts are available as document recipients.")
        st.divider()
        status_filter = st.selectbox("Filter documents by status", ["All", "submitted", "sent", "read", "reviewed", "needs_information", "archived"], key="admin_employee_documents_status")
        try:
            all_employee_docs = list_company_documents_for_admin(company_id, admin_user_id, status=status_filter)
        except Exception as exc:
            all_employee_docs = []
            st.error(f"Employee documents could not be loaded: {exc}")
        if all_employee_docs:
            st.dataframe([{"Document ID": row["document_id"], "Title": row.get("title"), "From": row.get("sender_name"), "To": row.get("recipient_name"), "File": row.get("file_name"), "Size (bytes)": row.get("file_size"), "Status": str(row.get("status") or "submitted").replace("_", " ").title(), "Created": str(row.get("created_at") or "")[:19]} for row in all_employee_docs], width="stretch", hide_index=True)
            document_options = {f"#{row['document_id']} · {row.get('title') or row.get('file_name')} · {row.get('sender_name')} → {row.get('recipient_name')}": row["document_id"] for row in all_employee_docs}
            selected_doc_label = st.selectbox("Open employee document", list(document_options.keys()), key="admin_employee_doc_selected")
            selected_doc_id = int(document_options[selected_doc_label])
            selected_doc = get_employee_document(company_id, admin_user_id, selected_doc_id)
            if selected_doc:
                st.markdown(f"### {selected_doc.get('title') or selected_doc.get('file_name')}")
                st.caption(f"{selected_doc.get('file_name')} · {int(selected_doc.get('file_size') or 0):,} bytes · Uploaded {str(selected_doc.get('created_at') or '')[:19]}")
                if selected_doc.get("purpose"):
                    st.write(f"Purpose: {selected_doc['purpose']}")
                if selected_doc.get("message"):
                    st.write(f"Message: {selected_doc['message']}")
                col_open, col_dl = st.columns(2)
                with col_open:
                    with st.expander("Open / read document"):
                        render_document_preview(st, file_name=selected_doc["file_name"], data=selected_doc["file_data"], content_type=selected_doc.get("content_type", ""), key=f"admin_employee_doc_{selected_doc_id}")
                with col_dl:
                    st.download_button("Download original file", data=selected_doc["file_data"], file_name=selected_doc["file_name"], mime=selected_doc.get("content_type") or "application/octet-stream", key=f"admin_employee_doc_download_{selected_doc_id}", use_container_width=True)
                with st.form(f"admin_employee_doc_review_{selected_doc_id}"):
                    document_states = ["submitted", "sent", "read", "reviewed", "needs_information", "archived"]
                    current_doc_status = str(selected_doc.get("status") or "submitted")
                    doc_status = st.selectbox("Document status", document_states, index=document_states.index(current_doc_status) if current_doc_status in document_states else 0)
                    doc_note = st.text_area("Note visible to recipient", value=selected_doc.get("admin_note") or "")
                    save_doc_review = st.form_submit_button("Save document status / note", type="primary")
                if save_doc_review:
                    doc_update = update_employee_document_status(company_id, admin_user_id, selected_doc_id, status=doc_status, admin_note=doc_note)
                    if doc_update.get("status") == "success":
                        st.success(doc_update.get("message", "Document status updated."))
                        st.rerun()
                    st.error(doc_update.get("message", "Document status update failed."))
        else:
            st.info("No employee documents match this filter.")

    with procurement_tab:
        st.subheader("Procurement requests and vendor assignment")
        vendor_form, vendor_list = st.columns([1, 1])
        with vendor_form:
            with st.form("company_vendor_form"):
                vendor_name = st.text_input("Vendor name")
                vendor_rating = st.number_input("Rating", min_value=0.0, max_value=5.0, step=0.1)
                vendor_delivery = st.number_input("Typical delivery days", min_value=1, step=1)
                save_vendor = st.form_submit_button("Save vendor")
            if save_vendor:
                try:
                    upsert_vendor_as_admin(company_id, admin_user_id, vendor_name, vendor_rating, int(vendor_delivery))
                    st.success("Vendor record saved.")
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
        vendors = list_vendors(company_id)
        with vendor_list:
            st.markdown("**Configured company vendors**")
            if vendors:
                st.dataframe(vendors, width="stretch", hide_index=True)
            else:
                st.caption("No vendors are configured.")
        st.divider()
        queue_statuses = ["All"] + sorted({str(row.get("status") or "unknown") for row in list_procurement_queue(company_id, admin_user_id)})
        selected_queue_status = st.selectbox("Request status", queue_statuses)
        purchase_requests = list_procurement_queue(company_id, admin_user_id, status=selected_queue_status)
        if purchase_requests:
            st.dataframe([{"Request": row["request_id"], "Item": row["title"], "Employee": row.get("employee"), "Department": row.get("department"), "Amount": f"{row.get('currency') or ''} {float(row.get('amount') or 0):,.2f}", "Status": row.get("status"), "Vendor": (row.get("details") or {}).get("assigned_vendor", {}).get("name", "Unassigned"), "Updated": row.get("updated_at")} for row in purchase_requests], width="stretch", hide_index=True)
            selected_purchase_id = st.selectbox("Process purchase request", [row["request_id"] for row in purchase_requests])
            selected_purchase = next(row for row in purchase_requests if row["request_id"] == selected_purchase_id)
            purchase_details = selected_purchase.get("details") or {}
            if purchase_details.get("purchase_order_id"):
                st.success(f"Purchase order {purchase_details['purchase_order_id']} was created automatically when this request was approved.")
            if vendors:
                names = [vendor["name"] for vendor in vendors]
                current_vendor = purchase_details.get("assigned_vendor", {}).get("name")
                vendor_choice = st.selectbox("Assign vendor", names, index=names.index(current_vendor) if current_vendor in names else 0)
                if st.button("Assign vendor", key=f"assign_vendor_{selected_purchase_id}"):
                    result = assign_purchase_vendor(company_id, admin_user_id, selected_purchase_id, vendor_choice)
                    if result.get("status") == "success":
                        st.success(result["message"])
                        st.rerun()
                    st.error(result.get("message", "Vendor assignment failed."))
                if not purchase_details.get("purchase_order_id"):
                    can_order = selected_purchase.get("status") in {"approved", "submitted"} and bool(current_vendor)
                    if st.button("Create purchase order", key=f"create_po_{selected_purchase_id}", disabled=not can_order):
                        result = create_purchase_order_from_request(company_id, admin_user_id, str(selected_purchase.get("workflow_id") or ""), selected_purchase_id)
                        if result.get("status") == "success":
                            st.success(result["message"])
                            st.rerun()
                        st.error(result.get("message", "Purchase order could not be created."))
                    if not can_order:
                        st.caption("Approval creates the purchase order automatically. For requests that do not require approval, assign a vendor before creating the order.")
            else:
                st.info("Configure a vendor before processing purchase orders.")
        else:
            st.info("No purchase requests match this status.")

    with hr_desk_tab:
        st.subheader("HR service request queue")
        st.caption("Review submitted HR requests, see the approval state, and track processing. Approval decisions remain in the Pending Approvals section below.")
        hr_search = st.text_input("Search HR requests", placeholder="Request ID, employee, or request type", key="hr_service_search")
        hr_all = list_service_requests_for_admin(company_id, admin_user_id, service_area="HR", search=hr_search)
        hr_statuses = ["All"] + sorted({str(row.get("status") or "unknown") for row in hr_all})
        hr_filter = st.selectbox("HR request status", hr_statuses, key="hr_service_status_filter")
        hr_requests = list_service_requests_for_admin(company_id, admin_user_id, service_area="HR", status=hr_filter, search=hr_search)
        if hr_requests:
            st.dataframe([{
                "Request": row.get("request_id"),
                "Type": row.get("request_type"),
                "Title": row.get("title"),
                "Employee": row.get("employee") or row.get("user_id"),
                "Status": row.get("status"),
                "Approval ID": row.get("approval_id"),
                "Updated": row.get("updated_at"),
            } for row in hr_requests], width="stretch", hide_index=True)
            selected_hr_id = st.selectbox("Open HR request", [row["request_id"] for row in hr_requests], key="hr_service_selected_id")
            selected_hr = next(row for row in hr_requests if row["request_id"] == selected_hr_id)
            st.markdown(f"**{selected_hr.get('title') or selected_hr.get('request_type')}** · `{selected_hr_id}`")
            st.caption(f"Employee: {selected_hr.get('employee') or selected_hr.get('user_id')} · Status: {str(selected_hr.get('status') or '').replace('_', ' ').title()}")
            if selected_hr.get("description"):
                st.write(selected_hr["description"])
            hr_details = selected_hr.get("details") or {}
            if hr_details.get("confidential"):
                st.warning("Confidential HR report: restricted to authorized HR/company administrators in this desk. The current portal does not support anonymous submission.")
            if hr_details.get("needs_external_integration"):
                st.info("This request is recorded for authorized processing. Any external action requires the corresponding integration or authorized manual processing; submission does not claim that action has completed.")
            if selected_hr.get("decision_reason"):
                st.caption(f"Latest processing note: {selected_hr['decision_reason']}")
            current_hr_status = str(selected_hr.get("status") or "submitted").casefold()
            if current_hr_status in {"pending_approval", "needs_clarification"}:
                st.info("This request is waiting for approval or clarification. Use the Pending Approvals controls below; this desk does not bypass that gate.")
            else:
                status_choices = ["submitted", "in_progress", "needs_information", "resolved", "completed", "closed", "cancelled"]
                status_default = current_hr_status if current_hr_status in status_choices else ("in_progress" if current_hr_status == "approved" else "submitted")
                with st.form(f"hr_service_update_{selected_hr_id}"):
                    next_hr_status = st.selectbox("Processing status", status_choices, index=status_choices.index(status_default))
                    hr_comment = st.text_area("Processing note", key=f"hr_service_comment_{selected_hr_id}")
                    save_hr_status = st.form_submit_button("Save HR request update", type="primary")
                if save_hr_status:
                    try:
                        update_result = update_service_request_status_as_admin(company_id, admin_user_id, selected_hr_id, status=next_hr_status, comment=hr_comment)
                        if update_result.get("status") == "success":
                            st.success(update_result["message"])
                            st.rerun()
                        st.error(update_result.get("message", "HR request update failed."))
                    except (ValueError, PermissionError) as exc:
                        st.error(str(exc))
        else:
            st.info("No HR requests match the current filters.")

    with it_desk_tab:
        st.subheader("IT support queue")
        ticket_search = st.text_input("Search tickets", placeholder="Ticket ID, issue, or employee")
        tickets = list_it_tickets(company_id, admin_user_id, search=ticket_search)
        ticket_states = ["All"] + sorted({str(ticket.get("status") or "submitted") for ticket in tickets})
        ticket_filter = st.selectbox("Ticket status", ticket_states)
        tickets = list_it_tickets(company_id, admin_user_id, status=ticket_filter, search=ticket_search)
        if tickets:
            st.dataframe([{"Ticket / Request": item["request_id"], "Issue": item["title"], "Category": (item.get("details") or {}).get("category") or (item.get("details") or {}).get("service_request_type") or item.get("request_type"), "Employee": item.get("employee"), "Department": item.get("department"), "Status": item.get("status"), "Priority": (item.get("details") or {}).get("priority", "normal"), "Updated": item.get("updated_at")} for item in tickets], width="stretch", hide_index=True)
            chosen_id = st.selectbox("Open ticket", [item["request_id"] for item in tickets])
            selected_ticket = next(item for item in tickets if item["request_id"] == chosen_id)
            st.markdown(f"**{selected_ticket['title']}** · {selected_ticket.get('employee') or selected_ticket['user_id']}")
            st.write(selected_ticket.get("description") or "No description was provided.")
            with st.form(f"it_ticket_update_{chosen_id}"):
                current_status = str(selected_ticket.get("status") or "submitted")
                statuses = ["submitted", "open", "in_progress", "needs_information", "resolved", "closed"]
                if current_status in {"pending_approval", "needs_clarification"}:
                    st.info("This request is waiting for approval/clarification. Use the Pending Approvals controls below before processing it.")
                status_value = st.selectbox("Status", statuses, index=statuses.index(current_status) if current_status in statuses else 0)
                priorities = ["low", "normal", "medium", "high", "urgent"]
                current_priority = str((selected_ticket.get("details") or {}).get("priority") or "normal").lower()
                priority_value = st.selectbox("Priority", priorities, index=priorities.index(current_priority) if current_priority in priorities else 1)
                eligible = [row for row in list_company_users(company_id) if row.get("role") in {"company_admin", "it_admin"} and row.get("status") == "active"]
                assignee_ids = [""] + [row["user_id"] for row in eligible]
                current_assignee = str((selected_ticket.get("details") or {}).get("assigned_to") or "")
                assignee = st.selectbox("Assign to", assignee_ids, index=assignee_ids.index(current_assignee) if current_assignee in assignee_ids else 0, format_func=lambda value: "Unassigned" if not value else next((f"{row['name']} · {value}" for row in eligible if row["user_id"] == value), value))
                comment = st.text_area("Add internal update")
                save_ticket = st.form_submit_button(
                    "Save ticket update", type="primary",
                    disabled=current_status in {"pending_approval", "needs_clarification"},
                )
            if save_ticket:
                try:
                    result = update_it_ticket(company_id, admin_user_id, chosen_id, status=status_value, priority=priority_value, assignee_user_id=assignee, comment=comment)
                    if result.get("status") == "success":
                        st.success(result["message"])
                        st.rerun()
                    st.error(result.get("message", "Ticket update failed."))
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
        else:
            st.info("No IT tickets match the current filters.")

    with workflow_tab:
        st.subheader("Workflow execution monitor")
        monitor_col1, monitor_col2 = st.columns([2, 1])
        workflow_search = monitor_col1.text_input("Search workflow, request, or employee")
        all_workflows = list_company_workflows(company_id, admin_user_id, search=workflow_search)
        workflow_statuses = ["All"] + sorted({str(row.get("status") or "unknown") for row in all_workflows})
        workflow_filter = monitor_col2.selectbox("Status", workflow_statuses)
        workflows = list_company_workflows(company_id, admin_user_id, search=workflow_search, status=workflow_filter)
        if workflows:
            st.dataframe([
                {"Workflow": row["workflow_id"], "Request": row["request_text"], "Employee": row.get("employee") or row["user_id"], "Agents": ", ".join(row.get("agents") or []), "Tools": ", ".join(row.get("tools") or []), "Status": row.get("status"), "Updated": row.get("updated_at")}
                for row in workflows
            ], width="stretch", hide_index=True)
            selected_workflow = st.selectbox("Inspect workflow", [row["workflow_id"] for row in workflows], format_func=lambda workflow_id: next((f"{row.get('request_category') or 'Request'} · {row.get('employee') or row['user_id']} · {workflow_id}" for row in workflows if row["workflow_id"] == workflow_id), workflow_id))
            detail = get_company_workflow_details(company_id, admin_user_id, selected_workflow)
            if detail:
                st.markdown(f"**{detail.get('request_text') or 'Workflow request'}**")
                st.caption(f"{detail.get('status', '').replace('_', ' ').title()} · {detail.get('intent') or detail.get('request_category') or 'Unclassified'} · Created {detail.get('created_at', '')}")
                st.write("Agents: " + (", ".join(detail.get("agents") or []) or "No agent recorded"))
                st.write("Tools: " + (", ".join(detail.get("tools") or []) or "No tool recorded"))
                st.json(detail.get("decision") or {})
                st.markdown("**Persisted execution timeline**")
                if detail.get("executions"):
                    for item in detail["executions"]:
                        label = " · ".join(value for value in (item.get("stage"), item.get("agent_key"), item.get("tool_key")) if value)
                        with st.expander(f"{item.get('created_at', '')[:19]} · {label} · {str(item.get('status') or '').title()}"):
                            st.write("Input")
                            st.json(item.get("input") or {})
                            st.write("Output")
                            st.json(item.get("output") or {})
                else:
                    st.info("No execution events were persisted for this workflow.")
                for approval in detail.get("approvals", []):
                    st.caption(f"Approval #{approval.get('approval_id')} · {approval.get('approval_type')} · {approval.get('status')} · {approval.get('reason') or ''}")
        else:
            st.info("No workflow records match the selected filters.")

    with inventory_tab:
        st.subheader("Company laptop and hardware catalog")
        st.caption("Demo laptop models are pre-filled for convenience. Select any existing model to edit its price, stock, specifications, currency, or item type. Changes are saved to the tenant database and used by future purchase requests.")
        if company_id == "demo_company":
            seed_demo_catalog(company_id)
        inventory = list_inventory(company_id)
        if inventory:
            st.dataframe([
                {"Type": row.get("item_type"), "Model": row.get("model"), "Price": f"{row.get('currency') or 'INR'} {float(row.get('unit_price') or 0):,.0f}", "Stock": row.get("quantity_available"), "Key specifications": "; ".join(f"{key.replace('_',' ').title()}: {value}" for key, value in (row.get("specifications") or {}).items())}
                for row in inventory
            ], width="stretch", hide_index=True)
        else:
            st.info("No inventory is configured. Add a company model below.")

        inventory_options = {"➕ Add a new catalog item": None}
        for row in inventory:
            label = f"{row.get('model')} · {row.get('item_type')} · {row.get('currency') or 'INR'} {float(row.get('unit_price') or 0):,.0f} · stock {int(row.get('quantity_available') or 0)}"
            inventory_options[label] = row
        selected_label = st.selectbox("Choose an existing model to edit or add a new one", list(inventory_options.keys()), key="inventory_edit_choice")
        selected_inventory = inventory_options[selected_label]
        default_type = str((selected_inventory or {}).get("item_type") or "laptop")
        default_model = str((selected_inventory or {}).get("model") or "")
        default_price = float((selected_inventory or {}).get("unit_price") or 0)
        default_currency = str((selected_inventory or {}).get("currency") or "INR")
        default_quantity = int((selected_inventory or {}).get("quantity_available") or 0)
        default_specs = json.dumps((selected_inventory or {}).get("specifications") or {}, indent=2, ensure_ascii=False)
        with st.form("company_inventory_item_form"):
            col1, col2 = st.columns(2)
            with col1:
                item_type = st.text_input("Item type", value=default_type, help="Examples: laptop, monitor, keyboard, printer")
                model = st.text_input("Model / product name", value=default_model)
                currency = st.selectbox("Currency", ["INR", "USD", "EUR", "GBP"], index=["INR", "USD", "EUR", "GBP"].index(default_currency) if default_currency in ["INR", "USD", "EUR", "GBP"] else 0)
            with col2:
                unit_price = st.number_input("Unit price", min_value=0.0, value=default_price, step=1000.0)
                quantity = st.number_input("Available quantity", min_value=0, value=default_quantity, step=1)
            specs_json = st.text_area(
                "Complete product specifications (JSON; editable)",
                value=default_specs,
                height=180,
                help="Include processor, RAM, storage, GPU, operating system, warranty, intended use, support, and any internal notes appropriate for the catalog.",
            )
            submitted_inventory = st.form_submit_button("Save / update catalog item", type="primary", use_container_width=True)
        if submitted_inventory:
            try:
                specs = _parse_json_object(specs_json, "Product specifications")
                if not model.strip():
                    raise ValueError("Model / product name is required.")
                if unit_price <= 0:
                    raise ValueError("Unit price must be greater than zero.")
                upsert_inventory_as_admin(company_id, admin_user_id, item_type, model, unit_price, currency, quantity, specs=specs)
                st.success(f"Saved {model.strip()} to the company catalog.")
                st.rerun()
            except Exception as exc:
                st.error(f"Inventory item could not be saved: {exc}")

    # ========================================================
    # COMPANY PROFILE
    # ========================================================

    with profile_tab:

        metadata = (
            context.get(
                "organization_metadata"
            )
            or {}
        )

        with st.form(
            "company_profile_form"
        ):

            name = st.text_input(
                "Company name",
                value=company.get(
                    "name",
                    ""
                ),
            )

            domain = st.text_input(
                "Company domain",
                value=company.get(
                    "domain",
                    ""
                ),
            )

            industry = st.text_input(
                "Industry",
                value=metadata.get(
                    "industry",
                    ""
                ),
            )

            timezone = st.text_input(
                "Timezone",
                value=metadata.get("timezone", "Asia/Kolkata"),
            )
            headquarters = st.text_input(
                "Headquarters / registered office",
                value=metadata.get("headquarters", "Vijayawada, Andhra Pradesh, India"),
            )
            website = st.text_input(
                "Company intranet / website",
                value=metadata.get("website", "https://demo.local"),
            )
            company_description = st.text_area(
                "Company description",
                value=metadata.get("company_description", "Enterprise technology workspace for software delivery and employee services."),
                height=90,
            )
            col_contact1, col_contact2 = st.columns(2)
            with col_contact1:
                hr_contact_email = st.text_input(
                    "HR contact email",
                    value=metadata.get("hr_contact_email", "hr@demo.local"),
                )
                support_phone = st.text_input(
                    "Company / support phone",
                    value=metadata.get("support_phone", "+91 00000 00000 (demo placeholder)"),
                )
            with col_contact2:
                it_support_email = st.text_input(
                    "IT support email",
                    value=metadata.get("it_support_email", "it-support@demo.local"),
                )
            st.caption("Demo defaults are pre-filled for convenience. All values can be edited and saved; replace placeholder contact details before production use.")

            submitted = st.form_submit_button(
                "Save Company Profile",
                type="primary",
            )

        if submitted:

            updated_metadata = dict(
                metadata
            )

            updated_metadata.update(
                {
                    "industry":
                        industry.strip(),

                    "timezone": timezone.strip(),
                    "headquarters": headquarters.strip(),
                    "website": website.strip(),
                    "company_description": company_description.strip(),
                    "hr_contact_email": hr_contact_email.strip(),
                    "it_support_email": it_support_email.strip(),
                    "support_phone": support_phone.strip(),
                }
            )

            try:

                updated = update_company_as_admin(
                    company_id,
                    admin_user_id,
                    name=name,
                    domain=domain,
                    context_updates={
                        "organization_metadata":
                            updated_metadata
                    },
                )

                st.success(
                    "Company profile saved successfully."
                )

                st.caption(
                    "Last updated: "
                    + str(
                        updated.get(
                            "updated_at",
                            "now"
                        )
                    )
                )

                st.rerun()

            except Exception as exc:

                st.error(
                    str(exc)
                )

    # ========================================================
    # ORGANIZATION
    # ========================================================

    with org_tab:

        st.markdown(
            "### Organization structure"
        )

        departments_default = "\n".join(
            context.get(
                "departments"
            )
            or []
        )

        locations_default = "\n".join(
            context.get(
                "locations"
            )
            or []
        )

        with st.form(
            "organization_form"
        ):

            departments = st.text_area(
                "Departments (one per line)",
                value=departments_default,
                height=170,
            )

            locations = st.text_area(
                "Office locations (one per line)",
                value=locations_default,
                height=120,
            )

            submitted = st.form_submit_button(
                "Save Organization",
                type="primary",
            )

        if submitted:

            try:

                updated = update_company_as_admin(
                    company_id,
                    admin_user_id,
                    context_updates={
                        "departments":
                            _lines(departments),

                        "locations":
                            _lines(locations),
                    },
                )

                st.success(
                    "Organization data saved successfully."
                )

                st.caption(
                    "Last updated: "
                    + str(
                        updated.get(
                            "updated_at",
                            "now"
                        )
                    )
                )

                st.rerun()

            except Exception as exc:

                st.error(
                    str(exc)
                )

    # ========================================================
    # ========================================================
    # POLICIES
    # ========================================================

    with policy_tab:

        st.markdown("### Company Policies & Business Rules")

        stored_policy_rows = get_active_policies(company_id)
        st.markdown("#### Versioned workflow policies")
        if stored_policy_rows:
            st.dataframe([{"Policy": row["name"], "Department": row.get("department") or "Company-wide", "Version": f"v{row.get('current_version') or 1}", "Status": row.get("status", "active").title(), "Last updated": row.get("updated_at", "")} for row in stored_policy_rows], width="stretch", hide_index=True)
            for stored_policy in stored_policy_rows:
                with st.expander(f"View {stored_policy['name']} · v{stored_policy.get('current_version', 1)}"):
                    st.json(stored_policy.get("configuration") or {})
        else:
            st.caption("Your editable workflow policies will appear here after the first save.")

        st.caption(
            "Company Admin can change these values directly. "
            "The latest saved values are stored in the company database "
            "and used by enterprise agents and tools."
        )

        current_policies = context.get("policies") or {}

        if not isinstance(current_policies, dict):
            current_policies = {}

        current_leave = current_policies.get("leave") or {}

        if not isinstance(current_leave, dict):
            current_leave = {}

        current_approval_rules = context.get(
            "approval_rules"
        ) or {}

        if not isinstance(current_approval_rules, dict):
            current_approval_rules = {}

        current_benefits = context.get("benefits") or {}

        if not isinstance(current_benefits, dict):
            current_benefits = {}

        # ----------------------------------------------------
        # CURRENT VALUES
        # ----------------------------------------------------

        try:
            current_annual_leave = int(
                current_leave.get(
                    "annual_leave_days",
                    20,
                )
            )
        except (TypeError, ValueError):
            current_annual_leave = 20

        
        current_manager_approval = bool(
            current_leave.get(
                "manager_approval_required",
                True,
            )
        )

        current_count_weekends = bool(
            current_leave.get("count_weekends", False)
        )

        current_holidays = current_leave.get("holidays", [])
        if not isinstance(current_holidays, list):
            current_holidays = []

        current_holiday_text = "\n".join(
            str(item.get("date", "")) if isinstance(item, dict) else str(item)
            for item in current_holidays
        )

        try:
            current_laptop_budget = int(
                current_policies.get(
                    "laptop_budget_inr",
                    0,
                )
            )
        except (TypeError, ValueError):
            current_laptop_budget = 0

        try:
            current_finance_budget = int(
                current_policies.get(
                    "finance_available_budget_inr",
                    0,
                )
            )
        except (TypeError, ValueError):
            current_finance_budget = 0

        try:
            current_purchase_approval = int(
                current_approval_rules.get(
                    "purchase_above_inr",
                    0,
                )
            )
        except (TypeError, ValueError):
            current_purchase_approval = 0

        current_finance_currency = str(
            current_policies.get("finance_currency") or "INR"
        )

        # ----------------------------------------------------
        # LEAVE POLICY
        # ----------------------------------------------------

        st.markdown("#### Leave Policy")

        col1, col2 = st.columns(2)

        with col1:
            annual_leave_days = st.number_input(
                "Annual Leave Days",
                min_value=0,
                value=current_annual_leave,
                step=1,
            )

        with col2:
            manager_approval_required = st.checkbox(
                "Manager Approval Required",
                value=current_manager_approval,
            )

        count_weekends = st.checkbox(
            "Count Saturdays and Sundays as leave days",
            value=current_count_weekends,
            key="leave_count_weekends",
        )

        holiday_text = st.text_area(
            "Company holidays (one date per line, YYYY-MM-DD)",
            value=current_holiday_text,
            help=(
                "Company holidays entered here will be excluded "
                "from leave-day calculation."
            ),
            key="company_leave_holidays",
        )

        configured_leave_types = current_leave.get("leave_types") or ["Annual Leave"]
        if isinstance(configured_leave_types, dict):
            configured_leave_types = list(configured_leave_types)
        if not isinstance(configured_leave_types, list):
            configured_leave_types = ["Annual Leave"]
        leave_type_text = st.text_area(
            "Supported leave types (one per line)",
            value="\n".join(str(value) for value in configured_leave_types),
            help=(
                "Include only leave types approved by your company, e.g. Annual Leave, "
                "Sick Leave, Casual Leave, Maternity Leave, Paternity Leave, or Parental Leave. "
                "The AI validates leave requests against this list."
            ),
            key="company_leave_types",
        )

        # ----------------------------------------------------
        # FINANCE AND PROCUREMENT
        # ----------------------------------------------------

        st.markdown(
            "#### Finance & Procurement Policy"
        )

        col1, col2 = st.columns(2)

        with col1:
            laptop_budget_inr = st.number_input(
                "Laptop Budget per Laptop (INR)",
                min_value=0,
                value=current_laptop_budget,
                step=1000,
            )

        with col2:
            finance_available_budget_inr = st.number_input(
                "Finance Available Budget (INR)",
                min_value=0,
                value=current_finance_budget,
                step=10000,
            )

        finance_currency = st.text_input("Finance currency", value=current_finance_currency, max_chars=3).strip().upper()

        purchase_approval_above_inr = st.number_input(
            "Purchase Approval Above (INR)",
            min_value=0,
            value=current_purchase_approval,
            step=10000,
        )

        st.caption(
            "Laptop Budget = maximum allowed amount per laptop. "
            "Finance Available Budget = currently available Finance funds. "
            "Purchase Approval Above = approval threshold."
        )

        # ----------------------------------------------------
        # BENEFITS
        # ----------------------------------------------------

        st.markdown("#### Additional Benefits")

        benefits_raw = json.dumps(
            current_benefits,
            indent=2,
            ensure_ascii=False,
        )

        benefits = st.text_area(
            "Benefits (JSON)",
            value=benefits_raw,
            height=150,
        )

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        st.markdown("---")

        if st.button(
            "Save Policies",
            type="primary",
            use_container_width=True,
            key="save_company_policies",
        ):

            try:

                parsed_benefits = _parse_json_object(
                    benefits,
                    "Benefits",
                )

                # Preserve existing policy fields.
                updated_policies = dict(
                    current_policies
                )

                # Parse and validate company holiday dates before saving.
                from datetime import date

                parsed_holidays = []
                for line in holiday_text.splitlines():
                    value = line.strip()
                    if not value:
                        continue
                    try:
                        parsed_holidays.append(
                            date.fromisoformat(value).isoformat()
                        )
                    except ValueError as exc:
                        raise ValueError(
                            f"Invalid holiday date: {value}. "
                            "Use YYYY-MM-DD format."
                        ) from exc

                parsed_holidays = sorted(set(parsed_holidays))
                parsed_leave_types = list(dict.fromkeys(_lines(leave_type_text)))
                if not parsed_leave_types:
                    raise ValueError("Configure at least one supported leave type.")

                # Preserve existing leave fields and update editable values.
                updated_leave = dict(current_leave)
                updated_leave["annual_leave_days"] = int(annual_leave_days)
                updated_leave["manager_approval_required"] = bool(
                    manager_approval_required
                )
                updated_leave["count_weekends"] = bool(count_weekends)
                updated_leave["holidays"] = parsed_holidays
                updated_leave["leave_types"] = parsed_leave_types

                updated_policies["leave"] = updated_leave

                # Company laptop policy.
                updated_policies[
                    "laptop_budget_inr"
                ] = int(
                    laptop_budget_inr
                )

                # Current Finance budget.
                updated_policies[
                    "finance_available_budget_inr"
                ] = int(
                    finance_available_budget_inr
                )
                updated_policies["finance_currency"] = finance_currency

                # Preserve existing approval rules.
                updated_approval_rules = dict(
                    current_approval_rules
                )

                updated_approval_rules[
                    "purchase_above_inr"
                ] = int(
                    purchase_approval_above_inr
                )

                # Save to database.
                updated = update_company_as_admin(
                    company_id,
                    admin_user_id,
                    context_updates={
                        "policies": updated_policies,
                        "approval_rules": updated_approval_rules,
                        "benefits": parsed_benefits,
                    },
                )

                # Store versioned policy entities as well as the compatibility
                # context consumed by existing workflow services.
                
                save_policy_configuration(
                    company_id=company_id,
                    user_id=admin_user_id,
                    policy_key="leave_policy",
                    name="Leave Policy",
                    department="HR",
                    category="Leave",
                    configuration={
                        "annual_leave_days": int(annual_leave_days),
                        "manager_approval_required": bool(manager_approval_required),
                        "count_weekends": bool(count_weekends),
                        "holidays": parsed_holidays,
                        "leave_types": parsed_leave_types,
                    },
                )
                save_policy_configuration(company_id=company_id, user_id=admin_user_id, policy_key="laptop_purchase_policy", name="Laptop Purchase Policy", department="IT / Procurement", category="Procurement", configuration={"laptop_budget_inr": int(laptop_budget_inr)})
                save_policy_configuration(company_id=company_id, user_id=admin_user_id, policy_key="purchase_approval_policy", name="Purchase Approval Policy", department="Finance", category="Procurement", configuration={"purchase_above_inr": int(purchase_approval_above_inr)})
                save_policy_configuration(company_id=company_id, user_id=admin_user_id, policy_key="finance_budget_policy", name="Finance Budget Policy", department="Finance", category="Finance", configuration={"finance_available_budget_inr": int(finance_available_budget_inr), "finance_currency": finance_currency})

                st.success(
                    "Company policies saved successfully."
                )

                st.info(
                    "The latest policy values are now stored "
                    "in the company database and will be used "
                    "by future workflows."
                )

                st.caption(
                    "Last updated: "
                    + str(
                        updated.get(
                            "updated_at",
                            "now",
                        )
                    )
                )

                st.rerun()

            except Exception as exc:

                st.error(
                    f"Could not save policies: {exc}"
                )

    with employees_tab:
        # Employee directory is the primary view; existing employee create/edit
        # and activation controls remain below unchanged.
        st.markdown("### Employee directory")
        directory_users = list_company_users(company_id)
        active_departments = sorted({str(row.get("department") or "Unassigned") for row in directory_users})
        directory_col1, directory_col2, directory_col3 = st.columns([2, 1, 1])
        directory_search = directory_col1.text_input("Search employees", placeholder="Name, employee ID, email or designation", key="employee_directory_search")
        directory_department = directory_col2.selectbox("Department", ["All"] + active_departments, key="employee_directory_department")
        directory_statuses = ["All"] + sorted({str(row.get("status") or "unknown").title() for row in directory_users})
        directory_status = directory_col3.selectbox("Employment status", directory_statuses, key="employee_directory_status")
        visible_users = [row for row in directory_users if
            (directory_department == "All" or (row.get("department") or "Unassigned") == directory_department) and
            (directory_status == "All" or str(row.get("status") or "unknown").title() == directory_status) and
            (not directory_search or directory_search.casefold() in " ".join(str(row.get(k) or "") for k in ("name", "employee_id", "email", "department", "role", "designation", "phone")).casefold())]
        if visible_users:
            st.dataframe([{"Employee": row.get("name") or "Unnamed", "Employee ID": row.get("employee_id") or "—", "Department": row.get("department") or "Unassigned", "Designation": row.get("designation") or row.get("role") or "employee", "Work email": row.get("email") or "—", "Phone": row.get("phone") or "—", "Status": row.get("status") or "unknown"} for row in visible_users], width="stretch", hide_index=True)
            selected_directory_id = st.selectbox("Open employee profile", [row["user_id"] for row in visible_users], format_func=lambda uid: next((f"{row.get('name')} · {row.get('employee_id') or uid}" for row in visible_users if row["user_id"] == uid), uid), key="employee_directory_selected")
            selected_employee = next(row for row in visible_users if row["user_id"] == selected_directory_id)
            st.markdown(f"#### {selected_employee.get('name') or 'Employee'}")
            st.caption(f"{selected_employee.get('employee_id') or 'No employee ID'} · {selected_employee.get('department') or 'Unassigned'} · {selected_employee.get('email') or 'No email'} · {str(selected_employee.get('status') or 'unknown').title()}")
            profile_overview, profile_attendance, profile_requests, profile_projects, profile_feedback = st.tabs(["Overview", "Attendance", "Requests & Approvals", "Projects & Submissions", "Performance Feedback"])
            with profile_overview:
                st.write({"Name": selected_employee.get("name"), "Employee ID": selected_employee.get("employee_id"), "Work email": selected_employee.get("email"), "Phone": selected_employee.get("phone") or "Not provided", "Department": selected_employee.get("department"), "Designation": selected_employee.get("designation") or selected_employee.get("role"), "Account status": selected_employee.get("status")})
                st.caption("Use the employee form below to edit account details or deactivate/reactivate this employee.")
            with profile_attendance:
                from datetime import date
                attendance_month = st.selectbox("Month", list(range(1, 13)), index=date.today().month - 1, format_func=lambda m: date(2000, m, 1).strftime("%B"), key=f"attendance_month_{selected_directory_id}")
                attendance_year = st.number_input("Year", min_value=2000, max_value=2100, value=date.today().year, step=1, key=f"attendance_year_{selected_directory_id}")
                st.info("No dedicated attendance-record table/service was found in this project. No attendance entries or totals are fabricated; connect this section to the authoritative attendance source when available.")
            with profile_requests:
                try:
                    employee_requests = list_service_requests_for_admin(company_id, admin_user_id, search=selected_employee.get("email") or selected_employee.get("name") or "")
                    employee_requests = [r for r in employee_requests if str(r.get("user_id") or "") == selected_directory_id]
                except Exception:
                    employee_requests = []
                if employee_requests:
                    st.dataframe([{"Request ID": r.get("request_id"), "Type": r.get("request_type"), "Submitted": r.get("created_at"), "Status": r.get("status"), "Decision": r.get("decision") or r.get("decision_reason"), "Approver": r.get("approver_user_id"), "Updated": r.get("updated_at"), "Details": r.get("description") or r.get("title")} for r in employee_requests], width="stretch", hide_index=True)
                else:
                    st.info("No matching HR/IT service requests are available for this employee in the current request service.")
            with profile_projects:
                try:
                    all_submissions = list_project_submissions_for_admin(company_id, admin_user_id)
                    employee_submissions = [r for r in all_submissions if str(r.get("employee_id") or "") == str(selected_employee.get("employee_id") or "")]
                except Exception:
                    employee_submissions = []
                if employee_submissions:
                    st.dataframe([{"Submission ID": r.get("submission_id"), "Project": r.get("project_name") or r.get("project_id"), "Submitted": r.get("created_at"), "Status": r.get("status"), "Files": r.get("file_count", 0), "Note": r.get("submission_note") or ""} for r in employee_submissions], width="stretch", hide_index=True)
                else:
                    st.info("No submitted projects are recorded for this employee.")
            with profile_feedback:
                from company.employee_portfolio_service import get_performance
                employee_reviews = get_performance(company_id, str(selected_employee.get("employee_id") or ""))
                if employee_reviews:
                    for review in employee_reviews:
                        with st.expander(f"{review.get('review_period')} · Rating {review.get('rating')} · {review.get('status')}"):
                            st.write("Strengths: " + str(review.get("strengths") or "Not recorded"))
                            st.write("Achievements: " + str(review.get("achievements_summary") or "Not recorded"))
                            st.write("Areas for improvement: " + str(review.get("areas_for_improvement") or "Not recorded"))
                            st.write("Goals / development: " + str(review.get("goals") or "Not recorded"))
                            st.write("HR feedback: " + str(review.get("manager_feedback") or "Not recorded"))
                            st.write("Additional comments: " + str(review.get("feedback_comments") or "Not recorded"))
                            st.caption("Reviewer ID: " + str(review.get("reviewer_user_id") or "Not recorded") + " · Submitted: " + str(review.get("created_at") or "Not recorded"))
                else:
                    st.info("No performance feedback is available yet.")
        else:
            st.info("No employees match the current search and filters.")

        st.divider()
        st.markdown("### Add or update employee")

        with st.form(
            "employee_form"
        ):

            col1, col2 = st.columns(
                2
            )

            with col1:

                user_id = st.text_input(
                    "User ID"
                )

                full_name = st.text_input(
                    "Name"
                )

                email = st.text_input(
                    "Work email"
                )

                password = st.text_input(
                    "Password",
                    type="password",
                    help=(
                        "Required for a new account. "
                        "Leave blank when updating an "
                        "existing account without changing "
                        "its password."
                    ),
                )

            with col2:

                role = st.selectbox(
                    "Role",
                    ROLES,
                )

                department_choices = [
                    "(none)"
                ] + list(
                    context.get(
                        "departments"
                    )
                    or []
                )

                department = st.selectbox(
                    "Department",
                    department_choices,
                )

            submitted = st.form_submit_button(
                "Save Employee",
                type="primary",
            )

        if submitted:

            if (
                not user_id.strip()
                or not full_name.strip()
            ):

                st.error(
                    "User ID and Name are required."
                )

            else:

                try:

                    add_or_update_user_as_admin(
                        company_id,
                        admin_user_id,
                        user_id=user_id,
                        name=full_name,
                        email=email,
                        role=role,
                        department=(
                            ""
                            if department == "(none)"
                            else department
                        ),
                        password=password,
                    )

                    st.success(
                        f"Employee '{user_id.strip()}' saved."
                    )

                    st.rerun()

                except Exception as exc:

                    st.error(
                        str(exc)
                    )

        # ----------------------------------------------------
        # USER TABLE
        # ----------------------------------------------------

        st.markdown(
            "### Current company users"
        )

        users = list_company_users(
            company_id
        )

        if users:

            st.dataframe(
                users,
                width="stretch",
                hide_index=True,
            )

        else:

            st.info(
                "No company users found."
            )

        # ----------------------------------------------------
        # ACTIVATE / DEACTIVATE
        # ----------------------------------------------------

        if users:

            active_user_ids = [
                user["user_id"]
                for user in users
            ]

            selected = st.selectbox(
                "Select user",
                active_user_ids,
                key="selected_user_status",
            )

            selected_user = next(
                user
                for user in users
                if user["user_id"] == selected
            )

            new_status = (
                "inactive"
                if selected_user.get(
                    "status"
                ) == "active"
                else "active"
            )

            action_label = (
                "Deactivate user"
                if new_status == "inactive"
                else "Reactivate user"
            )

            if st.button(
                action_label,
                key="toggle_user_status",
            ):

                try:

                    change_user_status_as_admin(
                        company_id,
                        admin_user_id,
                        selected,
                        new_status,
                    )

                    st.success(
                        f"{selected} is now {new_status}."
                    )

                    st.rerun()

                except Exception as exc:

                    st.error(
                        str(exc)
                    )

    # ========================================================
    # PERMISSIONS
    # ========================================================

    with documents_tab:

        st.markdown(
            "### Company Knowledge Documents"
        )

        st.caption(
            "Upload company documents that can be searched by "
            "the Knowledge Agent. Documents are isolated by company "
            "and indexed into searchable knowledge chunks."
        )

        with st.form(
            "knowledge_document_upload_form"
        ):

            uploaded_file = st.file_uploader(
                "Choose a document",
                type=[
                    "pdf",
                    "txt",
                    "md",
                    "csv",
                    "json",
                ],
                help=(
                    "Supported formats: PDF, TXT, MD, CSV and JSON."
                ),
            )

            col1, col2 = st.columns(2)

            with col1:

                document_title = st.text_input(
                    "Document title",
                    placeholder="Example: Employee Handbook",
                )

                document_category = st.text_input(
                    "Category",
                    placeholder="Example: HR Policy",
                )

            with col2:

                document_department = st.selectbox(
                    "Department",
                    ["Company-wide"]
                    + list(
                        context.get(
                            "departments"
                        )
                        or []
                    ),
                )

                document_visibility = st.selectbox(
                    "Visibility",
                    [
                        "company",
                        "department",
                        "private",
                    ],
                    index=0,
                )

            upload_submitted = st.form_submit_button(
                "Upload Knowledge Document",
                type="primary",
            )

        if upload_submitted:

            if uploaded_file is None:

                st.error(
                    "Please choose a document to upload."
                )

            else:

                try:

                    selected_department = (
                        ""
                        if document_department == "Company-wide"
                        else document_department
                    )

                    result = ingest_document(
                        company_id=company_id,
                        uploaded_by=admin_user_id,
                        title=(
                            document_title.strip()
                            or uploaded_file.name
                        ),
                        filename=uploaded_file.name,
                        data=uploaded_file.getvalue(),
                        category=document_category.strip(),
                        department=selected_department,
                        visibility=document_visibility,
                    )

                    if result.get("status") == "success":

                        st.success(
                            result.get(
                                "message",
                                "Document uploaded successfully.",
                            )
                        )

                        st.info(
                            f"Document ID: "
                            f"{result.get('document_id')} | "
                            f"Knowledge chunks: "
                            f"{result.get('chunk_count')}"
                        )

                        st.rerun()

                    else:

                        st.error(
                            result.get(
                                "message",
                                "Document upload failed.",
                            )
                        )

                except Exception as exc:

                    st.error(
                        f"Could not upload document: {exc}"
                    )

        # ----------------------------------------------------
        # STORED DOCUMENTS
        # ----------------------------------------------------

        st.markdown(
            "### Stored Knowledge Documents"
        )

        documents = list_documents(
              company_id, admin_user_id
        )

        if documents:

            st.dataframe(
                documents,
                width="stretch",
                hide_index=True,
            )

        else:

            st.info(
                "No company knowledge documents have been uploaded yet."
            )


    # ========================================================
    # IMPORTANT LINKS & UPDATES
    # ========================================================

    with updates_tab:

        st.markdown("### Shared company links")
        st.caption("Publish tenant-owned links with employee, department, or role visibility.")
        with st.form("shared_company_link_form"):
            resource_title = st.text_input("Link title", key="resource_title")
            resource_url = st.text_input("Destination URL", placeholder="https://...")
            resource_description = st.text_area("Description", key="resource_description")
            resource_category = st.text_input("Category", key="resource_category")
            resource_audience = st.selectbox("Who can access this link?", ["all", "employees", "department", "role"], format_func=lambda value: {"all":"Everyone in the company", "employees":"Employees", "department":"Specific department", "role":"Specific role"}[value])
            resource_target = st.text_input("Department or role (when selected above)") if resource_audience in {"department", "role"} else ""
            resource_priority = st.selectbox("Priority", ["medium", "high", "low"], key="resource_priority")
            resource_expires = st.text_input("Expiry date/time (ISO 8601, optional)", key="resource_expires")
            resource_submitted = st.form_submit_button("Save company link", type="primary")
        if resource_submitted:
            try:
                result = create_resource(company_id=company_id, user_id=admin_user_id, title=resource_title, url=resource_url, description=resource_description, category=resource_category, audience=resource_audience, department=resource_target, priority=resource_priority, expires_at=resource_expires)
                st.success(result["message"])
                st.rerun()
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
            except Exception:
                st.error("Company link could not be saved. Verify the destination and try again.")
        admin_resources = list_resources(company_id, admin_user_id, include_inactive=True)
        if admin_resources:
            for resource in admin_resources:
                with st.container(border=True):
                    st.markdown(f"**{resource['title']}** · {resource['status'].title()} · {resource['audience'].title()}")
                    st.caption(f"{resource.get('category') or 'Company link'} · {resource.get('department') or 'Company-wide'}")
                    st.write(resource.get("description") or "")
                    st.markdown(f"[Open destination]({resource['url']})")
                    if resource["status"] == "active" and st.button("Archive link", key=f"archive_resource_{resource['resource_id']}"):
                        result = archive_resource(company_id, admin_user_id, int(resource["resource_id"]))
                        st.success(result["message"])
                        st.rerun()

        st.divider()

        st.markdown(
            "### Important Links & Updates"
        )

        st.caption(
            "Publish important company announcements, useful links, "
            "deadlines and employee updates. These records are "
            "stored per company and can be searched by the "
            "enterprise assistant."
        )

        with st.form(
            "company_update_form"
        ):

            update_title = st.text_input(
                "Title",
                placeholder="Example: Annual Benefits Enrollment",
            )

            update_description = st.text_area(
                "Description",
                placeholder=(
                    "Describe the announcement, update or information."
                ),
                height=120,
            )

            update_link = st.text_input(
                "Useful link (optional)",
                placeholder="https://...",
            )

            col1, col2, col3 = st.columns(3)

            with col1:

                update_category = st.text_input(
                    "Category",
                    placeholder="Benefits",
                )

            with col2:

                update_priority = st.selectbox(
                    "Priority",
                    [
                        "high",
                        "normal",
                        "low",
                    ],
                    index=1,
                )

            with col3:

                update_audience = st.selectbox(
                    "Audience",
                    [
                        "company",
                        "employees",
                        "hr",
                        "it",
                        "finance",
                        "procurement",
                        "recruitment",
                        "department",
                    ],
                    index=0,
                )

            departments = context.get("departments") or []
            update_department = st.selectbox("Department (for department audience)", [""] + [str(value) for value in departments])
            update_status = st.selectbox("Publication", ["active", "scheduled", "draft"], help="Scheduled posts publish automatically when their effective date arrives and an employee opens the portal.")
            update_effective = st.text_input("Effective date/time (ISO 8601, optional)", placeholder="2026-10-15T09:00:00+05:30")
            update_expires = st.text_input("Expiry date/time (ISO 8601, optional)", placeholder="2026-10-31T23:59:00+05:30")

            update_submitted = st.form_submit_button(
                "Publish Update",
                type="primary",
            )

        if update_submitted:

            if not update_title.strip():

                st.error(
                    "Title is required."
                )

            elif not update_description.strip():

                st.error(
                    "Description is required."
                )

            else:

                try:

                    result = create_update(
                        company_id=company_id,
                        posted_by=admin_user_id,
                        title=update_title,
                        description=update_description,
                        link_url=update_link,
                        category=update_category,
                        priority=update_priority,
                        audience=update_audience,
                        department=update_department,
                        published_at=update_effective or None,
                        expires_at=update_expires or None,
                        status=update_status,
                    )

                    if result.get("status") == "success":

                        st.success(
                            result.get(
                                "message",
                                "Update published successfully.",
                            )
                        )

                        st.rerun()

                    else:

                        st.error(
                            result.get(
                                "message",
                                "Could not publish update.",
                            )
                        )

                except Exception as exc:

                    st.error(
                        f"Could not publish update: {exc}"
                    )

        # ----------------------------------------------------
        # STORED UPDATES
        # ----------------------------------------------------

        st.markdown(
            "### Published Company Updates"
        )

        updates = list_updates(company_id, user_id=admin_user_id, include_expired=True, include_inactive=True)

        if updates:
            for update in updates:
                with st.expander(f"{update['title']} · {str(update['status']).title()} · {update.get('priority', 'normal').title()}"):
                    st.caption(f"Audience: {update.get('audience')} {('· ' + update.get('department')) if update.get('department') else ''} · Effective: {update.get('published_at') or 'Now'} · Expires: {update.get('expires_at') or 'Never'}")
                    st.write(update.get("description") or "")
                    if update.get("link_url"):
                        st.markdown(f"[Open link]({update['link_url']})")
                    with st.form(f"edit_update_{update['update_id']}"):
                        title_edit = st.text_input("Title", value=update.get("title", ""))
                        desc_edit = st.text_area("Description", value=update.get("description", ""))
                        link_edit = st.text_input("Useful link", value=update.get("link_url", ""))
                        category_edit = st.text_input("Category", value=update.get("category", ""))
                        priority_edit = st.selectbox("Priority", ["high", "normal", "low"], index=["high", "normal", "low"].index(str(update.get("priority") or "normal").lower()), key=f"update_priority_{update['update_id']}")
                        audience_values = ["company", "employees", "hr", "it", "finance", "procurement", "recruitment", "department"]
                        current_audience = str(update.get("audience") or "company").lower()
                        audience_edit = st.selectbox("Audience", audience_values, index=audience_values.index(current_audience) if current_audience in audience_values else 0, key=f"update_audience_{update['update_id']}")
                        department_values = [""] + [str(value) for value in (context.get("departments") or [])]
                        current_department = str(update.get("department") or "")
                        department_edit = st.selectbox("Department", department_values, index=department_values.index(current_department) if current_department in department_values else 0, key=f"update_department_{update['update_id']}")
                        status_values = ["active", "scheduled", "draft"]
                        current_status = str(update.get("status") or "active").lower()
                        status_edit = st.selectbox("Publication", status_values, index=status_values.index(current_status) if current_status in status_values else 0, key=f"update_status_{update['update_id']}")
                        publish_edit = st.text_input("Effective date/time", value=update.get("published_at") or "")
                        expiry_edit = st.text_input("Expiry date/time", value=update.get("expires_at") or "")
                        update_action = st.form_submit_button("Save changes")
                    if update_action:
                        result = update_company_update(company_id=company_id, user_id=admin_user_id, update_id=int(update["update_id"]), fields={"title": title_edit, "description": desc_edit, "link_url": link_edit, "category": category_edit, "priority": priority_edit, "audience": audience_edit, "department": department_edit, "status": status_edit, "published_at": publish_edit or None, "expires_at": expiry_edit or None})
                        if result.get("status") == "success":
                            st.success(result["message"])
                            st.rerun()
                        else:
                            st.error(result.get("message", "Update could not be saved."))
                    if update.get("status") != "archived" and st.button("Archive announcement", key=f"archive_update_{update['update_id']}"):
                        result = archive_update(company_id=company_id, user_id=admin_user_id, update_id=int(update["update_id"]))
                        if result.get("status") == "success":
                            st.success(result["message"])
                            st.rerun()
                        else:
                            st.error(result.get("message", "Announcement could not be archived."))

        else:

            st.info(
                "No company updates or links have been published yet."
            )


    # ========================================================
    # PENDING APPROVALS
    # ========================================================

    st.markdown("---")
    st.markdown("## Pending Approvals")

    pending_approvals = list_pending_approvals(
        company_id=company_id
    )

    if not pending_approvals:

        st.info(
            "There are no pending approvals for this company."
        )

    else:

        st.caption(
            f"{len(pending_approvals)} approval(s) waiting for review."
        )

        for approval in pending_approvals:

            approval_id = approval.get(
                "approval_id"
            )

            metadata = approval.get(
                "metadata",
                {}
            )

            amount_inr = metadata.get(
                "amount_inr"
            )

            request_text = metadata.get(
                "request",
                approval.get(
                    "reason",
                    ""
                ),
            )

            st.markdown(
                f"### Approval #{approval_id}"
            )

            col1, col2 = st.columns(2)

            with col1:

                st.write(
                    f"**Requested by:** "
                    f"{approval.get('requested_by', '')}"
                )

                st.write(
                    f"**Approval type:** "
                    f"{approval.get('approval_type', '')}"
                )

                st.write(
                    f"**Department:** "
                    f"{metadata.get('department', '')}"
                )

            with col2:

                if amount_inr is not None:

                    st.write(
                        f"**Amount:** "
                        f"?{float(amount_inr):,.0f}"
                    )

                st.write(
                    f"**Requested at:** "
                    f"{approval.get('requested_at', '')}"
                )

                st.write(
                    f"**Status:** "
                    f"{approval.get('status', '')}"
                )

            st.write(
                f"**Request:** {request_text}"
            )

            decision_reason = st.text_input(
                "Decision reason",
                key=f"approval_reason_{approval_id}",
                placeholder="Enter approval/rejection reason",
            )

            approve_col, reject_col = st.columns(2)

            with approve_col:

                if st.button(
                    "Approve",
                    key=f"approve_{approval_id}",
                    type="primary",
                ):

                    try:

                        result = approve_request(
                            company_id=company_id,
                            approval_id=int(approval_id),
                            approver_user_id=admin_user_id,
                            reason=decision_reason.strip(),
                        )

                        if result:

                            st.success(
                                f"Approval #{approval_id} approved."
                            )

                        else:

                            st.error(
                                f"Approval #{approval_id} "
                                "could not be approved."
                            )

                        st.rerun()

                    except Exception as exc:

                        st.error(
                            str(exc)
                        )

            with reject_col:

                if st.button(
                    "Reject",
                    key=f"reject_{approval_id}",
                ):

                    try:

                        result = reject_request(
                            company_id=company_id,
                            approval_id=int(approval_id),
                            approver_user_id=admin_user_id,
                            reason=decision_reason.strip(),
                        )

                        if result:

                            st.warning(
                                f"Approval #{approval_id} rejected."
                            )

                        else:

                            st.error(
                                f"Approval #{approval_id} "
                                "could not be rejected."
                            )

                        st.rerun()

                    except Exception as exc:

                        st.error(
                            str(exc)
                        )

            st.markdown("---")


    # ========================================================
    # PERFORMANCE MANAGEMENT
    # ========================================================
    with performance_tab:
        st.markdown("### Employee performance reviews")
        st.caption(
            "Create and publish a review for an employee in this company. "
            "Published reviews are stored in the company database."
        )

        company_users = list_company_users(company_id)
        employees = [
            u for u in company_users
            if u.get("employee_id")
            and str(u.get("status", "active")).lower() == "active"
            and str(u.get("role", "")).lower()
                not in {"company_admin", "hr_admin", "admin"}
        ]

        if not employees:
            st.info(
                "No active employee accounts with employee IDs were found. "
                "Check the Employees tab first."
            )
        else:
            labels = {
                f"{u.get('name', 'Employee')} ? {u.get('email', '')} "
                f"({u.get('employee_id')})": u
                for u in employees
            }

            with st.form("create_employee_performance_form"):
                selected_label = st.selectbox(
                    "Employee",
                    list(labels.keys()),
                )
                review_period = st.text_input(
                    "Review period",
                    placeholder="e.g. Q3 2026 or July?September 2026",
                )
                rating = st.slider(
                    "Overall rating (1?5)",
                    min_value=1.0,
                    max_value=5.0,
                    value=3.0,
                    step=0.5,
                )
                strengths = st.text_area("Strengths")
                goals = st.text_area("Goals / development recommendations")
                areas_for_improvement = st.text_area("Areas for improvement")
                achievements = st.text_area("Achievements summary")
                feedback = st.text_area("Manager feedback")
                feedback_comments = st.text_area("Additional feedback comments")
                publish = st.form_submit_button(
                    "Publish review and notify employee",
                    type="primary",
                )

            if publish:
                employee = labels[selected_label]
                if not review_period.strip():
                    st.error("Enter the review period before publishing.")
                else:
                    try:
                        saved = create_performance(
                            company_id=company_id,
                            employee_id=str(employee["employee_id"]),
                            review_period=review_period.strip(),
                            rating=rating,
                            goals=goals,
                            achievements_summary=achievements,
                            manager_feedback=feedback,
                            status="completed",
                            strengths=strengths,
                            areas_for_improvement=areas_for_improvement,
                            reviewer_user_id=admin_user_id,
                            feedback_comments=feedback_comments,
                        )

                        # Create an in-app notification for the actual user.
                        with sqlite3.connect(str(PORTFOLIO_DB_PATH)) as conn:
                            conn.execute(
                                """
                                INSERT INTO notifications
                                (company_id, user_id, workflow_id,
                                 notification_type, title, body,
                                 resource_type, resource_id, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    company_id,
                                    employee["user_id"],
                                    "",
                                    "performance_review_published",
                                    "Performance review published",
                                    f"Your performance review for "
                                    f"{review_period.strip()} is available "
                                    f"in your employee portfolio.",
                                    "employee_performance",
                                    str(saved["performance_id"]),
                                    datetime.now().astimezone().isoformat(),
                                ),
                            )

                        st.success(
                            f"Review saved and employee notified. "
                            f"Review ID: {saved['performance_id']}"
                        )
                    except Exception as exc:
                        st.error(f"Could not publish the review: {exc}")

        st.divider()
        st.markdown("#### Existing reviews")
        try:
            from company.employee_portfolio_service import get_performance
            from datetime import timezone

            review_employees = {
                str(u["employee_id"]): u for u in employees
            }
            found_reviews = []
            for employee_id, employee in review_employees.items():
                for review in get_performance(company_id, employee_id):
                    item = dict(review)
                    item["Employee"] = employee.get("name", employee_id)
                    found_reviews.append(item)

            if not found_reviews:
                st.info("No performance reviews have been recorded yet.")

            for review in found_reviews:
                rid = int(review["performance_id"])
                employee_id = str(review["employee_id"])

                with st.container(border=True):
                    st.markdown(
                        f"**{review['Employee']}** ? "
                        f"Review #{rid}"
                    )
                    st.caption(
                        f"{review.get('review_period', '')} ? "
                        f"Rating: {review.get('rating', 0)}/5 ? "
                        f"Status: {review.get('status', '')}"
                    )

                    with st.expander("View / edit review", expanded=False):
                        st.write(
                            "Employee ID:", employee_id
                        )
                        with st.form(f"edit_performance_{rid}"):
                            new_period = st.text_input(
                                "Review period",
                                value=review.get("review_period", ""),
                                key=f"period_{rid}",
                            )
                            new_rating = st.slider(
                                "Rating (1?5)",
                                min_value=1.0,
                                max_value=5.0,
                                value=float(review.get("rating") or 3.0),
                                step=0.5,
                                key=f"rating_{rid}",
                            )
                            new_goals = st.text_area(
                                "Goals / improvement areas",
                                value=review.get("goals", ""),
                                key=f"goals_{rid}",
                            )
                            new_achievements = st.text_area(
                                "Achievements summary",
                                value=review.get("achievements_summary", ""),
                                key=f"achievements_{rid}",
                            )
                            new_feedback = st.text_area(
                                "Manager feedback",
                                value=review.get("manager_feedback", ""),
                                key=f"feedback_{rid}",
                            )
                            save_edit = st.form_submit_button(
                                "Save review changes",
                                type="primary",
                            )

                        if save_edit:
                            if not new_period.strip():
                                st.error("Review period is required.")
                            else:
                                try:
                                    with sqlite3.connect(
                                        str(PORTFOLIO_DB_PATH)
                                    ) as conn:
                                        cursor = conn.execute(
                                            """
                                            UPDATE employee_performance
                                            SET review_period = ?,
                                                rating = ?,
                                                goals = ?,
                                                achievements_summary = ?,
                                                manager_feedback = ?,
                                                updated_at = ?
                                            WHERE performance_id = ?
                                              AND company_id = ?
                                              AND employee_id = ?
                                            """,
                                            (
                                                new_period.strip(),
                                                float(new_rating),
                                                new_goals.strip(),
                                                new_achievements.strip(),
                                                new_feedback.strip(),
                                                datetime.now(timezone.utc).isoformat(),
                                                rid,
                                                company_id,
                                                employee_id,
                                            ),
                                        )
                                        if cursor.rowcount != 1:
                                            raise RuntimeError(
                                                "Review not found or access mismatch."
                                            )
                                    st.success("Review updated successfully.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Update failed: {exc}")

                    with st.expander("Delete review", expanded=False):
                        st.warning(
                            "This permanently deletes this review and its "
                            "linked in-app notification."
                        )
                        confirmed = st.checkbox(
                            "I confirm deleting this review",
                            key=f"confirm_delete_performance_{rid}",
                        )
                        if st.button(
                            "Delete this review",
                            key=f"delete_performance_{rid}",
                            type="secondary",
                            disabled=not confirmed,
                        ):
                            try:
                                with sqlite3.connect(
                                    str(PORTFOLIO_DB_PATH)
                                ) as conn:
                                    conn.execute("BEGIN IMMEDIATE")
                                    cursor = conn.execute(
                                        """
                                        DELETE FROM employee_performance
                                        WHERE performance_id = ?
                                          AND company_id = ?
                                          AND employee_id = ?
                                        """,
                                        (rid, company_id, employee_id),
                                    )
                                    if cursor.rowcount != 1:
                                        raise RuntimeError(
                                            "Review not found or access mismatch."
                                        )
                                    conn.execute(
                                        """
                                        DELETE FROM notifications
                                        WHERE company_id = ?
                                          AND resource_type = ?
                                          AND resource_id = ?
                                        """,
                                        (
                                            company_id,
                                            "employee_performance",
                                            str(rid),
                                        ),
                                    )
                                    conn.commit()
                                st.success(f"Review #{rid} deleted.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Delete failed: {exc}")

        except Exception as exc:
            st.warning(f"Could not load existing reviews: {exc}")

