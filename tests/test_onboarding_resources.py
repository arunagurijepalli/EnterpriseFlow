"""Regression coverage for workspace onboarding and company links."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch

_test_db = tempfile.NamedTemporaryFile(prefix="enterpriseflow-tests-", suffix=".db", delete=False)
_test_db.close()
os.environ["COMPANY_DB_PATH"] = _test_db.name

from company.auth import authenticate_user
from company.audit_service import list_audit_events
from company.agent_registry_service import list_agent_runtime_status
from company.approval_service import approve_request, create_approval, get_approval, reject_request, request_approval_clarification, respond_to_approval_clarification
from company.catalog_service import upsert_inventory_as_admin, upsert_vendor_as_admin
from company.memory_service import save_workflow_execution, save_workflow_request
from company.operations_service import list_it_tickets, update_it_ticket
from company.policy_service import get_active_policies, save_policy_configuration
from company.onboarding_service import create_company_workspace
from company.outbound_email import list_email_deliveries, send_admin_test_email
from company.leave_service import get_leave_summary
from company.resource_service import archive_resource, create_resource, list_resources
from company.request_service import create_department_request, create_purchase_order_from_request, get_my_department_request
from company.store import add_company_user, authorize_user, get_company_context
from company.workflow_monitor_service import get_company_workflow_details, list_company_workflows
from tools.it_tools import create_ticket
from company.approval_service import list_pending_approvals
from company.request_service import list_my_department_requests
from core.workflow import run_workflow, resume_workflow, cancel_pending_workflow
from core.pending_confirmation import classify_pending_confirmation_reply, hold_pending_confirmation_result
from core.llm import local_fallback_analyze

# unittest discovery imports sibling test modules before executing test methods.
# An earlier module may already have imported company services while reading the
# local .env, so setting COMPANY_DB_PATH alone is not sufficient. Rebind every
# imported service module's cached DB_PATH to this isolated test database before
# any tests execute. This prevents automated tests from reading or mutating a
# developer's real company database.
_TEST_DB_PATH = Path(_test_db.name).resolve()
for _module_name, _module in list(sys.modules.items()):
    if not (_module_name.startswith("company.") or _module_name.startswith("tools.")):
        continue
    if hasattr(_module, "DB_PATH"):
        try:
            _module.DB_PATH = _TEST_DB_PATH
        except Exception:
            pass
    if hasattr(_module, "CONFIGURED_DB_PATH"):
        try:
            _module.CONFIGURED_DB_PATH = _TEST_DB_PATH
        except Exception:
            pass


class WorkspaceOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.company_id = f"tenant_{uuid.uuid4().hex[:10]}"
        self.email = f"admin-{uuid.uuid4().hex[:8]}@example.test"

    def test_company_signup_creates_tenant_admin_and_scoped_defaults(self):
        created = create_company_workspace(
            company_id=self.company_id,
            company_name="Test Company",
            admin_name="Tenant Admin",
            admin_email=self.email,
            password="ValidPass123",
        )
        user = authenticate_user(self.company_id, self.email, "ValidPass123")
        self.assertEqual(user["user_id"], created["user_id"])
        self.assertEqual(user["role"], "company_admin")
        self.assertEqual(user["company_id"], self.company_id)
        context = get_company_context(self.company_id)
        self.assertIn("IT", context["departments"])
        self.assertEqual(authorize_user(self.company_id, created["user_id"])["role"], "company_admin")
        self.assertTrue(any(event["action"] == "company_workspace_created" for event in list_audit_events(self.company_id, created["user_id"])))
        with self.assertRaises(PermissionError):
            authenticate_user(self.company_id, self.email, "wrong-password")

    def test_signup_generates_company_id_and_persists_business_profile(self):
        created = create_company_workspace(
            company_name="Northwind Research Group", admin_name="Workspace Admin",
            admin_email=self.email, password="ValidPass123", company_domain="northwind.example",
            industry="Research", location="Bengaluru", timezone_name="Asia/Kolkata",
        )
        self.assertTrue(created["company_id"].startswith("northwind-research-group-"))
        context = get_company_context(created["company_id"])
        self.assertEqual(context["organization_metadata"]["industry"], "Research")
        self.assertEqual(context["organization_metadata"]["location"], "Bengaluru")
        self.assertEqual(context["organization_metadata"]["timezone"], "Asia/Kolkata")

    def test_unconfigured_test_email_is_not_claimed_sent_and_is_logged(self):
        created = create_company_workspace(company_id=self.company_id, company_name="Email Co",
                                           admin_name="Admin", admin_email=self.email,
                                           password="ValidPass123")
        with patch.dict(os.environ, {"SMTP_HOST": "", "SMTP_PORT": "", "SMTP_FROM_EMAIL": "", "SMTP_USERNAME": "", "SMTP_PASSWORD": ""}):
            result = send_admin_test_email(self.company_id, created["user_id"])
        self.assertEqual(result["status"], "not_configured")
        self.assertIn("not configured", result["message"])
        records = list_email_deliveries(self.company_id, created["user_id"])
        self.assertEqual(records[0]["status"], "not_configured")
        self.assertEqual(records[0]["event_type"], "test_email")

    def test_company_link_access_is_tenant_and_audience_scoped(self):
        workspace = create_company_workspace(
            company_id=self.company_id,
            company_name="Test Company",
            admin_name="Tenant Admin",
            admin_email=self.email,
            password="ValidPass123",
        )
        add_company_user("employee_" + self.company_id, self.company_id, "IT Employee", "employee@example.test", department="IT")
        add_company_user("other_" + self.company_id, self.company_id, "HR Employee", "hr@example.test", department="HR")
        with self.assertRaises(PermissionError):
            list_audit_events(self.company_id, "employee_" + self.company_id)
        link = create_resource(
            company_id=self.company_id,
            user_id=workspace["user_id"],
            title="IT Helpdesk",
            url="https://support.example.test",
            audience="department",
            department="IT",
        )
        self.assertEqual(len(list_resources(self.company_id, "employee_" + self.company_id)), 1)
        self.assertEqual(list_resources(self.company_id, "other_" + self.company_id), [])
        other_company = create_company_workspace(
            company_id=f"other_{uuid.uuid4().hex[:10]}",
            company_name="Other Company",
            admin_name="Other Admin",
            admin_email=f"other-{uuid.uuid4().hex[:8]}@example.test",
            password="ValidPass123",
        )
        self.assertEqual(list_resources(other_company["company_id"], other_company["user_id"]), [])
        with self.assertRaises(PermissionError):
            create_resource(company_id=self.company_id, user_id="employee_" + self.company_id,
                            title="Unauthorized", url="https://example.test")
        self.assertEqual(archive_resource(self.company_id, workspace["user_id"], link["resource_id"])["status"], "success")
        self.assertEqual(list_resources(self.company_id, "employee_" + self.company_id), [])

    def test_invalid_link_and_duplicate_workspace_are_rejected(self):
        created = create_company_workspace(
            company_id=self.company_id,
            company_name="Test Company",
            admin_name="Tenant Admin",
            admin_email=self.email,
            password="ValidPass123",
        )
        with self.assertRaises(ValueError):
            create_resource(company_id=self.company_id, user_id=created["user_id"],
                            title="Bad link", url="javascript:alert(1)")
        with self.assertRaises(ValueError):
            create_company_workspace(company_id=self.company_id, company_name="Duplicate",
                                     admin_name="Other", admin_email="other@example.test",
                                     password="ValidPass123")

    def test_department_approval_updates_request_and_rejects_self_approval(self):
        workspace = create_company_workspace(
            company_id=self.company_id,
            company_name="Test Company",
            admin_name="Tenant Admin",
            admin_email=self.email,
            password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        request = create_department_request(
            company_id=self.company_id,
            user_id=employee_id,
            workflow_id="wf-approve-" + self.company_id,
            service_area="IT",
            request_type="support_request",
            title="Connectivity issue",
            requires_approval=True,
        )
        approval = create_approval(
            company_id=self.company_id,
            workflow_id=request["workflow_id"],
            requested_by=employee_id,
            approval_type="it_request",
            metadata={"request_id": request["request_id"], "service_area": "IT"},
        )
        with self.assertRaises(PermissionError):
            approve_request(self.company_id, approval["approval_id"], employee_id)
        decided = approve_request(self.company_id, approval["approval_id"], workspace["user_id"], "Reviewed")
        self.assertEqual(decided["status"], "approved")
        self.assertEqual(get_my_department_request(self.company_id, employee_id, request["request_id"])["status"], "approved")

        reject_request_id = create_department_request(
            company_id=self.company_id,
            user_id=employee_id,
            workflow_id="wf-reject-" + self.company_id,
            service_area="IT",
            request_type="support_request",
            title="Second issue",
            requires_approval=True,
        )
        rejected_approval = create_approval(
            company_id=self.company_id,
            workflow_id=reject_request_id["workflow_id"],
            requested_by=employee_id,
            approval_type="it_request",
            metadata={"request_id": reject_request_id["request_id"], "service_area": "IT"},
        )
        rejected = reject_request(self.company_id, rejected_approval["approval_id"], workspace["user_id"], "Not required")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(get_my_department_request(self.company_id, employee_id, reject_request_id["request_id"])["status"], "rejected")

    def test_policy_versions_update_executable_company_context(self):
        workspace = create_company_workspace(company_id=self.company_id, company_name="Policy Co", admin_name="Admin", admin_email=self.email, password="ValidPass123")
        first = save_policy_configuration(company_id=self.company_id, user_id=workspace["user_id"], policy_key="finance_budget_policy", name="Finance budget", department="Finance", category="Budget", configuration={"finance_available_budget_inr": 500000, "finance_currency": "INR"})
        second = save_policy_configuration(company_id=self.company_id, user_id=workspace["user_id"], policy_key="finance_budget_policy", name="Finance budget", department="Finance", category="Budget", configuration={"finance_available_budget_inr": 750000, "finance_currency": "INR"})
        self.assertEqual((first["version"], second["version"]), (1, 2))
        self.assertEqual(get_company_context(self.company_id)["policies"]["finance_available_budget_inr"], 750000)
        policy = next(item for item in get_active_policies(self.company_id) if item["policy_key"] == "finance_budget_policy")
        self.assertEqual(policy["current_version"], 2)
        self.assertEqual(policy["configuration"]["finance_currency"], "INR")

    def test_natural_language_leave_is_approved_and_balance_is_updated(self):
        workspace = create_company_workspace(company_id=self.company_id, company_name="Leave Co", admin_name="Admin", admin_email=self.email, password="ValidPass123")
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            workflow = run_workflow("I want to apply for leave from October 12 to October 14, 2026. Personal.", company_id=self.company_id, user_id=employee_id, user_role="employee", confirmation_received=True)
        leave = next(item for item in workflow["tool_results"] if item.get("tool") == "leave_management")
        self.assertEqual(leave["status_label"], "pending_approval")
        pending = next(item for item in list_pending_approvals(self.company_id) if item["workflow_id"] == workflow["workflow_id"])
        approved = approve_request(self.company_id, pending["approval_id"], workspace["user_id"], "Approved")
        self.assertEqual(approved["status"], "approved")
        summary = get_leave_summary(self.company_id, employee_id)
        self.assertEqual(summary["leave_balance"], 17)
        record = next(item for item in summary["requests"] if item["leave_request_id"] == leave["request_id"])
        self.assertEqual(record["status"], "approved")

    def test_approval_clarification_returns_request_to_pending(self):
        workspace = create_company_workspace(company_id=self.company_id, company_name="Clarification Co", admin_name="Admin", admin_email=self.email, password="ValidPass123")
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        request = create_department_request(company_id=self.company_id, user_id=employee_id, workflow_id="wf-clarify-" + self.company_id, service_area="IT", request_type="support_request", title="VPN access", requires_approval=True)
        approval = create_approval(company_id=self.company_id, workflow_id=request["workflow_id"], requested_by=employee_id, approval_type="it_request", metadata={"request_id": request["request_id"], "service_area": "IT"})
        result = request_approval_clarification(self.company_id, approval["approval_id"], workspace["user_id"], "Which device needs access?")
        self.assertEqual(result["status"], "success")
        self.assertEqual(get_approval(self.company_id, approval["approval_id"])["status"], "needs_clarification")
        self.assertEqual(get_my_department_request(self.company_id, employee_id, request["request_id"])["status"], "needs_clarification")
        response = respond_to_approval_clarification(self.company_id, approval["approval_id"], employee_id, "My company laptop")
        self.assertEqual(response["status"], "success")
        self.assertEqual(get_approval(self.company_id, approval["approval_id"])["status"], "pending")
        self.assertEqual(get_my_department_request(self.company_id, employee_id, request["request_id"])["status"], "pending_approval")

    def test_natural_language_variations_and_multi_turn_clarification(self):
        routes = [
            ("Can I take leave for three days next week?", "leave_management"),
            ("I want to apply for vacation.", "leave_management"),
            ("My system is having a network problem.", "knowledge_base_service"),
            ("Can I get a developer machine?", "purchase_request"),
            ("I need software installed on my system.", "software_service"),
            ("What is our leave policy?", "hr_policy_service"),
            ("Do we have developer laptops?", "inventory_check"),
        ]
        for request, expected_tool in routes:
            with self.subTest(request=request):
                analysis = local_fallback_analyze(request)
                self.assertIn(expected_tool, analysis["tools"])

        workspace = create_company_workspace(company_id=self.company_id, company_name="Conversation Co", admin_name="Admin", admin_email=self.email, password="ValidPass123")
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            first = run_workflow("I want leave.", company_id=self.company_id, user_id=employee_id, user_role="employee")
        self.assertEqual(first["validation"]["status"], "needs_clarification")
        self.assertIn("start date", first["response"].lower())
        save_workflow_request(first["workflow_id"], self.company_id, employee_id, first["raw_message"], status="needs_clarification")
        history = [{"role": "user", "content": "I want leave."}, {"role": "assistant", "content": first["response"]}]
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            second = run_workflow("I want leave.\nAdditional information: Next Monday and Tuesday, for personal reasons", conversation_history=history, company_id=self.company_id, user_id=employee_id, user_role="employee", workflow_id=first["workflow_id"])
        self.assertEqual(second["validation"]["status"], "pending_confirmation")
        self.assertFalse(
            any(
                item.get("tool") == "leave_management"
                and item.get("executed") is True
                for item in second["tool_results"]
            ),
            "Leave must not be submitted before explicit confirmation.",
        )
        self.assertEqual(get_leave_summary(self.company_id, employee_id)["requests"], [])

        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            completed = resume_workflow(second, "yes, proceed")

        leave = next(
            item for item in completed["tool_results"]
            if item.get("tool") == "leave_management"
        )
        self.assertEqual(leave["status"], "success")
        summary = get_leave_summary(self.company_id, employee_id)
        record = next(
            item for item in summary["requests"]
            if item["leave_request_id"] == leave["request_id"]
        )
        next_monday = date.today() + timedelta(days=7 - date.today().weekday())
        self.assertEqual(
            (record["start_date"], record["end_date"]),
            (next_monday.isoformat(), (next_monday + timedelta(days=1)).isoformat()),
        )
        self.assertEqual(record["status"], "pending_approval")

    def test_laptop_assistant_collects_purpose_then_confirms_before_creation(self):
        workspace = create_company_workspace(company_id=self.company_id, company_name="Assistant Co", admin_name="Admin", admin_email=self.email, password="ValidPass123")
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        with __import__("sqlite3").connect(_test_db.name) as conn:
            import json
            row = conn.execute("SELECT context_json FROM companies WHERE company_id=?", (self.company_id,)).fetchone()
            context = json.loads(row[0])
            context["policies"].update({"laptop_budget_inr": 200000, "finance_available_budget_inr": 250000, "finance_currency": "INR"})
            context["approval_rules"]["purchase_above_inr"] = 100000
            conn.execute("UPDATE companies SET context_json=? WHERE company_id=?", (json.dumps(context), self.company_id))
        upsert_inventory_as_admin(self.company_id, workspace["user_id"], "laptop", "AI Pro", 145000, "INR", 2, {"use_case": "AI/ML development"})
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            first = run_workflow("I need a laptop.", company_id=self.company_id, user_id=employee_id, user_role="employee")
        self.assertEqual(first["validation"]["status"], "needs_clarification")
        self.assertIn("what will you use", first["response"].lower())
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "Procurement"), [])
        history = [{"role": "user", "content": "I need a laptop."}, {"role": "assistant", "content": first["response"]}]
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            second = run_workflow("AI development.", conversation_history=history, company_id=self.company_id, user_id=employee_id, user_role="employee", workflow_id=first["workflow_id"])
        self.assertEqual(second["validation"]["status"], "pending_confirmation")
        self.assertIn("AI Pro", second["response"])
        self.assertIn("145,000", second["response"])
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "Procurement"), [])
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            completed = resume_workflow(second, "yes")
        purchase = next(item for item in completed["tool_results"] if item.get("tool") == "purchase_request")
        self.assertEqual(purchase["model"], "AI Pro")
        self.assertEqual(purchase["status_label"], "pending_approval")

    def test_unconfigured_payment_is_reported_without_creating_a_request(self):
        create_company_workspace(company_id=self.company_id, company_name="Payments Co", admin_name="Admin", admin_email=self.email, password="ValidPass123")
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="Finance")
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            result = run_workflow("Transfer ₹10,000 to my bank account.", company_id=self.company_id, user_id=employee_id, user_role="employee")
        self.assertIn("not configured", result["response"].casefold())
        self.assertTrue(any(item.get("tool") == "payment_service" and item.get("status") == "not_configured" for item in result["tool_results"]))
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "Finance"), [])

    def test_unconfigured_transfer_capability_overrides_non_action_llm_route(self):
        from core.llm import analyze_request
        empty_route = {"request_category": "information_request", "intent": "transfer status", "department": "", "departments": [], "agents": [], "tools": [], "tool_plan": [], "details": {}, "requires_action": False, "confidence": 0.4, "llm_provider": "test"}
        with patch("core.llm.GEMINI_API_KEY", "test-key"), patch("core.llm.GROQ_API_KEY", ""), patch("core.llm._gemini_analyze_request", return_value=empty_route):
            result = analyze_request("Transfer ₹10,000 to my bank account.")
        self.assertIn("payment_service", result["tools"])
        self.assertTrue(result["requires_action"])
        self.assertEqual(result["capability_guard"], "unconfigured_payment_service")

    def test_it_ticket_operations_and_monitor_use_persisted_workflow(self):
        workspace = create_company_workspace(
            company_id=self.company_id,
            company_name="Test Company",
            admin_name="Tenant Admin",
            admin_email=self.email,
            password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        ticket = create_ticket({"company_id": self.company_id, "user_id": employee_id, "workflow_id": "wf-it-" + self.company_id}, "My laptop WiFi is not working")
        self.assertEqual(ticket["service_area"], "IT")
        updated = update_it_ticket(self.company_id, workspace["user_id"], ticket["request_id"], status="in_progress", priority="high", assignee_user_id=workspace["user_id"], comment="Troubleshooting started")
        self.assertEqual(updated["ticket_status"], "in_progress")
        self.assertEqual(list_it_tickets(self.company_id, workspace["user_id"])[0]["details"]["priority"], "high")

        save_workflow_request("wf-monitor-" + self.company_id, self.company_id, employee_id, "My laptop WiFi is not working", request_category="IT", intent="create_ticket", status="pending_approval", assigned_agents=["IT Support Agent"], selected_tools=["create_ticket"], context={"validation": {"status": "ok"}})
        save_workflow_execution(self.company_id, "wf-monitor-" + self.company_id, "tool_execution", agent_key="IT Support Agent", tool_key="create_ticket", output_data=ticket)
        workflows = list_company_workflows(self.company_id, workspace["user_id"], search="WiFi")
        self.assertTrue(any(item["workflow_id"] == "wf-monitor-" + self.company_id for item in workflows))
        detail = get_company_workflow_details(self.company_id, workspace["user_id"], "wf-monitor-" + self.company_id)
        self.assertEqual(detail["executions"][0]["tool_key"], "create_ticket")
        agent = next(item for item in list_agent_runtime_status(self.company_id, workspace["user_id"]) if item["key"] == "it")
        self.assertEqual(agent["status"], "active")
        self.assertGreaterEqual(agent["active_workflows"], 1)
        with self.assertRaises(PermissionError):
            list_company_workflows(self.company_id, employee_id)

    def test_natural_language_laptop_purchase_runs_and_resumes_after_approval(self):
        workspace = create_company_workspace(
            company_id=self.company_id,
            company_name="Test Company",
            admin_name="Tenant Admin",
            admin_email=self.email,
            password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        procurement_id = "procurement_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        add_company_user(procurement_id, self.company_id, "Procurement Admin", "procurement@example.test", role="procurement_admin", department="Procurement")
        with __import__("sqlite3").connect(_test_db.name) as conn:
            import json
            row = conn.execute("SELECT context_json FROM companies WHERE company_id=?", (self.company_id,)).fetchone()
            context = json.loads(row[0])
            context["policies"].update({"laptop_budget_inr": 200000, "finance_available_budget_inr": 200000, "finance_currency": "INR"})
            context["approval_rules"]["purchase_above_inr"] = 100000
            conn.execute("UPDATE companies SET context_json=? WHERE company_id=?", (json.dumps(context), self.company_id))
        upsert_inventory_as_admin(self.company_id, workspace["user_id"], "laptop", "AI Pro", 145000, "INR", 3, {"use_case": "AI/ML development"})
        upsert_vendor_as_admin(self.company_id, procurement_id, "Trusted Supplier", 4.5, 5)
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            workflow = run_workflow("I need a laptop for AI development.", company_id=self.company_id, user_id=employee_id, user_role="employee", confirmation_received=True)
        self.assertIn("Procurement Agent", workflow["assigned_agents"])
        self.assertIn("Finance Agent", workflow["assigned_agents"])
        purchase = next(item for item in workflow["tool_results"] if item.get("tool") == "purchase_request")
        self.assertEqual(purchase["model"], "AI Pro")
        self.assertEqual(purchase["status_label"], "pending_approval")
        approval = next(item for item in list_pending_approvals(self.company_id) if item["workflow_id"] == workflow["workflow_id"])
        approved = approve_request(self.company_id, approval["approval_id"], procurement_id, "Budget and policy reviewed")
        self.assertEqual(approved["status"], "approved")
        self.assertTrue(approved.get("purchase_order_id"))
        self.assertEqual(approved.get("workflow_status"), "completed")
        queue_item = next(item for item in list_my_department_requests(self.company_id, employee_id, "Procurement") if item["request_id"] == purchase["request_id"])
        self.assertEqual(queue_item["status"], "approved")
        from company.operations_service import assign_purchase_vendor
        self.assertEqual(assign_purchase_vendor(self.company_id, procurement_id, purchase["request_id"], "Trusted Supplier")["status"], "success")
        order = create_purchase_order_from_request(self.company_id, procurement_id, workflow["workflow_id"], purchase["request_id"])
        self.assertEqual(order["status"], "success")
        self.assertEqual(order["request_id"], approved["purchase_order_id"])
        repeated = create_purchase_order_from_request(self.company_id, procurement_id, workflow["workflow_id"], purchase["request_id"])
        self.assertEqual(repeated["request_id"], order["request_id"])
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "Procurement")[0]["details"]["assigned_vendor"]["name"], "Trusted Supplier")
        with __import__("sqlite3").connect(_test_db.name) as conn:
            source_details = __import__("json").loads(conn.execute("SELECT details_json FROM department_requests WHERE company_id=? AND request_id=?", (self.company_id, purchase["request_id"])).fetchone()[0])
            order_details = __import__("json").loads(conn.execute("SELECT details_json FROM department_requests WHERE company_id=? AND request_id=?", (self.company_id, order["request_id"])).fetchone()[0])
            stock_after = conn.execute("SELECT quantity_available FROM company_inventory WHERE company_id=? AND inventory_id=?", (self.company_id, source_details["inventory_id"])).fetchone()[0]
        self.assertEqual(source_details["purchase_order_id"], order["request_id"])
        self.assertEqual(order_details["assigned_vendor"]["name"], "Trusted Supplier")
        self.assertEqual(stock_after, 2)


    def test_service_catalog_routes_specialized_hr_and_it_requests(self):
        from core.service_catalog import classify_specialized_request

        cases = [
            ("I need an employment verification letter for a bank loan", "employment_verification_letter"),
            ("Please submit an expense reimbursement for my business trip", "expense_reimbursement"),
            ("I want to relocate to another office", "relocation_mobility"),
            ("I want to request a transfer to another company office location.", "relocation_mobility"),
            ("I need a medical accommodation at work", "medical_accommodation"),
            ("I need visa sponsorship and immigration support", "visa_immigration_support"),
            ("Please report fraud as an ethics violation", "whistleblower_ethics"),
            ("I need a salary slip request", "payroll_compensation_request"),
            ("Can I get a salary slip?", "payroll_compensation_request"),
            ("Please request an appraisal form", "performance_appraisal_request"),
            ("Please request a professional development course", "professional_training_request"),
            ("Please report a workplace complaint", "employee_grievance"),
            ("Please correct my attendance", "attendance_correction"),
            ("I need an insurance claim", "insurance_claim"),
            ("Please enroll me in health insurance", "insurance_enrollment"),
            ("Please start onboarding for a new hire", "employee_onboarding_request"),
            ("Please apply for maternity leave", "family_leave_support"),
            ("I need a relieving letter", "hr_document_request"),
            ("Please report this phishing email", "security_incident"),
            ("Please create a ticket for offboarding access removal", "offboarding_access_removal"),
            ("Please recover deleted files from backup", "data_recovery_backup"),
            ("I accidentally deleted an important work file. I need help recovering it.", "data_recovery_backup"),
            ("Please submit a system-wide upgrade change request", "change_management"),
            ("Please enroll my personal phone in BYOD MDM", "byod_mdm_enrollment"),
            ("Please whitelist this blocked domain", "software_whitelisting"),
            ("Please reset my MFA", "mfa_2fa_support"),
            ("Please reset my password", "password_reset"),
            ("I need support for the office printer", "office_equipment_support"),
            ("Please request a new monitor", "peripheral_device_request"),
            ("I need to onboard a new hire", "employee_onboarding_request"),
            ("Please initiate offboarding for an employee", "employee_offboarding_request"),
            ("I want to enroll in employee benefits", "benefit_enrollment_request"),
            ("Please revoke employee access when staff leaves the company", "offboarding_access_removal"),
            ("I want to enroll in a technical training course", "professional_training_request"),
            ("I need help with a technical issue in an internal company system", "it_general_request"),
            ("Create an IT ticket for my network problem", "network_connectivity"),
            ("I need my salary advance processed", "payroll_compensation_request"),
            ("I want to request a promotion", "performance_appraisal_request"),
            ("I need a gym membership benefit", "benefit_enrollment_request"),
            ("Please update my work from home schedule", "remote_work_request"),
            ("I need Python installed on my company laptop", "software_installation_access"),
            ("Please file an IT hardware asset request for a laptop", "hardware_asset_request"),
            ("Please set up my corporate email", "account_access_request"),
            ("I need help with a VPN connection issue", "network_connectivity"),
            ("I accidentally deleted a OneDrive document; please restore it", "data_recovery_backup"),
            ("Please remove access when an employee resigns", "offboarding_access_removal"),
            ("Please report sexual harassment by my manager", "employee_grievance"),
            ("I need reimbursement for my home internet bill", "expense_reimbursement"),
            ("I need an employment certificate", "employment_verification_letter"),
            ("Please request a business application license", "software_installation_access"),
            ("I need a network support ticket", "network_connectivity"),
        ]
        for message, expected_type in cases:
            with self.subTest(message=message):
                route = classify_specialized_request(message)
                self.assertIsNotNone(route, message)
                self.assertEqual(route["intent"], expected_type)
                self.assertTrue(route["tools"])
                self.assertTrue(route["agents"])
                self.assertEqual(route["request_category"], "enterprise_action")
                if message == "Create an IT ticket for my network problem":
                    self.assertFalse(route["details"]["service_request_requires_approval"])

    def test_read_only_policy_and_troubleshooting_queries_stay_read_only(self):
        from core.service_catalog import classify_read_only_route
        cases = [
            ("What are our work from home rules?", "hr_policy_service", "hr_policy_information"),
            ("What is our holiday calendar?", "hr_policy_service", "hr_policy_information"),
            ("How do I reset my password?", "knowledge_base_service", "it_support_guidance"),
            ("My laptop has a blue screen", "knowledge_base_service", "it_troubleshooting_guidance"),
        ]
        for text, tool, intent in cases:
            with self.subTest(text=text):
                route = classify_read_only_route(text)
                self.assertIsNotNone(route)
                self.assertEqual(route["tools"][0], tool)
                self.assertEqual(route["intent"], intent)
                self.assertFalse(route.get("requires_action", False))

    def test_action_request_wording_cannot_self_confirm(self):
        from core.tool_executor import can_execute_action_tool, has_explicit_confirmation
        action_messages = [
            "Please submit an expense reimbursement for my business trip.",
            "Please create an IT ticket for my network problem.",
            "Please submit the employment verification letter request.",
            "Please create the purchase order.",
        ]
        for message in action_messages:
            with self.subTest(message=message):
                self.assertFalse(has_explicit_confirmation(message))
                self.assertFalse(can_execute_action_tool("hr_general_request_service", {}, message, confirmed=False))
                self.assertFalse(can_execute_action_tool("create_ticket", {}, message, confirmed=False))
        self.assertTrue(has_explicit_confirmation("Yes, proceed"))
        self.assertTrue(can_execute_action_tool("create_ticket", {}, "Yes, proceed", confirmed=True))

    def test_generic_hr_request_type_is_persisted_not_dropped(self):
        create_company_workspace(
            company_id=self.company_id, company_name="Generic HR Service Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="HR")
        from tools.hr_tools import hr_general_request_service
        result = hr_general_request_service({
            "company_id": self.company_id,
            "user_id": employee_id,
            "workflow_id": "wf-generic-hr-" + self.company_id,
            "service_request_type": "employee_flexible_schedule",
            "service_request_title": "Flexible schedule request",
            "service_request_needs_external_integration": True,
        }, "Please submit my request for a flexible working schedule.")
        self.assertEqual(result["status"], "success")
        saved = list_my_department_requests(self.company_id, employee_id, "HR")
        record = next(item for item in saved if item["request_id"] == result["request_id"])
        self.assertEqual(record["request_type"], "employee_flexible_schedule")
        self.assertEqual(record["title"], "Flexible schedule request")
        self.assertEqual(record["details"]["service_request_type"], "employee_flexible_schedule")
        self.assertEqual(record["status"], "pending_approval")

    def test_generic_hr_and_it_fallbacks_are_confirmation_gated_and_persisted(self):
        workspace = create_company_workspace(
            company_id=self.company_id, company_name="Generic Service Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="Engineering")

        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            hr_pending = run_workflow(
                "I need help changing a personal detail in my employee record.",
                company_id=self.company_id, user_id=employee_id, user_role="employee",
            )
        self.assertEqual(hr_pending["validation"]["status"], "pending_confirmation")
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "HR"), [])
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            hr_done = resume_workflow(hr_pending, "Yes, proceed")
        hr_records = list_my_department_requests(self.company_id, employee_id, "HR")
        self.assertEqual(len(hr_records), 1)
        self.assertEqual(hr_records[0]["request_type"], "generic_hr_request")
        self.assertEqual(hr_records[0]["status"], "pending_approval")
        self.assertIn(hr_records[0]["request_id"], hr_done["response"])

        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            it_pending = run_workflow(
                "I need help with a technical issue in an internal company system.",
                company_id=self.company_id, user_id=employee_id, user_role="employee",
            )
        self.assertEqual(it_pending["validation"]["status"], "pending_confirmation")
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "IT"), [])
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            it_done = resume_workflow(it_pending, "Yes, proceed")
        it_records = list_my_department_requests(self.company_id, employee_id, "IT")
        self.assertEqual(len(it_records), 1)
        self.assertEqual(it_records[0]["details"]["service_request_type"], "it_general_request")
        self.assertEqual(it_records[0]["status"], "submitted")
        self.assertIn(it_records[0]["request_id"], it_done["response"])

        from company.request_service import list_service_requests_for_admin
        self.assertEqual(
            list_service_requests_for_admin(self.company_id, workspace["user_id"], service_area="HR")[0]["request_id"],
            hr_records[0]["request_id"],
        )
        self.assertEqual(
            list_service_requests_for_admin(self.company_id, workspace["user_id"], service_area="IT")[0]["request_id"],
            it_records[0]["request_id"],
        )

    def test_wifi_request_does_not_get_attached_to_pending_leave_clarification(self):
        history = [
            {"role": "user", "content": "leave request"},
            {"role": "assistant", "content": "Please provide the leave start date and end date."},
        ]
        analysis = local_fallback_analyze(
            "my wifi was not connecting",
            conversation_history=history,
        )
        self.assertEqual(analysis.get("department"), "IT")
        self.assertIn("create_ticket", analysis.get("tools", []))
        self.assertFalse(analysis.get("details", {}).get("follow_up_applied"))

    def test_comma_separated_leave_dates_are_parsed_as_range(self):
        history = [
            {"role": "user", "content": "leave request"},
            {"role": "assistant", "content": "Please provide the leave start date and end date."},
        ]
        analysis = local_fallback_analyze(
            "20-10-2026, 22-10-2026",
            conversation_history=history,
        )
        self.assertEqual(analysis.get("intent"), "leave_request")
        self.assertEqual(analysis.get("details", {}).get("start_date"), "2026-10-20")
        self.assertEqual(analysis.get("details", {}).get("end_date"), "2026-10-22")

    def test_learning_question_never_creates_hr_or_it_request(self):
        workspace = create_company_workspace(
            company_id=self.company_id, company_name="Learning Query Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            result = run_workflow(
                "What tool should I use to learn Python?",
                company_id=self.company_id, user_id=employee_id, user_role="employee",
            )
        self.assertEqual(result["intent"], "general_learning_guidance")
        self.assertIn("learn Python", result["response"])
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "HR"), [])
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "IT"), [])
        self.assertEqual(result["validation"]["status"], "success")

    def test_password_how_to_question_is_read_only(self):
        from core.service_catalog import classify_read_only_route, classify_specialized_request
        question = "How do I reset my password?"
        self.assertFalse(classify_specialized_request(question))
        route = classify_read_only_route(question)
        self.assertIsNotNone(route)
        self.assertEqual(route["request_category"], "information_request")
        self.assertNotEqual(route["tools"], ["password_access_service"])

    def test_network_troubleshooting_answers_without_creating_ticket(self):
        create_company_workspace(
            company_id=self.company_id, company_name="Network Help Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            result = run_workflow(
                "My system is having a network problem.",
                company_id=self.company_id, user_id=employee_id, user_role="employee",
            )
        self.assertEqual(result["intent"], "it_troubleshooting_guidance")
        self.assertIn("general guidance only", result["response"].casefold())
        self.assertIn("Wi-Fi/Ethernet", result["response"])
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "IT"), [])

    def test_follow_up_during_pending_confirmation_preserves_action_until_confirmed(self):
        create_company_workspace(
            company_id=self.company_id, company_name="Pending Follow-up Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        original_message = "I accidentally deleted an important work file. I need help recovering it."
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            pending = run_workflow(
                original_message, company_id=self.company_id, user_id=employee_id, user_role="employee",
            )
        self.assertEqual(pending["validation"]["status"], "pending_confirmation")
        self.assertEqual(classify_pending_confirmation_reply("Where do I see that?", pending), "hold")

        held = hold_pending_confirmation_result(pending)
        self.assertEqual(held["validation"]["status"], "pending_confirmation")
        self.assertIn("No IT ticket has been created yet", held["response"])
        self.assertIn("Yes, proceed", held["response"])
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "IT"), [])

        # The confirmation must still resume the original action after the follow-up.
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            completed = resume_workflow(held, "Yes, proceed")
        records = list_my_department_requests(self.company_id, employee_id, "IT")
        self.assertEqual(len(records), 1)
        self.assertIn(records[0]["request_id"], completed["response"])

    def test_pending_action_can_be_cancelled_without_creating_a_request(self):
        create_company_workspace(
            company_id=self.company_id, company_name="Pending Cancellation Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            pending = run_workflow(
                "Create an IT ticket for my network problem.",
                company_id=self.company_id, user_id=employee_id, user_role="employee",
            )
        self.assertEqual(pending["validation"]["status"], "pending_confirmation")
        self.assertEqual(classify_pending_confirmation_reply("No, cancel", pending), "cancel")
        cancelled = cancel_pending_workflow(pending, "No, cancel")
        self.assertEqual(cancelled["validation"]["status"], "cancelled")
        self.assertIn("not submitted", cancelled["response"].casefold())
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "IT"), [])

    def test_confirm_reply_variants_are_normalized_but_typo_is_not_accepted(self):
        pending = {"validation": {"status": "pending_confirmation"}, "decision": {"confirmation_required": True}}
        self.assertEqual(classify_pending_confirmation_reply("Yes,proceed", pending), "confirm")
        self.assertEqual(classify_pending_confirmation_reply("yes,procced", pending), "hold")
        self.assertEqual(classify_pending_confirmation_reply("What tool should I use to learn Python?", pending), "hold")

    def test_confirmed_ticket_can_be_retrieved_by_vague_follow_up(self):
        create_company_workspace(
            company_id=self.company_id, company_name="Ticket Follow-up Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        original_message = "Create an IT ticket for my network problem."
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            pending = run_workflow(
                original_message, company_id=self.company_id, user_id=employee_id, user_role="employee",
            )
        self.assertEqual(pending["validation"]["status"], "pending_confirmation")
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "IT"), [])
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            created = resume_workflow(pending, "yes, proceed")
        records_before = list_my_department_requests(self.company_id, employee_id, "IT")
        self.assertEqual(len(records_before), 1)
        ticket_id = records_before[0]["request_id"]
        self.assertIn(ticket_id, created["response"])
        history = [
            {"role": "user", "content": original_message},
            {"role": "assistant", "content": created["response"]},
        ]
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            follow_up = run_workflow(
                "Where do I see that?", conversation_history=history,
                company_id=self.company_id, user_id=employee_id, user_role="employee",
            )
        self.assertEqual(follow_up["intent"], "it_ticket_follow_up")
        self.assertIn(ticket_id, follow_up["response"])
        self.assertIn("Current status: Submitted", follow_up["response"])
        self.assertIn("My IT Tickets", follow_up["response"])
        self.assertEqual(len(list_my_department_requests(self.company_id, employee_id, "IT")), 1)

    def test_deleted_work_file_recovery_is_confirmation_gated_and_saved_as_it_ticket(self):
        create_company_workspace(
            company_id=self.company_id, company_name="Recovery Routing Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="Engineering")
        message = "I accidentally deleted an important work file. I need help recovering it."
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            pending = run_workflow(message, company_id=self.company_id, user_id=employee_id, user_role="employee")
        self.assertEqual(pending["intent"], "data_recovery_backup")
        self.assertEqual(pending["validation"]["status"], "pending_confirmation")
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "IT"), [])
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            created = resume_workflow(pending, "yes, proceed")
        records = list_my_department_requests(self.company_id, employee_id, "IT")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["details"]["service_request_type"], "data_recovery_backup")
        self.assertEqual(records[0]["status"], "pending_approval")
        self.assertIn(records[0]["request_id"], created["response"])
        self.assertIn("not itself", records[0]["details"]["processing_note"].casefold())

    def test_specialized_hr_request_is_confirmed_then_saved_for_admin_review(self):
        workspace = create_company_workspace(
            company_id=self.company_id, company_name="HR Service Catalog Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="Engineering")
        message = "I need an employment verification letter for a bank loan."
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            pending = run_workflow(message, company_id=self.company_id, user_id=employee_id, user_role="employee")
        self.assertEqual(pending["validation"]["status"], "pending_confirmation")
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "HR"), [])
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            created = resume_workflow(pending, "yes, proceed")
        records = list_my_department_requests(self.company_id, employee_id, "HR")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["request_type"], "employment_verification_letter")
        self.assertEqual(records[0]["status"], "pending_approval")
        self.assertTrue(records[0]["details"]["needs_external_integration"])
        self.assertIn("approval", created["response"].casefold())
        from company.request_service import list_service_requests_for_admin
        queue = list_service_requests_for_admin(self.company_id, workspace["user_id"], service_area="HR")
        self.assertEqual(queue[0]["request_id"], records[0]["request_id"])

    def test_security_incident_is_confirmation_gated_and_marked_restricted(self):
        create_company_workspace(
            company_id=self.company_id, company_name="Security Routing Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="IT")
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            pending = run_workflow(
                "Please report this phishing email to IT.",
                company_id=self.company_id, user_id=employee_id, user_role="employee",
            )
        self.assertEqual(pending["validation"]["status"], "pending_confirmation")
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "IT"), [])
        with patch("core.llm.GROQ_API_KEY", ""), patch("core.llm.GEMINI_API_KEY", ""):
            created = resume_workflow(pending, "yes, proceed")
        records = list_my_department_requests(self.company_id, employee_id, "IT")
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["details"]["confidential"])
        self.assertEqual(records[0]["details"]["service_request_type"], "security_incident")
        self.assertIn("external integration", records[0]["details"]["processing_note"].casefold())

    def test_benefits_question_is_read_only_and_never_enrolls_employee(self):
        create_company_workspace(
            company_id=self.company_id, company_name="Benefits Query Co",
            admin_name="Admin", admin_email=self.email, password="ValidPass123",
        )
        employee_id = "employee_" + self.company_id
        add_company_user(employee_id, self.company_id, "Employee", "employee@example.test", department="HR")
        from tools.hr_tools import benefits_service
        from core.tool_executor import can_execute_action_tool
        details = {"company_id": self.company_id, "user_id": employee_id}
        self.assertTrue(can_execute_action_tool("benefits_service", details, "Do we have health insurance?", confirmed=False))
        result = benefits_service(details, "Do we have health insurance?")
        self.assertIn(result["status"], {"not_configured", "success"})
        self.assertEqual(list_my_department_requests(self.company_id, employee_id, "HR"), [])

    def test_hr_grievance_and_training_tools_require_confirmation(self):
        from core.tool_executor import can_execute_action_tool
        self.assertFalse(can_execute_action_tool("hr_grievance_service", {}, "Please report workplace harassment", confirmed=False))
        self.assertFalse(can_execute_action_tool("hr_training_service", {}, "I need a training request", confirmed=False))
        self.assertTrue(can_execute_action_tool("hr_grievance_service", {}, "yes, proceed", confirmed=True))
        self.assertTrue(can_execute_action_tool("hr_training_service", {}, "yes, proceed", confirmed=True))


if __name__ == "__main__":
    unittest.main()

