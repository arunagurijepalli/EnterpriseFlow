"""Regression tests for confirmed ticket/leave workflows and pending summaries."""
from __future__ import annotations
import unittest
from unittest.mock import patch

from core.service_catalog import classify_read_only_route, classify_specialized_request
from core.conversation_intent import is_clear_new_request_during_clarification
from company.pending_query_service import get_pending_lookup_result
from core.tool_executor import execute_tool
from tools.hr_tools import leave_management
from company.request_service import _looks_like_nonbusiness_workflow_request


class CoordinatorRegressionV13Tests(unittest.TestCase):
    def test_bare_it_ticket_routes_to_ticket_creation_not_knowledge(self):
        for prompt in ("create it ticket", "create one It ticket", "Create an IT ticket"):
            with self.subTest(prompt=prompt):
                route = classify_specialized_request(prompt)
                self.assertIsNotNone(route)
                self.assertEqual(route["department"], "IT")
                self.assertEqual(route["agents"], ["IT Support Agent"])
                self.assertEqual(route["tools"], ["create_ticket"])
                self.assertTrue(route["requires_action"])

    def test_specific_ticket_intent_keeps_specific_category(self):
        route = classify_read_only_route("Create an IT ticket for my network problem.", None)
        if route is None:
            route = classify_specialized_request("Create an IT ticket for my network problem.")
        self.assertEqual(route["intent"], "network_connectivity")
        self.assertEqual(route["tools"], ["create_ticket"])

    def test_show_details_after_ticket_id_uses_read_only_ticket_lookup(self):
        history = [{"role": "assistant", "content": "IT request IT-974496B1 was created."}]
        route = classify_read_only_route("show details", history)
        self.assertIsNotNone(route)
        self.assertEqual(route["intent"], "it_ticket_follow_up")
        self.assertEqual(route["tools"], ["create_ticket"])
        self.assertEqual(route["details"]["ticket_id"], "IT-974496B1")
        self.assertTrue(route["details"]["read_only_follow_up"])

    def test_show_performance_routes_to_read_only_performance_service(self):
        for prompt in ("Show performance for EMP1003", "Show my performance review"):
            with self.subTest(prompt=prompt):
                route = classify_read_only_route(prompt, None)
                self.assertIsNotNone(route)
                self.assertEqual(route["request_category"], "information_request")
                self.assertEqual(route["tools"], ["performance_service"])
                self.assertFalse(route["requires_action"])

    def test_show_leave_history_routes_to_read_only_leave_service(self):
        route = classify_read_only_route(
            "Show all my leave requests, including pending, approved, and rejected requests.", None
        )
        self.assertIsNotNone(route)
        self.assertEqual(route["request_category"], "information_request")
        self.assertEqual(route["tools"], ["leave_management"])
        self.assertFalse(route["requires_action"])

    def test_legacy_read_only_hr_queries_are_hidden_from_pending_list(self):
        self.assertTrue(_looks_like_nonbusiness_workflow_request("Show performance for EMP1003", "enterprise_action"))
        self.assertTrue(_looks_like_nonbusiness_workflow_request("Show all my leave requests, including pending and approved requests", "enterprise_action"))
        self.assertFalse(_looks_like_nonbusiness_workflow_request("Create a leave request for tomorrow", "enterprise_action"))

    def test_command_line_input_is_never_classified_as_business_action(self):
        prompt = r"..venv312\Scripts\streamlit.exe run .\ui\app.py"
        route = classify_read_only_route(prompt, None)
        self.assertIsNotNone(route)
        self.assertEqual(route["request_category"], "information_request")
        self.assertFalse(route["requires_action"])
        self.assertNotIn("create_ticket", route["tools"])

    def test_printer_symptom_after_generic_ticket_prompt_continues_clarification(self):
        self.assertFalse(is_clear_new_request_during_clarification(
            "The office printer is not working.", "create one IT ticket"
        ))

    def test_bare_ticket_request_asks_for_issue_before_confirmation(self):
        result = execute_tool(
            "create_ticket",
            {"service_request_type": "it_general_request", "service_request_title": "General IT support request"},
            "create one IT ticket",
            confirmed=False,
        )
        self.assertEqual(result["status"], "missing_information")
        self.assertIn("describe the IT issue", result["message"])
        self.assertFalse(result.get("executed", False))

    def test_leave_request_collects_reason_before_confirmation(self):
        result = execute_tool(
            "leave_management",
            {"start_date": "2026-10-20", "end_date": "2026-10-21"},
            "create leave request Additional information: 20-10-2026, 21-10-2026",
            confirmed=False,
        )
        self.assertEqual(result["status"], "missing_information")
        self.assertIn("purpose of your leave", result["message"])
        self.assertFalse(result.get("executed", False))

    def test_confirmed_leave_action_creates_request_instead_of_only_returning_balance(self):
        with patch("company.leave_service.get_leave_summary", return_value={
            "status": "success", "leave_balance": 10, "leave_entitlement": 20,
            "leave_types": ["Annual Leave"], "requests": [],
        }), patch("company.leave_service.create_leave_request", return_value={
            "status": "success", "executed": True, "tool": "leave_management",
            "request_id": "LV-2026-ABC123", "status_label": "pending_approval",
            "start_date": "2026-10-20", "end_date": "2026-10-21", "requested_days": 2,
            "leave_type": "Annual Leave", "message": "Leave request LV-2026-ABC123 was created with status pending approval.",
        }) as create_request:
            result = leave_management({
                "company_id": "test-company", "user_id": "test-user", "workflow_id": "wf-test",
                "start_date": "2026-10-20", "end_date": "2026-10-21",
                "leave_type": "Annual Leave", "reason": "Personal reasons", "_confirmed_action": True,
            }, "ceate leave request Additional information: 20-10-2026, 21-10-2026")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["request_id"], "LV-2026-ABC123")
        create_request.assert_called_once()

    def test_legacy_terminal_command_is_not_shown_as_a_business_request(self):
        self.assertTrue(_looks_like_nonbusiness_workflow_request(
            r"..venv312\Scripts\streamlit.exe run .\ui\app.py", "enterprise_action"
        ))
        self.assertTrue(_looks_like_nonbusiness_workflow_request(
            "What is our leave policy?", "information_request"
        ))
        self.assertFalse(_looks_like_nonbusiness_workflow_request(
            "My office printer is not working", "enterprise_action"
        ))

    def test_pending_approvals_excludes_clarifications(self):
        fake = [
            {"request_id": "IT-AAAA1111", "display_title": "Network support", "service_area": "IT", "status": "pending_approval"},
            {"request_id": "HR-BBBB2222", "display_title": "Leave request", "service_area": "HR", "status": "awaiting_clarification"},
            {"request_id": "IT-CCCC3333", "display_title": "Password support", "service_area": "IT", "status": "pending"},
        ]
        with patch("company.pending_query_service.list_my_pending_requests", return_value=fake):
            result = get_pending_lookup_result("my pending approvals", "co", "u", "employee")
        self.assertIn("2 request(s) awaiting approval", result["response"])
        self.assertIn("awaiting clarification", result["response"])
        self.assertNotIn("HR-BBBB2222", result["response"])
        self.assertIn("IT-AAAA1111", result["response"])
        self.assertIn("IT-CCCC3333", result["response"])

    def test_my_pending_requests_separates_approvals_from_clarifications(self):
        fake = [
            {"request_id": "IT-AAAA1111", "display_title": "Network support", "service_area": "IT", "status": "pending_approval"},
            {"request_id": "HR-BBBB2222", "display_title": "Leave request", "service_area": "HR", "status": "awaiting_clarification"},
        ]
        with patch("company.pending_query_service.list_my_pending_requests", return_value=fake):
            result = get_pending_lookup_result("my pending requests", "co", "u", "employee")
        self.assertIn("1 awaiting approval", result["response"])
        self.assertIn("1 awaiting clarification", result["response"])


if __name__ == "__main__":
    unittest.main()
