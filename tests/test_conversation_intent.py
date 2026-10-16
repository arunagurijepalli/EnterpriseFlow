"""Regression tests for separating new topics from pending clarification."""
import unittest
from core.conversation_intent import (
    is_clear_new_request_during_clarification,
    is_simple_greeting,
    pending_lookup_requested,
)


class ConversationIntentTests(unittest.TestCase):
    def test_network_request_interrupts_pending_leave_date_clarification(self):
        self.assertTrue(is_clear_new_request_during_clarification(
            "my wifi was not connecting", "leave request"
        ))

    def test_pending_approvals_query_is_new_read_only_task(self):
        self.assertTrue(pending_lookup_requested("my pending approvals"))
        self.assertTrue(is_clear_new_request_during_clarification(
            "my pending approvals", "leave request"
        ))

    def test_explicit_two_dates_are_a_slot_reply(self):
        self.assertFalse(is_clear_new_request_during_clarification(
            "20-10-2026, 22-10-2026", "leave request"
        ))

    def test_leave_policy_question_is_new_read_only_task(self):
        self.assertTrue(is_clear_new_request_during_clarification(
            "What is our leave policy?", "leave request"
        ))

    def test_simple_greeting_is_local(self):
        self.assertTrue(is_simple_greeting("hi"))
        self.assertFalse(is_simple_greeting("hi, I need a laptop"))

    def test_topic_change_does_not_continue_unrelated_clarification(self):
        self.assertTrue(is_clear_new_request_during_clarification(
            "my wifi was not connecting", "leave request"
        ))
        self.assertTrue(is_clear_new_request_during_clarification(
            "What is our leave policy?", "leave request"
        ))


if __name__ == "__main__":
    unittest.main()
