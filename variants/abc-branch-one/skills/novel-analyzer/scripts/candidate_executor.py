#!/usr/bin/env python3
"""Deterministic OpenAI-compatible executor for candidate workflow actions."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import candidate_workflow as workflow


PLAIN_TEXT_ROLES = {"story_creator", "story_editor"}
DEFAULT_MODEL = 'your-model-id'


def extract_response_content(raw_text: str) -> str:
    stripped = raw_text.strip()
    envelopes: list[dict[str, Any]] = []
    streamed_parts: list[str] = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        value = line[5:].strip()
        if not value or value == "[DONE]":
            continue
        try:
            envelope = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(envelope, dict):
            envelopes.append(envelope)
            choices = envelope.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                if isinstance(delta.get("content"), str):
                    streamed_parts.append(delta["content"])
    if streamed_parts:
        return "".join(streamed_parts)
    if not envelopes:
        try:
            value = json.loads(stripped)
            if isinstance(value, dict):
                envelopes.append(value)
        except json.JSONDecodeError:
            try:
                value, end = json.JSONDecoder().raw_decode(stripped)
            except json.JSONDecodeError:
                value, end = None, 0
            trailing = stripped[end:].strip()
            if (
                isinstance(value, dict)
                and trailing
                and all(line.strip() == 'data: [DONE]' for line in trailing.splitlines())
            ):
                envelopes.append(value)
    for envelope in reversed(envelopes):
        choices = envelope.get("choices") or []
        if not choices:
            continue
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
    raise ValueError("MODEL_RESPONSE_CONTENT_MISSING")


def strip_json_comments(text: str) -> str:
    """Strip // line comments that sit outside JSON string literals.

    Models sometimes annotate JSON with trailing // comments (e.g.
    `"atom_type": "identify_fantasy",  // 修正为 identity_fantasy`), which
    standard json.loads rejects. This walks line-by-line tracking string
    state so URLs like "https://..." inside values are preserved.
    """
    out: list[str] = []
    for line in text.splitlines():
        in_string = False
        escape = False
        cut = len(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    cut = i
                    break
            i += 1
        out.append(line[:cut].rstrip())
    return "\n".join(out)


def parse_json_content(content: str) -> dict[str, Any] | list[Any]:
    text = content.strip().lstrip("\ufeff")
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            return parsed
    except json.JSONDecodeError:
        pass
    # Models sometimes emit trailing // comments — strip and retry
    stripped = strip_json_comments(text)
    if stripped != text:
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            pass
    # Models sometimes emit invalid escapes (e.g. \' ) — fix and retry
    repaired = text.replace("\\'", "'")
    if repaired != text:
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            pass
    decoder = json.JSONDecoder()
    for position, character in enumerate(text):
        if character not in "[{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[position:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)) and not text[position + end:].strip():
            return parsed
    raise ValueError("MODEL_JSON_OUTPUT_INVALID")


def endpoint_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    return value if value.endswith("/chat/completions") else value + "/chat/completions"


def materialize_action_prompt(action: dict[str, Any], output_dir: Path) -> str:
    sections = [
        action["prompt"],
        "The executor, not you, writes files. Return only the requested content in this response.",
    ]
    for raw_path in action.get("input_paths") or []:
        resolved = workflow.canonical_path(Path(raw_path))
        path = workflow.win_long_path(resolved)
        try:
            relative = resolved.relative_to(workflow.canonical_path(output_dir))
        except ValueError as exc:
            raise ValueError("ACTION_INPUT_OUTSIDE_RUN") from exc
        if not path.is_file():
            raise ValueError(f"ACTION_INPUT_MISSING:{relative.as_posix()}")
        sections.extend([
            f"\n--- BEGIN FROZEN INPUT: {relative.as_posix()} ---",
            path.read_text(encoding="utf-8"),
            f"--- END FROZEN INPUT: {relative.as_posix()} ---",
        ])
    return "\n".join(sections)


def call_model(
    action: dict[str, Any], output_dir: Path, *, base_url: str, model: str,
    timeout: int, max_tokens: int, api_key: str,
) -> tuple[str, str]:
    plain_text = action["role"] in PLAIN_TEXT_ROLES
    system = (
        "Follow the frozen task exactly. Return only plain text; no commentary or markdown fences."
        if plain_text else
        "Follow the frozen task exactly. Return one valid JSON value only; no commentary or markdown fences."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": materialize_action_prompt(action, output_dir)},
        ],
        "max_tokens": max_tokens,
        "stream": False,
        # Keep provider-specific request options opt-in; use standard fields by default.
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        endpoint_url(base_url), data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_response = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"MODEL_HTTP_ERROR:{exc.code}:{detail}") from exc
    content = extract_response_content(raw_response).strip()
    if not content:
        raise ValueError("MODEL_RESPONSE_EMPTY")
    canonical_raw_path = workflow.canonical_path(Path(action["raw_output"]))
    raw_path = workflow.win_long_path(canonical_raw_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    response_record = raw_path.with_suffix(raw_path.suffix + ".response.json")
    response_record.write_text(json.dumps({
        "job_id": action["job_id"], "role": action["role"], "model": model,
        "request": payload, "raw_response": raw_response, "content": content,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if plain_text:
        raw_path.write_text(content + "\n", encoding="utf-8")
    else:
        parsed = parse_json_content(content)
        raw_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(canonical_raw_path), str(
        canonical_raw_path.with_suffix(canonical_raw_path.suffix + ".response.json")
    )


def recoverable_output(action: dict[str, Any], state: dict[str, Any]) -> tuple[str, str] | None:
    """Recover a completed model response that survived an interrupted executor."""
    raw_path = workflow.canonical_path(Path(action["raw_output"]))
    response_path = raw_path.with_suffix(raw_path.suffix + ".response.json")
    if not workflow.win_long_path(raw_path).is_file() or not workflow.win_long_path(response_path).is_file():
        return None
    prior_call = next(
        (
            row for row in reversed((state.get("call_budget") or {}).get("calls") or [])
            if row.get("job_id") == action["job_id"] and row.get("session_id")
        ),
        None,
    )
    if prior_call is None:
        return None
    return str(raw_path), str(prior_call["session_id"])


def run_executor(
    claim_path: Path, *, base_url: str, model: str, timeout: int = 600,
    max_tokens: int = 12000, max_concurrency: int = 3, api_key: str = "",
) -> dict[str, Any]:
    claim_path = claim_path.resolve()
    claim, _, _, output_dir, _ = workflow.validate_claim(claim_path)
    executor_id = f"exec-{uuid.uuid4().hex}"
    workflow.acquire_executor_lease(claim_path, executor_id, model)
    try:
        while True:
            workflow.heartbeat_executor(claim_path, executor_id)
            state = workflow.resume(claim_path)
            if state["status"] in workflow.TERMINAL:
                return workflow.verify_delivery(claim_path) if state["status"] == "awaiting_user_choice" else state
            actions = list(state.get("actions") or [])[:max_concurrency]
            if not actions:
                raise RuntimeError("EXECUTOR_NO_ACTIONS_FOR_NONTERMINAL_RUN")
            recovered = False
            for action in actions:
                completed = recoverable_output(action, state)
                if completed is None:
                    continue
                raw_path, session_id = completed
                workflow.append_manifest(output_dir, {
                    "event": "interrupted_call_recovered",
                    "job_id": action["job_id"],
                    "session_id": session_id,
                })
                workflow.ingest_job(claim_path, action["job_id"], session_id, Path(raw_path))
                recovered = True
            if recovered:
                continue
            calls_started = int((state.get("call_budget") or {}).get("calls_started", 0))
            hard_fuse = int((state.get("call_budget") or {}).get("hard_fuse", workflow.CALL_FUSE_THRESHOLD))
            if calls_started + len(actions) > hard_fuse:
                return workflow.abort_for_executor(claim_path, "LLM_CALL_FUSE_REACHED")
            scheduled: list[tuple[dict[str, Any], str]] = []
            for action in actions:
                session_id = f"{executor_id}:{calls_started + len(scheduled) + 1:03d}"
                workflow.record_executor_call(claim_path, executor_id, action, session_id)
                scheduled.append((action, session_id))
            stop_heartbeat = threading.Event()

            def keep_lease_alive() -> None:
                while not stop_heartbeat.wait(30):
                    workflow.heartbeat_executor(claim_path, executor_id)

            heartbeat_thread = threading.Thread(target=keep_lease_alive, name="candidate-lease-heartbeat")
            heartbeat_thread.start()
            try:
                with ThreadPoolExecutor(max_workers=min(max_concurrency, len(scheduled))) as pool:
                    futures = {
                        pool.submit(
                            call_model, action, output_dir, base_url=base_url, model=model,
                            timeout=timeout, max_tokens=max_tokens, api_key=api_key,
                        ): (action, session_id)
                        for action, session_id in scheduled
                    }
                    for future in as_completed(futures):
                        action, session_id = futures[future]
                        raw_path, _ = future.result()
                        current_state = workflow.load_json(output_dir / "controller_state.json")
                        current_job = next(
                            (job for job in current_state.get("jobs", []) if job.get("job_id") == action["job_id"]),
                            None,
                        )
                        if current_job is None or current_job.get("status") != "pending":
                            workflow.append_manifest(output_dir, {
                                "event": "batch_result_skipped",
                                "job_id": action["job_id"],
                                "reason": "job_no_longer_pending",
                            })
                            continue
                        workflow.ingest_job(claim_path, action["job_id"], session_id, Path(raw_path))
            finally:
                stop_heartbeat.set()
                heartbeat_thread.join()
    except Exception as exc:
        workflow.release_executor_lease(claim_path, executor_id, error=f"{type(exc).__name__}:{exc}")
        raise
    finally:
        lease = workflow.load_json(Path(claim["output_dir"]) / "controller_state.json").get("executor_lease") or {}
        if lease.get("executor_id") == executor_id and lease.get("status") == "active":
            workflow.release_executor_lease(claim_path, executor_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic candidate action executor")
    parser.add_argument("--claim", type=Path, required=True)
    parser.add_argument("--base-url", default=os.environ.get("CANDIDATE_BASE_URL", "http://localhost:8000/v1"))
    parser.add_argument("--model", default=os.environ.get("CANDIDATE_MODEL", DEFAULT_MODEL))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-tokens", type=int, default=48000)
    parser.add_argument("--max-concurrency", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--api-key-env", default="")
    args = parser.parse_args()
    api_key = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
    try:
        result = run_executor(
            args.claim, base_url=args.base_url, model=args.model, timeout=args.timeout,
            max_tokens=args.max_tokens, max_concurrency=args.max_concurrency, api_key=api_key,
        )
    except Exception as exc:
        result = {"status": "paused", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
