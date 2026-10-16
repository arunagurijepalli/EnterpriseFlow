"""Acceptance coverage for the requested HR/IT natural-language service catalog."""
from __future__ import annotations

import unittest

from core.service_catalog import classify_read_only_route, classify_specialized_request


class ServiceCatalogAcceptanceV12Tests(unittest.TestCase):
    def route(self, message):
        return classify_read_only_route(message, None) or classify_specialized_request(message)

    def assert_action_route(self, message, area, intent, tool=None):
        route = self.route(message)
        self.assertIsNotNone(route, f"No route for: {message}")
        self.assertEqual(route.get("department"), area, message)
        self.assertEqual(route.get("intent"), intent, message)
        self.assertEqual(route.get("request_category"), "enterprise_action", message)
        self.assertTrue(route.get("requires_action"), message)
        if tool:
            self.assertEqual((route.get("tools") or [None])[0], tool, message)
        return route

    def assert_read_only_route(self, message, area, intent):
        route = self.route(message)
        self.assertIsNotNone(route, f"No read-only route for: {message}")
        self.assertEqual(route.get("department"), area, message)
        self.assertEqual(route.get("intent"), intent, message)
        self.assertEqual(route.get("request_category"), "information_request", message)
        self.assertFalse(route.get("requires_action"), message)

    def test_general_information_is_read_only(self):
        self.assert_read_only_route(
            "What tool should I use to learn Python?",
            "Knowledge", "general_learning_guidance",
        )
        self.assert_read_only_route(
            "What is our leave policy?", "HR", "hr_policy_information"
        )
        self.assert_read_only_route(
            "My system is having a network problem.",
            "IT", "it_troubleshooting_guidance",
        )
        self.assert_read_only_route(
            "my wifi was not connecting", "IT", "it_troubleshooting_guidance"
        )
        self.assert_read_only_route(
            "The office printer is not working.",
            "IT", "it_troubleshooting_guidance",
        )
        self.assert_read_only_route(
            "I have a question about my payslip and salary deductions.",
            "HR", "payroll_compensation_information",
        )

    def test_it_request_catalog_routes_all_listed_categories(self):
        cases = [
            ("Create an IT ticket for my network problem.", "network_connectivity", "create_ticket"),
            ("I need Python installed on my company laptop.", "software_installation_access", "software_service"),
            ("I need help resetting my password.", "password_reset", "password_access_service"),
            ("I need help resetting my MFA authentication.", "mfa_2fa_support", "password_access_service"),
            ("I accidentally deleted an important work file. I need help recovering it.", "data_recovery_backup", "create_ticket"),
            ("I need to report a suspected phishing email.", "security_incident", "create_ticket"),
            ("I need help connecting to the company VPN.", "network_connectivity", "create_ticket"),
            ("I need a business website reviewed for allowlisting.", "software_whitelisting", "software_service"),
            ("I want to enroll my personal phone for company email access.", "byod_mdm_enrollment", "create_ticket"),
            ("I want to request a scheduled company software upgrade.", "change_management", "create_ticket"),
            ("I need to request removal of access for an employee who is leaving.", "offboarding_access_removal", "create_ticket"),
        ]
        for message, intent, tool in cases:
            with self.subTest(message=message):
                self.assert_action_route(message, "IT", intent, tool)

    def test_hr_request_catalog_routes_all_listed_categories(self):
        cases = [
            ("I need to correct my attendance record for yesterday.", "attendance_correction", "hr_general_request_service"),
            ("I need help completing my employee onboarding documents.", "employee_onboarding_request", "hr_general_request_service"),
            ("I am resigning and need help with my offboarding process.", "employee_offboarding_request", "hr_general_request_service"),
            ("I need an employment verification letter for a bank loan.", "employment_verification_letter", "hr_general_request_service"),
            ("I want to enroll in the company health insurance plan.", "insurance_enrollment", "hr_general_request_service"),
            ("I need help submitting a health insurance claim.", "insurance_claim", "hr_general_request_service"),
            ("I want to request a performance review meeting.", "performance_appraisal_request", "hr_general_request_service"),
            ("I want to report a workplace grievance to HR.", "employee_grievance", "hr_grievance_service"),
            ("I need to report a suspected ethics violation confidentially.", "whistleblower_ethics", "hr_grievance_service"),
            ("I want to enroll in a technical training course.", "professional_training_request", "hr_training_service"),
            ("I want to submit a travel expense reimbursement.", "expense_reimbursement", "hr_general_request_service"),
            ("I want to request a transfer to another company office location.", "relocation_mobility", "hr_general_request_service"),
            ("I need to request a workplace accommodation.", "medical_accommodation", "hr_general_request_service"),
            ("I need HR assistance with employment visa documentation.", "visa_immigration_support", "hr_general_request_service"),
        ]
        for message, intent, tool in cases:
            with self.subTest(message=message):
                route = self.assert_action_route(message, "HR", intent, tool)
                self.assertTrue(route.get("details", {}).get("service_request_needs_external_integration"))

    def test_leave_application_remains_on_dedicated_leave_workflow(self):
        message = "I want to apply for sick leave for two days next week."
        self.assertIsNone(classify_specialized_request(message))
        self.assertIsNone(classify_read_only_route(message, None))

    def test_request_prompts_do_not_claim_external_actions_are_completed(self):
        for message in (
            "I need help resetting my MFA authentication.",
            "I accidentally deleted an important work file. I need help recovering it.",
            "I want to enroll my personal phone for company email access.",
            "I have a question about my payslip and salary deductions.",
        ):
            with self.subTest(message=message):
                route = self.route(message)
                self.assertIsNotNone(route)
                details = route.get("details") or {}
                if route.get("request_category") == "enterprise_action":
                    self.assertTrue(route.get("requires_action"))
                    self.assertTrue(details.get("service_request_needs_external_integration"))


if __name__ == "__main__":
    unittest.main()
