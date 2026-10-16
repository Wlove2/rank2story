"""No-network unit tests for the unified, claim-safe candidate policy switch."""
from __future__ import annotations
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/"scripts"/"candidate.py"
spec=importlib.util.spec_from_file_location("unified_candidate_policy",ENTRY)
assert spec and spec.loader
policy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

class PolicySwitchTests(unittest.TestCase):
    def test_repo_default_is_new_abc_policy(self):
        which=policy.read_config(policy.DEFAULT_CONFIG)
        self.assertEqual(which,"abc_branch_one")
        target,fw,details=policy.dispatch_plan(["run","--base-root","private","--packet","frozen.json","--lane","long"])
        self.assertEqual(fw[0],"run")
        self.assertEqual(details["policy"],"abc_branch_one")
        self.assertIn("variants/abc-branch-one",target.as_posix())

    def test_override_selects_original_quality_strict(self):
        target,forwarded,report=policy.dispatch_plan(["run","--policy","quality_strict","--base-root","x"])
        self.assertEqual(report["policy"],"quality_strict")
        self.assertTrue(target.as_posix().endswith("skills/novel-candidate-portfolio/scripts/candidate.py"))
        self.assertNotIn("--policy",forwarded)

    def test_json_config_file_switches_selected_controller(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"configuration.json"
            f.write_text(json.dumps({"candidate":{"policy":"quality_strict"}}),encoding="utf-8")
            _,_,meta=policy.dispatch_plan(["config","--config",str(f)])
            self.assertEqual(meta["policy"],"quality_strict")
            _,_,meta=policy.dispatch_plan(["run","--config",str(f)])
            self.assertEqual(meta["policy"],"quality_strict")
            _,_,meta=policy.dispatch_plan(["run","--config",str(f),"--policy","abc_branch_one"])
            self.assertEqual(meta["policy"],"abc_branch_one")

    def test_bad_config_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"bad.json"
            for raw in ("{}",'{"candidate":{"policy":"undefined"}}','{"candidate":{"policy":"abc_branch_one","ignored":"x"}}','{unparsable'):
                with self.subTest(raw=raw):
                    f.write_text(raw,encoding="utf-8")
                    with self.assertRaises(ValueError):
                        policy.dispatch_plan(["run","--config",str(f)])
            with self.assertRaises(ValueError):
                policy.dispatch_plan(["run","--policy","invalid"])

    def test_claim_bound_commands_ignore_default_even_when_policy_changes(self):
        for operation in ("execute","status","resume","verify"):
            with self.subTest(operation=operation):
                with patch.object(policy,"read_config",side_effect=AssertionError("READ_CONFIG_ON_CLAIM")):
                    target,forwarded,meta=policy.dispatch_plan([operation,"--claim","a/claim.json"])
                self.assertEqual(meta,{"mode":"claim_frozen"})
                self.assertEqual(forwarded,[operation,"--claim","a/claim.json"])
                self.assertNotIn("variants",target.as_posix())

    def test_claim_equals_syntax_normalizes_for_frozen_dispatch(self):
        for operation in ("execute", "status", "resume", "verify"):
            with self.subTest(operation=operation):
                target, forwarded, meta = policy.dispatch_plan([operation, "--claim=run/claim.json"])
                self.assertEqual(forwarded, [operation, "--claim", "run/claim.json"])
                self.assertEqual(meta, {"mode": "claim_frozen"})
                self.assertEqual(target, policy.entry_for("quality_strict"))
        for invalid in (["status", "--claim="], ["status", "--claim"],
                        ["status", "--claim=a", "--claim", "b"]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                policy.dispatch_plan(invalid)

    def test_claim_equals_syntax_reaches_frozen_snapshot_without_model(self):
        with tempfile.TemporaryDirectory() as folder:
            claim = Path(folder) / "candidate_run_claim.json"
            snapshot = Path(folder) / "_bundle_snapshot"
            snapshot.mkdir()
            (snapshot / "candidate_workflow.py").write_text("print('FROZEN_CLAIM_ROUTED')\n", encoding="utf-8")
            process = subprocess.run(
                [sys.executable, str(ENTRY), "status", f"--claim={claim}"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertIn("FROZEN_CLAIM_ROUTED", process.stdout)

    def test_claim_bound_policy_override_is_rejected(self):
        for command in ("execute","verify","status","resume"):
            with self.subTest(command=command):
                with self.assertRaisesRegex(ValueError,"POLICY_ONLY_ON_NEW_RUN"):
                    policy.dispatch_plan([command,"--claim","abc.json","--policy","quality_strict"])
        with self.assertRaisesRegex(ValueError,"CLAIM_REQUIRED"):
            policy.dispatch_plan(["execute"])
        with self.assertRaises(ValueError):
            policy.dispatch_plan(["config","--policy","quality_strict"])

    def test_no_duplicated_or_empty_cli_flags(self):
        for args in (
            ["run","--policy","abc_branch_one","--policy","quality_strict"],
            ["run","--policy"],
            ["run","--policy="],
            ["run","--config","--base-root","x"],
        ):
            with self.subTest(args=args),self.assertRaises(ValueError):
                policy.dispatch_plan(args)

    def test_dispatch_calls_exact_policy_path_without_model_itself(self):
        with patch.object(policy.subprocess,"run",return_value=subprocess.CompletedProcess([],0)) as subprocess_call:
            self.assertEqual(policy.main(["run","--policy","quality_strict","--base-root","dummy"]),0)
        argv=subprocess_call.call_args.args[0]
        self.assertEqual(Path(argv[1]),policy.entry_for("quality_strict"))
        self.assertNotIn("--policy",argv)
        with patch.object(policy.subprocess,"run",return_value=subprocess.CompletedProcess([],7)) as subprocess_call:
            self.assertEqual(policy.main(["status","--claim","dummy"]),7)
        argv=subprocess_call.call_args.args[0]
        self.assertEqual(Path(argv[1]),policy.entry_for("quality_strict"))
        self.assertEqual(argv[-3:],["status","--claim","dummy"])

    def test_execute_loads_untracked_model_configuration_without_secret_in_args(self):
        config={
            "MODEL_BASE_URL":"https://example.invalid/v1",
            "MODEL_ID":"configured-model",
            "MODEL_API_KEY":"secret-not-for-argv"
        }
        with patch.object(policy, "load_settings", return_value=config):
            with patch.object(policy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as call:
                self.assertEqual(policy.main(["execute","--claim","example.json"]),0)
        args=call.call_args.args[0]
        self.assertIn("https://example.invalid/v1",args)
        self.assertIn("configured-model",args)
        self.assertIn("--api-key-env",args)
        self.assertIn("MODEL_API_KEY",args)
        self.assertNotIn("secret-not-for-argv"," ".join(args))
        self.assertEqual(call.call_args.kwargs["env"]["MODEL_API_KEY"],"secret-not-for-argv")

    def test_config_command_never_starts_subprocess(self):
        with patch.object(policy.subprocess,"run",side_effect=AssertionError("UNEXPECTED_EXECUTION")):
            self.assertEqual(policy.main(["config"]),0)
            # GitHub Windows runners may use CP1252 instead of UTF-8. Confirm
            # both commands fail-safe without requiring a console codepage tweak.
            raw=io.BytesIO()
            console=io.TextIOWrapper(raw,encoding="cp1252",errors="strict",write_through=True)
            with patch.object(sys,"stdout",console):
                self.assertEqual(policy.main(["config"]),0)
                self.assertEqual(policy.main(["--help"]),0)
            content=raw.getvalue().decode("cp1252")
            self.assertIn("abc_branch_one",content)
            self.assertIn("quality_strict",content)
            console.detach()

    def test_top_level_cli_help(self):
        proc=subprocess.run([sys.executable,str(ENTRY),"--help"],capture_output=True,text=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn("abc_branch_one",proc.stdout)
        self.assertIn("quality_strict",proc.stdout)

if __name__=="__main__":
    unittest.main()
