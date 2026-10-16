"""Unit tests for bounded AI provider failover and cooldown behavior."""
import time
import unittest
from unittest.mock import patch

from core import llm


class ProviderFailoverTests(unittest.TestCase):
    def setUp(self):
        with llm._PROVIDER_COOLDOWN_LOCK:
            self.previous_cooldowns = dict(llm._PROVIDER_COOLDOWNS)
            llm._PROVIDER_COOLDOWNS.clear()
        self.groq_sdk = llm.Groq
        self.groq_key = llm.GROQ_API_KEY
        self.gemini_key = llm.GEMINI_API_KEY
        self.provider = llm.LLM_PROVIDER
        llm.GROQ_API_KEY = "test-groq-key"
        llm.GEMINI_API_KEY = "test-gemini-key"
        llm.LLM_PROVIDER = "groq"

    def tearDown(self):
        llm.Groq = self.groq_sdk
        llm.GROQ_API_KEY = self.groq_key
        llm.GEMINI_API_KEY = self.gemini_key
        llm.LLM_PROVIDER = self.provider
        with llm._PROVIDER_COOLDOWN_LOCK:
            llm._PROVIDER_COOLDOWNS.clear()
            llm._PROVIDER_COOLDOWNS.update(self.previous_cooldowns)

    def test_quota_and_503_failures_enter_cooldown_and_are_not_retried(self):
        groq_error = RuntimeError(
            "Error code: 429 - token limit tokens per day; try again in 11m19.968s"
        )
        gemini_error = RuntimeError("Gemini API error 503: high demand")
        with patch.object(llm, "_call_groq", side_effect=groq_error) as groq_call, \
             patch.object(llm, "_call_gemini", side_effect=gemini_error) as gemini_call:
            start = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, "deterministic fallback is active"):
                llm._call_llm("test prompt", timeout=30)
            first_duration = time.monotonic() - start

            groq_call.assert_called_once()
            gemini_call.assert_called_once()
            self.assertLessEqual(groq_call.call_args.kwargs["timeout"], 6)
            self.assertGreaterEqual(llm._PROVIDER_COOLDOWNS["groq"]["until"] - time.monotonic(), 600)

            # The next workflow stage must skip both unavailable providers.
            start = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, "temporary cooldown"):
                llm._call_llm("second prompt", timeout=30)
            second_duration = time.monotonic() - start
            self.assertLess(second_duration, max(0.1, first_duration + 0.05))
            groq_call.assert_called_once()
            gemini_call.assert_called_once()

    def test_healthy_fallback_provider_is_used_when_primary_is_cooling(self):
        with llm._PROVIDER_COOLDOWN_LOCK:
            llm._PROVIDER_COOLDOWNS["groq"] = {
                "until": time.monotonic() + 600,
                "kind": "rate limited (429)",
            }
        with patch.object(llm, "_call_groq") as groq_call, \
             patch.object(llm, "_call_gemini", return_value='{"ok": true}') as gemini_call:
            result, provider = llm._call_llm("test prompt")
        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(provider, "gemini")
        groq_call.assert_not_called()
        gemini_call.assert_called_once()

    def test_missing_groq_sdk_does_not_prevent_gemini_fallback(self):
        llm.Groq = None
        with patch.object(llm, "_call_gemini", return_value='{"ok": true}') as gemini_call:
            result, provider = llm._call_llm("test prompt")
        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(provider, "gemini")
        gemini_call.assert_called_once()

    def test_provider_error_summary_does_not_expose_full_upstream_payload(self):
        with patch.object(
            llm,
            "_call_groq",
            side_effect=RuntimeError(
                "429 token limit tokens per day org_PRIVATE_ID; try again in 11m19.968s"
            ),
        ), patch.object(llm, "_call_gemini", side_effect=RuntimeError("503 high demand")):
            with self.assertRaises(RuntimeError) as raised:
                llm._call_llm("test prompt")
        self.assertNotIn("org_PRIVATE_ID", str(raised.exception))
        self.assertNotIn("198677", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
