"""Tests for authoritative pending request lookup responses."""
import unittest
from unittest.mock import patch
from company.pending_query_service import get_pending_lookup_result


class PendingQueryServiceTests(unittest.TestCase):
    @patch("company.pending_query_service.list_my_pending_requests")
    def test_employee_my_pending_approvals_returns_own_saved_requests(self, lookup):
        lookup.return_value = [{
            "request_id": "HR-1234ABCD", "title": "Employment letter",
            "service_area": "HR", "status": "pending_approval",
        }]
        result = get_pending_lookup_result("my pending approvals", "tenant-a", "employee-a", "employee")
        self.assertIn("HR-1234ABCD", result["response"])
        self.assertIn("pending approval", result["response"].casefold())
        self.assertEqual(result["tool_names"], ["list_my_pending_requests"])
        lookup.assert_called_once_with("tenant-a", "employee-a")

    @patch("company.pending_query_service.reconcile_pending_approval_records")
    @patch("company.pending_query_service.list_pending_approvals")
    def test_company_admin_query_returns_company_pending_approvals(self, lookup, reconcile):
        lookup.return_value = [{
            "approval_id": 7, "approval_type": "it_network_request",
            "status": "pending", "approver_user_id": "it-admin",
            "metadata": {"request_id": "IT-1234ABCD", "service_area": "IT", "title": "Network issue"},
        }]
        result = get_pending_lookup_result("pending approvals", "tenant-a", "admin-a", "company_admin")
        self.assertIn("IT-1234ABCD", result["response"])
        self.assertIn("Network Issue", result["response"])
        lookup.assert_called_once_with("tenant-a")
        reconcile.assert_called_once_with("tenant-a")

    @patch("company.pending_query_service.reconcile_pending_approval_records")
    @patch("company.pending_query_service.list_pending_approvals")
    def test_department_admin_lookup_is_tenant_and_department_scoped(self, lookup, reconcile):
        lookup.return_value = [
            {"approval_id": 7, "approval_type": "it_ticket", "status": "pending", "approver_user_id": None,
             "metadata": {"request_id": "IT-1234ABCD", "service_area": "IT", "title": "Wi-Fi issue"}},
            {"approval_id": 8, "approval_type": "hr_letter", "status": "pending", "approver_user_id": None,
             "metadata": {"request_id": "HR-1234ABCD", "service_area": "HR", "title": "Employment letter"}},
        ]
        result = get_pending_lookup_result("pending approvals", "tenant-a", "it-admin", "it_admin")
        self.assertIn("IT-1234ABCD", result["response"])
        self.assertNotIn("HR-1234ABCD", result["response"])
        lookup.assert_called_once_with("tenant-a", "it-admin")
        reconcile.assert_called_once_with("tenant-a")


if __name__ == "__main__":
    unittest.main()
