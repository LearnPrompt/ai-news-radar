"""Tests for the shared LLM provider resolver.

The pipeline's LLM features can talk to DeepSeek (default) or, when
``ORCAROUTER_API_KEY`` is set, to the OrcaRouter gateway through the same
OpenAI-compatible chat-completions endpoint.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.llm_provider import (
    DEEPSEEK_API_BASE_URL,
    DEEPSEEK_DEFAULT_MODEL,
    ORCAROUTER_API_BASE_URL,
    ORCAROUTER_DEFAULT_MODEL,
    llm_api_key_available,
    resolve_llm_config,
)


class TestResolveLLMConfig(unittest.TestCase):
    def test_defaults_to_deepseek_without_keys(self):
        with patch.dict("os.environ", {}, clear=True):
            cfg = resolve_llm_config()
        self.assertEqual(cfg["api_key"], "")
        self.assertEqual(cfg["base_url"], DEEPSEEK_API_BASE_URL)
        self.assertEqual(cfg["model"], DEEPSEEK_DEFAULT_MODEL)

    def test_deepseek_key_selects_deepseek(self):
        with patch.dict(
            "os.environ", {"DEEPSEEK_API_KEY": "sk-test", "DEEPSEEK_MODEL": "deepseek-custom"}, clear=True
        ):
            cfg = resolve_llm_config()
        self.assertEqual(cfg["api_key"], "sk-test")
        self.assertEqual(cfg["base_url"], DEEPSEEK_API_BASE_URL)
        self.assertEqual(cfg["model"], "deepseek-custom")

    def test_orcarouter_key_takes_precedence(self):
        with patch.dict(
            "os.environ",
            {
                "DEEPSEEK_API_KEY": "sk-deepseek",
                "ORCAROUTER_API_KEY": "sk-orca-test",
            },
            clear=True,
        ):
            cfg = resolve_llm_config()
        self.assertEqual(cfg["api_key"], "sk-orca-test")
        self.assertEqual(cfg["base_url"], ORCAROUTER_API_BASE_URL)
        self.assertEqual(cfg["model"], ORCAROUTER_DEFAULT_MODEL)

    def test_orcarouter_overrides(self):
        with patch.dict(
            "os.environ",
            {
                "ORCAROUTER_API_KEY": "sk-orca-test",
                "ORCAROUTER_API_BASE_URL": "https://example.com/v1",
                "ORCAROUTER_MODEL": "orcarouter/auto",
            },
            clear=True,
        ):
            cfg = resolve_llm_config()
        self.assertEqual(cfg["base_url"], "https://example.com/v1")
        self.assertEqual(cfg["model"], "orcarouter/auto")

    def test_trailing_slash_on_base_url_is_stripped(self):
        with patch.dict(
            "os.environ",
            {
                "DEEPSEEK_API_KEY": "sk-test",
                "DEEPSEEK_API_BASE_URL": "https://api.deepseek.com/",
            },
            clear=True,
        ):
            cfg = resolve_llm_config()
        self.assertEqual(cfg["base_url"], "https://api.deepseek.com")

    def test_default_model_override_for_persona(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            cfg = resolve_llm_config(default_model="deepseek-chat")
        self.assertEqual(cfg["model"], "deepseek-chat")

    def test_api_key_available(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(llm_api_key_available())
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            self.assertTrue(llm_api_key_available())
        with patch.dict("os.environ", {"ORCAROUTER_API_KEY": "sk-orca-test"}, clear=True):
            self.assertTrue(llm_api_key_available())


if __name__ == "__main__":
    unittest.main()
