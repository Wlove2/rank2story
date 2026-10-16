"""Opt-in, strictly bounded S3 envelope compatibility.

Four frozen 2026-09-05 production core scripts remain byte-for-byte unchanged.
Only relocate a known scalar review-status field when *all* expected candidate
records are present; never repair substantive scores, evidence or missing cards.
The caller remains responsible for strict frozen-schema validation and
recording a provenance receipt for any actual change.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


_ALLOWED_STATUS = {"passed", "pass", "rejected", "failed"}


def normalize_nested_review_status(
    raw: dict[str, Any], expected_candidate_ids: set[str],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return copied JSON content and optional audit details, never mutate input.

    Any missing ID, unknown extra ID, or non-scalar status passes through
    unchanged so that the ORIGINAL candidate-set validator rejects it.
    """
    value = deepcopy(raw)
    if not isinstance(value, dict):
        return value, None
    records = value.get("candidates")
    if not isinstance(records, dict):
        return value, None
    if (
        set(records) == set(expected_candidate_ids) | {"status"}
        and isinstance(records.get("status"), str)
        and records["status"] in _ALLOWED_STATUS
        and all(isinstance(records.get(cid), dict) for cid in expected_candidate_ids)
    ):
        moved = records.pop("status")
        return value, {
            "event": "review_envelope_scalar_status_normalized",
            "removed_metadata_path": "candidates.status",
            "removed_metadata_value": moved,
            "candidate_ids_retained": sorted(expected_candidate_ids),
            "review_body_changed": False,
            "requires_original_validator": True,
        }
    return value, None
