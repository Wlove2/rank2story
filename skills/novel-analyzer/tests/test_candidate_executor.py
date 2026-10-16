from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import candidate_executor as executor


class CandidateExecutorTests(unittest.TestCase):
    def test_default_model_is_generic_and_configurable(self):
        self.assertEqual(executor.DEFAULT_MODEL, 'your-model-id')

    def test_extracts_direct_and_sse_responses(self):
        direct = '{"choices":[{"message":{"content":"ok"}}]}'
        self.assertEqual(executor.extract_response_content(direct), "ok")
        sse = 'data: {"choices":[{"delta":{"content":"a"}}]}\n' + \
              'data: {"choices":[{"delta":{"content":"b"}}]}\ndata: [DONE]\n'
        self.assertEqual(executor.extract_response_content(sse), "ab")

    def test_extracts_direct_response_with_sse_done_tail(self):
        hybrid = '{"choices":[{"message":{"content":"ok"}}]}\ndata: [DONE]\n\n'
        self.assertEqual(executor.extract_response_content(hybrid), 'ok')
        with self.assertRaisesRegex(ValueError, 'MODEL_RESPONSE_CONTENT_MISSING'):
            executor.extract_response_content(
                '{"choices":[{"message":{"content":"ok"}}]}\nextra'
            )

    def test_json_parser_rejects_trailing_commentary(self):
        self.assertEqual(executor.parse_json_content('```json\n{"a":1}\n```'), {"a": 1})
        with self.assertRaisesRegex(ValueError, "MODEL_JSON_OUTPUT_INVALID"):
            executor.parse_json_content('{"a":1}\nextra')

    def test_materialized_inputs_must_stay_inside_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inside = root / "input.json"
            inside.write_text('{"ok":true}', encoding="utf-8")
            prompt = executor.materialize_action_prompt(
                {"prompt": "task", "input_paths": [str(inside)]}, root,
            )
            self.assertIn('{"ok":true}', prompt)
            outside = root.parent / "outside.json"
            outside.write_text('{}', encoding="utf-8")
            try:
                with self.assertRaisesRegex(ValueError, "ACTION_INPUT_OUTSIDE_RUN"):
                    executor.materialize_action_prompt(
                        {"prompt": "task", "input_paths": [str(outside)]}, root,
                    )
            finally:
                outside.unlink(missing_ok=True)

    def test_default_model_request_uses_only_standard_fields(self):
        variant = ROOT.parents[1] / "variants" / "abc-branch-one" / "skills" / "novel-analyzer" / "scripts" / "candidate_executor.py"
        self.assertEqual((ROOT / "scripts" / "candidate_executor.py").read_bytes(), variant.read_bytes())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bodies = []

            class FakeResponse:
                def __enter__(self): return self
                def __exit__(self, *_args): return False
                def read(self): return b'{"choices":[{"message":{"content":"ready"}}]}'

            def fake_urlopen(request, timeout):
                bodies.append(json.loads(request.data))
                return FakeResponse()

            action = {"job_id": "offline", "role": "story_creator", "prompt": "test",
                      "raw_output": str(root / "raw" / "story.txt")}
            with patch.object(executor.urllib.request, "urlopen", side_effect=fake_urlopen):
                executor.call_model(action, root, base_url="http://localhost:9999/v1",
                                    model="test-model", timeout=1, max_tokens=128, api_key="")
            self.assertEqual(len(bodies), 1)
            self.assertEqual(set(bodies[0]), {"model", "messages", "max_tokens", "stream"})
            self.assertEqual([m["role"] for m in bodies[0]["messages"]], ["system", "user"])

    def test_completed_interrupted_call_is_recovered_without_a_new_call(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "raw" / "atoms.json"
            raw.parent.mkdir()
            raw.write_text('{"atoms":[]}', encoding="utf-8")
            response = raw.with_suffix(raw.suffix + ".response.json")
            response.write_text(json.dumps({"content": '{"atoms":[]}'}) + "\n", encoding="utf-8")
            action = {"job_id": "run-atoms", "raw_output": str(raw)}
            state = {
                "call_budget": {
                    "calls": [{"job_id": "run-atoms", "session_id": "exec-old:001"}],
                },
            }
            recovered_path, recovered_session = executor.recoverable_output(action, state)
            self.assertEqual(recovered_session, "exec-old:001")
            self.assertTrue(Path(recovered_path).samefile(raw))


if __name__ == "__main__":
    unittest.main()
