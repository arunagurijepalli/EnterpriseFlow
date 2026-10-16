"""Regression tests for pending approval recovery and editable demo defaults."""
from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

import company.store as store
import company.request_service as requests
import company.approval_service as approvals
import company.catalog_service as catalog
import company.leave_service as leave
import company.employee_service as employee_service


class AdminDefaultsAndPendingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "company.db"
        self.patches = [
            patch.object(store, "DB_PATH", self.db),
            patch.object(requests, "DB_PATH", self.db),
            patch.object(approvals, "DB_PATH", self.db),
            patch.object(catalog, "DB_PATH", self.db),
            patch.object(leave, "DB_PATH", self.db),
            patch.object(employee_service, "DB_PATH", self.db),
        ]
        for item in self.patches:
            item.start()
        store.initialize_company_store()
        self.company_id = "tenant_v8"
        store.register_company(self.company_id, "Tenant V8", "tenant-v8.example", context={"departments": ["HR", "IT"]})
        store.add_company_user("admin_v8", self.company_id, "Admin V8", "admin@tenant-v8.test", role="company_admin")
        store.add_company_user("it_admin_v8", self.company_id, "IT Admin V8", "it-admin@tenant-v8.test", role="it_admin", department="IT")
        store.add_company_user("hr_admin_v8", self.company_id, "HR Admin V8", "hr-admin@tenant-v8.test", role="hr_admin", department="HR")
        store.add_company_user("employee_v8", self.company_id, "Employee V8", "employee@tenant-v8.test", role="employee", department="IT")

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_legacy_pending_request_is_visible_to_employee_and_admin(self):
        req = requests.create_department_request(
            company_id=self.company_id,
            user_id="employee_v8",
            workflow_id="legacy-wf-approval-v8",
            service_area="IT",
            request_type="data_recovery",
            title="Recover deleted work file",
            description="Employee deleted a business file and needs a recovery review.",
            requires_approval=True,
        )
        self.assertEqual(req["status"], "success")
        self.assertEqual(req["status_label"], "pending_approval")

        # Simulate a legacy request that lacks a linked approvals row.
        own_pending = requests.list_my_pending_requests(self.company_id, "employee_v8")
        self.assertEqual(len(own_pending), 1)
        self.assertEqual(own_pending[0]["request_id"], req["request_id"])

        reconciled = approvals.reconcile_pending_approval_records(self.company_id)
        self.assertEqual(reconciled, 1)
        pending_for_admin = approvals.list_pending_approvals(self.company_id)
        matching = [item for item in pending_for_admin if (item.get("metadata") or {}).get("request_id") == req["request_id"]]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["status"], "pending")
        self.assertGreater(int(matching[0]["approval_id"]), 0)

        # Re-running the recovery routine must not duplicate approvals.
        self.assertEqual(approvals.reconcile_pending_approval_records(self.company_id), 0)
        again = approvals.list_pending_approvals(self.company_id)
        self.assertEqual(len([item for item in again if (item.get("metadata") or {}).get("request_id") == req["request_id"]]), 1)

    def test_multiple_legacy_requests_without_workflow_ids_get_distinct_approvals(self):
        created = []
        for title, request_type in (
            ("Recover deleted work file", "data_recovery"),
            ("MFA access support", "mfa_support"),
        ):
            result = requests.create_department_request(
                company_id=self.company_id,
                user_id="employee_v8",
                workflow_id="",
                service_area="IT",
                request_type=request_type,
                title=title,
                description=title,
                requires_approval=True,
            )
            self.assertEqual(result["status"], "success")
            created.append(result["request_id"])

        reconciled = approvals.reconcile_pending_approval_records(self.company_id)
        self.assertEqual(reconciled, 2)
        with closing(sqlite3.connect(self.db)) as conn:
            rows = conn.execute(
                "SELECT request_id,approval_id FROM department_requests WHERE company_id=? AND request_id IN (?,?)",
                (self.company_id, *created),
            ).fetchall()
        links = {row[0]: row[1] for row in rows}
        self.assertEqual(set(links), set(created))
        self.assertTrue(all(links.values()))
        self.assertEqual(len(set(links.values())), 2)
        self.assertEqual(approvals.reconcile_pending_approval_records(self.company_id), 0)

    def test_department_admin_can_retrieve_unassigned_legacy_approval_with_null_assignee(self):
        req = requests.create_department_request(
            company_id=self.company_id,
            user_id="employee_v8",
            workflow_id="legacy-null-assignee-v8",
            service_area="IT",
            request_type="mfa_support",
            title="MFA reset support",
            description="Review the employee MFA access issue.",
            requires_approval=True,
        )
        self.assertEqual(req["status"], "success")
        approval = approvals.create_approval(
            company_id=self.company_id,
            workflow_id="legacy-null-assignee-v8",
            requested_by="employee_v8",
            approval_type="it_request",
            reason="Review MFA support request",
            metadata={"request_id": req["request_id"], "service_area": "IT", "title": "MFA reset support"},
        )
        with approvals._connect() as conn:
            conn.execute(
                "UPDATE approvals SET approver_user_id=NULL WHERE company_id=? AND approval_id=?",
                (self.company_id, approval["approval_id"]),
            )
        pending = approvals.list_pending_approvals(self.company_id, "it_admin_v8")
        self.assertIn(int(approval["approval_id"]), {int(item["approval_id"]) for item in pending})

    def test_it_approval_notifications_route_to_company_and_it_admin_not_hr_admin(self):
        approval = approvals.create_approval(
            company_id=self.company_id,
            workflow_id="it-notify-role-routing",
            requested_by="employee_v8",
            approval_type="it_request",
            reason="Review a device security issue",
            metadata={"request_id": "IT-ROLE-ROUTE", "service_area": "IT", "title": "Device security"},
        )
        with closing(sqlite3.connect(self.db)) as conn:
            recipients = {
                row[0] for row in conn.execute(
                    "SELECT user_id FROM notifications WHERE company_id=? AND workflow_id=? AND notification_type='approval_required'",
                    (self.company_id, "it-notify-role-routing"),
                ).fetchall()
            }
        self.assertIn("admin_v8", recipients)
        self.assertIn("it_admin_v8", recipients)
        self.assertNotIn("hr_admin_v8", recipients)

    def test_workflow_only_pending_approval_is_visible_to_employee_and_admin(self):
        # Older workflow records may exist without a department_requests row.
        # Employee and admin queues must still retrieve those pending items.
        import json
        from company.request_service import list_my_pending_requests

        workflow_id = "workflow-only-pending-v12"
        with requests._connect() as conn:
            conn.execute(
                "INSERT INTO workflow_requests "
                "(workflow_id,company_id,user_id,request_text,request_category,intent,status,decision,assigned_agents_json,selected_tools_json,context_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    workflow_id, self.company_id, "employee_v8",
                    "I need a secure IT review for my deleted work file.",
                    "enterprise_action", "data_recovery_backup", "pending_approval", "{}",
                    '["IT Support Agent"]', '["create_ticket"]',
                    json.dumps({"departments": ["IT"], "tool_results": [{"request_id": "IT-WFONLY12"}]}),
                    "2026-10-12T10:00:00+00:00", "2026-10-12T10:00:00+00:00",
                ),
            )

        employee_items = list_my_pending_requests(self.company_id, "employee_v8")
        matching_employee = [item for item in employee_items if item.get("request_id") == "IT-WFONLY12"]
        self.assertEqual(len(matching_employee), 1)
        self.assertEqual(matching_employee[0]["status"], "pending_approval")

        from company.pending_query_service import get_pending_lookup_result
        pending_reply = get_pending_lookup_result(
            "my pending approvals", self.company_id, "employee_v8", "employee"
        )
        self.assertIn("IT-WFONLY12", pending_reply["response"])

        created = approvals.reconcile_pending_approval_records(self.company_id)
        self.assertEqual(created, 1)
        pending_for_admin = approvals.list_pending_approvals(self.company_id, "it_admin_v8")
        matching_admin = [item for item in pending_for_admin if (item.get("metadata") or {}).get("request_id") == "IT-WFONLY12"]
        self.assertEqual(len(matching_admin), 1)
        self.assertEqual((matching_admin[0].get("metadata") or {}).get("service_area"), "IT")

        # Running reconciliation again is idempotent and must not duplicate it.
        self.assertEqual(approvals.reconcile_pending_approval_records(self.company_id), 0)
        matching_again = [item for item in approvals.list_pending_approvals(self.company_id) if (item.get("metadata") or {}).get("request_id") == "IT-WFONLY12"]
        self.assertEqual(len(matching_again), 1)

    def test_demo_catalog_is_prefilled_editable_and_does_not_overwrite_admin_edits(self):
        store.register_company("demo_company", "Demo Enterprise", "demo.local", context={"departments": ["HR", "IT"]})
        store.add_company_user("demo_admin_v8", "demo_company", "Demo Admin", "admin@demo.local", role="company_admin")

        catalog.ensure_demo_company_defaults("demo_company")
        items = catalog.list_inventory("demo_company", "laptop")
        self.assertEqual({item["model"] for item in items}, {"AI Pro Laptop", "Developer Laptop", "Business Laptop"})
        ai = next(item for item in items if item["model"] == "AI Pro Laptop")
        self.assertEqual(ai["unit_price"], 145000)
        self.assertIn("gpu", ai["specifications"])

        catalog.upsert_inventory_as_admin(
            "demo_company", "demo_admin_v8", "laptop", "AI Pro Laptop", 151000, "INR", 2,
            specs={"ram": "64 GB", "storage": "2 TB SSD", "gpu": "RTX workstation"},
        )
        catalog.ensure_demo_company_defaults("demo_company")
        edited = next(item for item in catalog.list_inventory("demo_company", "laptop") if item["model"] == "AI Pro Laptop")
        self.assertEqual(edited["unit_price"], 151000)
        self.assertEqual(edited["quantity_available"], 2)
        self.assertEqual(edited["specifications"]["ram"], "64 GB")
        context = store.get_company_context("demo_company")
        self.assertEqual(context["organization_metadata"]["industry"], "Technology")
        self.assertEqual(context["organization_metadata"]["timezone"], "Asia/Kolkata")
        self.assertIn("headquarters", context["organization_metadata"])
        self.assertEqual(context["policies"]["leave"]["annual_leave_days"], 20)

        # Explicit admin edits to organization defaults survive later logins.
        metadata = dict(context["organization_metadata"])
        metadata["headquarters"] = "Guntur, Andhra Pradesh, India"
        store.update_company("demo_company", context_updates={"organization_metadata": metadata})
        catalog.ensure_demo_company_defaults("demo_company")
        context = store.get_company_context("demo_company")
        self.assertEqual(context["organization_metadata"]["headquarters"], "Guntur, Andhra Pradesh, India")


if __name__ == "__main__":
    unittest.main()
