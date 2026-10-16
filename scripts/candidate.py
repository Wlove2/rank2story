#!/usr/bin/env python3
"""Unified candidate-policy router for Rank2Story.

Policy is selected ONLY when initializing a new run. Existing claims always
execute their own frozen _bundle_snapshot, regardless of current defaults.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
from model_config import load_settings, model_args

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "candidate.json"
POLICIES = {
    "abc_branch_one": {
        "label": "新版 A/B/C 策略 4.4.2（默认）",
        "entry": "variants/abc-branch-one/skills/novel-candidate-portfolio/scripts/candidate.py",
    },
    "quality_strict": {
        "label": "质量严格策略",
        "entry": "skills/novel-candidate-portfolio/scripts/candidate.py",
    },
}
CLAIM_OPERATIONS = {"execute", "status", "resume", "verify"}
HELP = """Rank2Story：多来源市场扫描与候选生成 Skills 工作流

  python scripts/candidate.py config [--config PATH]
  python scripts/candidate.py run [--policy POLICY] [--config PATH] <run 参数...>
  python scripts/candidate.py status|resume|execute|verify --claim <claim.json> [参数...]

  abc_branch_one  4.4.2 新版 A/B/C 策略（默认）
  quality_strict  质量严格策略

config/candidate.json 设置默认 policy。
--policy 仅在创建新 run 时生效；旧 claim 始终使用自己的冻结源码。
run/config/status/resume 不请求模型，execute 需要模型端点与明确操作。
"""

def check_policy(name: str) -> str:
    if name not in POLICIES:
        raise ValueError("POLICY_UNKNOWN: " + str(name))
    return name

def read_config(path: Path) -> str:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("POLICY_CONFIG_UNREADABLE: " + str(exc)) from exc
    if not isinstance(config, dict) or set(config) != {"candidate"}:
        raise ValueError("POLICY_CONFIG_SCHEMA_INVALID")
    selected = config["candidate"]
    if not isinstance(selected, dict) or set(selected) != {"policy"} or not isinstance(selected["policy"], str):
        raise ValueError("POLICY_CONFIG_SCHEMA_INVALID")
    return check_policy(selected["policy"])

def pull_option(argv: list[str], flag: str) -> tuple[list[str], str | None]:
    remaining = []
    value = None
    found = False
    i = 0
    while i < len(argv):
        x = argv[i]
        if x == flag or x.startswith(flag + "="):
            if found:
                raise ValueError("OPTION_DUPLICATE: " + flag)
            found = True
            if x == flag:
                if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                    raise ValueError("OPTION_VALUE_MISSING: " + flag)
                value = argv[i+1]
                i += 2
                continue
            value = x[len(flag)+1:]
            if not value:
                raise ValueError("OPTION_VALUE_MISSING: " + flag)
        else:
            remaining.append(x)
        i += 1
    return remaining, value

def normalize_claim_args(argv: list[str]) -> list[str]:
    """Normalize both --claim PATH and --claim=PATH before snapshot dispatch."""
    normalized: list[str] = []
    seen = False
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--claim" or token.startswith("--claim="):
            if seen:
                raise ValueError("CLAIM_DUPLICATE")
            seen = True
            if token == "--claim":
                if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                    raise ValueError("CLAIM_REQUIRED")
                value = argv[i + 1]
                i += 2
            else:
                value = token.partition("=")[2]
                i += 1
            if not value:
                raise ValueError("CLAIM_REQUIRED")
            normalized.extend(["--claim", value])
        else:
            normalized.append(token)
            i += 1
    if not seen:
        raise ValueError("CLAIM_REQUIRED")
    return normalized


def entry_for(policy: str) -> Path:
    path = ROOT / POLICIES[check_policy(policy)]["entry"]
    if not path.is_file():
        raise ValueError("POLICY_RUNTIME_MISSING: " + str(path))
    return path

def dispatch_plan(argv: list[str]) -> tuple[Path | None, list[str], dict]:
    if not argv or argv[0] in {"help", "-h", "--help"}:
        return None, [], {"help": HELP}
    command = argv[0]
    if command not in CLAIM_OPERATIONS | {"run", "config"}:
        raise ValueError("COMMAND_UNKNOWN: " + command)
    remaining, policy_override = pull_option(argv[1:], "--policy")
    remaining, config_override = pull_option(remaining, "--config")
    if command in CLAIM_OPERATIONS:
        if policy_override is not None or config_override is not None:
            raise ValueError("POLICY_ONLY_ON_NEW_RUN")
        remaining = normalize_claim_args(remaining)
        # The original adapter dispatches to claim/_bundle_snapshot for every
        # claim-bound action. Never use changed config to migrate an old claim.
        return entry_for("quality_strict"), [command, *remaining], {"mode":"claim_frozen"}
    if command == "config" and policy_override is not None:
        raise ValueError("POLICY_OVERRIDE_ONLY_ON_RUN")
    config_path = Path(config_override).expanduser() if config_override else DEFAULT_CONFIG
    policy = check_policy(policy_override) if policy_override is not None else read_config(config_path)
    metadata = {
        "policy":policy,
        "label":POLICIES[policy]["label"],
        "config":str(config_path.resolve()),
        "entry":str(entry_for(policy)),
    }
    if command == "config":
        if remaining:
            raise ValueError("CONFIG_UNEXPECTED_ARGS")
        return None, [], metadata
    return entry_for(policy), [command, *remaining], metadata

def safe_console(text: str, stream=None) -> None:
    """Preserve useful CLI output on Windows CP1252 and other limited consoles."""
    target = sys.stdout if stream is None else stream
    encoding = getattr(target, "encoding", None) or "utf-8"
    # Encoding only the unrepresentable characters as ASCII escapes avoids
    # UnicodeEncodeError without changing UTF-8 output on modern terminals.
    printable = text.encode(encoding, errors="backslashreplace").decode(encoding)
    print(printable, file=target)


def main(args: list[str] | None = None) -> int:
    try:
        entry, passed, metadata = dispatch_plan(list(sys.argv[1:] if args is None else args))
    except ValueError as exc:
        print("POLICY_ERROR: " + str(exc), file=sys.stderr)
        return 2
    if "help" in metadata:
        safe_console(metadata["help"])
        return 0
    if entry is None:
        safe_console(json.dumps(metadata, ensure_ascii=False, indent=2))
        return 0
    if passed[0] == "run":
        safe_console("POLICY_SELECTED: "+metadata["policy"]+" ("+metadata["label"]+")",stream=sys.stderr)
    try:
        if passed[0] == "execute":
            environment = load_settings()
            args_for_executor = model_args(passed, environment)
            return subprocess.run([sys.executable, str(entry), *args_for_executor],
                                  check=False, env=environment).returncode
        return subprocess.run([sys.executable, str(entry), *passed], check=False).returncode
    except (OSError, UnicodeError, ValueError) as exc:
        # Never render environment variables or secret values in error messages.
        code = str(exc).split(":", 1)[0] if isinstance(exc, ValueError) else type(exc).__name__
        print("EXECUTOR_START_FAILED: " + code, file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
