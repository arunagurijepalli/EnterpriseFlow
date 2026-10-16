"""Isolated regression tests for profile media, document exchange and project submissions."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import company.store as store
import company.employee_portfolio_service as portfolio
import company.user_profile_service as profile_service
import company.employee_document_service as document_service


# A small valid PNG signature + IHDR/IEND for profile upload verification.
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n" +
    b"\x00\x00\x00\x0dIHDR" + b"\x00\x00\x00\x01\x00\x00\x00\x01" +
    b"\x08\x02\x00\x00\x00" + b"\x90wS\xde" +
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class EmployeeCollaborationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "company.db"
        self.data_root = self.root / "data"
        self.data_root.mkdir()
        self.patches = [
            patch.object(store, "DB_PATH", self.db),
            patch.object(portfolio, "DB_PATH", self.db),
            patch.object(portfolio, "BASE_DIR", self.root),
            patch.object(profile_service, "DB_PATH", self.db),
            patch.object(document_service, "DB_PATH", self.db),
        ]
        for item in self.patches:
            item.start()
        store.initialize_company_store()
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "INSERT INTO companies(company_id,name,domain,context_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("tenant_a", "Tenant A", "tenant-a.test", "{}", "now", "now"),
            )
            # Employee ID is supplied explicitly to avoid relying on UI provisioning.
            for row in [
                ("employee_1", "tenant_a", "Employee One", "employee1@tenant-a.test", "employee", "HR", "active", "EMP0001"),
                ("admin_1", "tenant_a", "Admin One", "admin1@tenant-a.test", "company_admin", "Administration", "active", "ADM0001"),
                ("employee_2", "tenant_a", "Employee Two", "employee2@tenant-a.test", "employee", "IT", "active", "EMP0002"),
            ]:
                conn.execute(
                    """INSERT INTO company_users
                       (user_id,company_id,name,email,role,department,status,employee_id,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (*row, "now", "now"),
                )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_profile_settings_and_avatar_are_persisted_per_tenant_user(self):
        result = profile_service.save_user_profile_settings(
            "tenant_a", "employee_1", phone="9876543210", location="Vijayawada"
        )
        self.assertEqual(result["status"], "success")
        photo_result = profile_service.save_user_profile_photo(
            "tenant_a", "employee_1", file_name="profile.png", file_data=TINY_PNG,
            mime_type="image/png",
        )
        self.assertEqual(photo_result["status"], "success")
        saved = profile_service.get_user_profile_settings("tenant_a", "employee_1")
        self.assertEqual(saved["phone"], "9876543210")
        self.assertEqual(saved["location"], "Vijayawada")
        self.assertEqual(saved["avatar_data"], TINY_PNG)
        with self.assertRaises(PermissionError):
            profile_service.get_user_profile_settings("tenant_a", "missing_user")

    def test_employee_document_exchange_supports_both_directions_and_admin_review(self):
        employee_upload = document_service.submit_employee_document(
            "tenant_a", "employee_1", "admin_1", title="Project report",
            file_name="report.txt", file_data=b"Project submission content.",
            purpose="Project submission", content_type="text/plain",
        )
        self.assertEqual(employee_upload["status"], "success")
        document_id = employee_upload["document_id"]
        admin_list = document_service.list_company_documents_for_admin("tenant_a", "admin_1")
        self.assertEqual(len(admin_list), 1)
        record = document_service.get_employee_document("tenant_a", "admin_1", document_id)
        self.assertEqual(record["file_data"], b"Project submission content.")
        update = document_service.update_employee_document_status(
            "tenant_a", "admin_1", document_id, status="reviewed", admin_note="Reviewed."
        )
        self.assertEqual(update["status"], "success")

        outbound = document_service.submit_employee_document(
            "tenant_a", "admin_1", "employee_2", title="Reviewed feedback",
            file_name="feedback.txt", file_data=b"Please review.",
            purpose="Feedback", content_type="text/plain",
        )
        self.assertEqual(outbound["status"], "success")
        incoming = document_service.list_user_documents("tenant_a", "employee_2")
        self.assertEqual(len(incoming), 1)
        employee_record = document_service.get_employee_document(
            "tenant_a", "employee_2", outbound["document_id"]
        )
        self.assertEqual(employee_record["file_data"], b"Please review.")
        self.assertEqual(
            document_service.mark_employee_document_read("tenant_a", "employee_2", outbound["document_id"])["status"],
            "success",
        )

    def test_document_exchange_rejects_cross_tenant_or_employee_to_employee_send(self):
        result = document_service.submit_employee_document(
            "tenant_a", "employee_1", "employee_2", title="Private document",
            file_name="a.txt", file_data=b"no", content_type="text/plain",
        )
        self.assertEqual(result["status"], "forbidden")
        with self.assertRaises(PermissionError):
            document_service.submit_employee_document(
                "tenant_other", "employee_1", "admin_1", title="Cross tenant",
                file_name="a.txt", file_data=b"no",
            )

    def test_project_folder_files_are_saved_and_visible_to_admin_for_review(self):
        created = portfolio.create_project(
            "tenant_a", "EMP0001", "AI Project", description="Project submitted for review",
            role_in_project="Developer", start_date="2026-10-01", end_date="2026-12-01",
        )
        self.assertEqual(created["status"], "success")
        project_id = created["project_id"]
        saved = portfolio.save_project_file(
            "tenant_a", "EMP0001", project_id, "src/main.py", b"print('hello')\n"
        )
        self.assertEqual(saved["status"], "success")
        submitted = portfolio.create_project_submission(
            "tenant_a", "EMP0001", "employee_1", project_id, submission_note="Please review."
        )
        self.assertEqual(submitted["status"], "success")
        admin_items = portfolio.list_project_submissions_for_admin("tenant_a", "admin_1")
        self.assertEqual(len(admin_items), 1)
        self.assertEqual(admin_items[0]["project_name"], "AI Project")
        self.assertEqual(admin_items[0]["file_count"], 1)
        files = portfolio.list_project_files_for_admin("tenant_a", "admin_1", project_id)
        self.assertEqual(files[0]["file_name"], "src/main.py")
        data = portfolio.read_project_file_for_admin("tenant_a", "admin_1", saved["file_id"])
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"], b"print('hello')\n")
        reviewed = portfolio.update_project_submission_status(
            "tenant_a", "admin_1", submitted["submission_id"], status="approved", admin_feedback="Looks good."
        )
        self.assertEqual(reviewed["status"], "success")
        user_history = portfolio.list_my_project_submissions("tenant_a", "EMP0001")
        self.assertEqual(user_history[0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
