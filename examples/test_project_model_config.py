"""Offline tests for private project .env with secure, overridable model routing."""
from __future__ import annotations
import tempfile,importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import sys,subprocess

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import model_config as c

class ProjectModelConfigTests(unittest.TestCase):
    def test_env_file_is_optional_and_model_placeholders_are_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            f=Path(folder)/".env"
            f.write_text("# settings\nMODEL_BASE_URL=https://your-endpoint.example/v1\nMODEL_ID=your-model-id\nMODEL_API_KEY=\n",encoding="utf-8")
            data=c.load_settings(f,environ={})
            self.assertNotIn("MODEL_BASE_URL",data)
            self.assertNotIn("MODEL_ID",data)
            self.assertNotIn("MODEL_API_KEY",data)

    def test_quoted_values_and_process_environment_priority(self):
        with tempfile.TemporaryDirectory() as folder:
            f=Path(folder)/".env"
            f.write_text('MODEL_BASE_URL="https://service.invalid/v1"\nMODEL_ID="model-a"\nMODEL_API_KEY="file-secret"\n',encoding="utf-8")
            data=c.load_settings(f,environ={"MODEL_API_KEY":"session-secret"})
            self.assertEqual(data["MODEL_BASE_URL"],"https://service.invalid/v1")
            self.assertEqual(data["MODEL_ID"],"model-a")
            self.assertEqual(data["MODEL_API_KEY"],"session-secret")
            self.assertEqual(data["UNSET"] if "UNSET" in data else None,None)

    def test_unrecognized_env_settings_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            f=Path(folder)/".env"
            f.write_text("HIDDEN_SHELL_COMMAND=do-not-run\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"MODEL_ENV_UNKNOWN_KEY"):
                c.load_settings(f,environ={})

    def test_model_flags_never_contain_secret(self):
        args=c.model_args(["execute","--claim","file.json"],{
            "MODEL_BASE_URL":"https://example.invalid/v1","MODEL_ID":"hello-model","MODEL_API_KEY":"not-a-real-secret"})
        self.assertIn("--api-key-env",args)
        self.assertIn("MODEL_API_KEY",args)
        self.assertNotIn("not-a-real-secret"," ".join(args))
        self.assertIn("https://example.invalid/v1",args)
        self.assertIn("hello-model",args)

    def test_explicit_cli_options_take_precedence(self):
        original=["execute","--claim","file.json","--base-url","https://custom.invalid/v1","--model","custom"]
        out=c.model_args(original,{
            "MODEL_BASE_URL":"https://file.invalid/v1","MODEL_ID":"some-other","MODEL_API_KEY":""})
        self.assertEqual(out,original)

    def test_execute_requires_model_config_when_unspecified(self):
        with self.assertRaisesRegex(ValueError,"MODEL_BASE_URL_MISSING"):
            c.model_args(["execute","--claim","file.json"],{})
        with self.assertRaisesRegex(ValueError,"MODEL_ID_MISSING"):
            c.model_args(["execute","--claim","file.json"],{"MODEL_BASE_URL":"https://host.invalid/v1"})

if __name__=="__main__":
    unittest.main()
