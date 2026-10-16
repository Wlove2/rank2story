from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "examples"))
import check_model_endpoint as checker


class Response(io.BytesIO):
    status = 200


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.request = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return Response(json.dumps(self.response).encode("utf8"))


class EndpointProbeTests(unittest.TestCase):
    def test_ready_nonempty_content_and_secret_never_logged(self):
        transport = FakeOpener({
            "model": "test-model",
            "choices": [{"message": {"content": "READY"}, "finish_reason": "stop"}],
        })
        outcome = checker.check_endpoint(
            base_url="http://localhost:9999/v1", model="test-model",
            api_key="top-secret", opener=transport,
        )
        self.assertTrue(outcome["ready"])
        self.assertEqual(outcome["http_status"], 200)
        self.assertNotIn("top-secret", json.dumps(outcome))
        self.assertEqual(
            transport.request.get_header("Authorization"), "Bearer top-secret"
        )

    def test_reasoning_only_http200_is_not_ready(self):
        transport = FakeOpener({
            "choices": [{"message": {"content": "", "reasoning_content": "reasoning"}, "finish_reason": "length"}],
        })
        outcome = checker.check_endpoint(
            base_url="http://localhost:9999/v1", model="test-model", opener=transport
        )
        self.assertFalse(outcome["ready"])
        self.assertEqual(outcome["reasoning_chars"], 9)
        self.assertEqual(outcome["finish_reason"], "length")

    def test_missing_key_env_fails_closed(self):
        output = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            code = checker.main([
                "--base-url", "http://localhost:9999/v1", "--model", "test",
                "--api-key-env", "MODEL_KEY_NOT_SET",
            ])
        self.assertEqual(code, 2)
        self.assertIn("MODEL_API_KEY_ENV_MISSING", output.getvalue())

    def test_invalid_url_is_rejected_before_network(self):
        with self.assertRaisesRegex(ValueError, "MODEL_BASE_URL_INVALID"):
            checker.check_endpoint(base_url="file:///tmp/secret", model="test")


if __name__ == "__main__":
    unittest.main()
