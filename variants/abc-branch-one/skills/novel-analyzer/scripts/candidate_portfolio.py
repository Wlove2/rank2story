#!/usr/bin/env python3
"""Deterministic candidate portfolio contracts shared by short and long lanes.

LLMs may extract atoms and draft concepts, but this module owns the audit trail:
frozen-evidence binding, isolated generation contexts, structural clustering,
market/originality gates, Pareto selection, and the user-choice pause.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

FREEZER_PATH = Path(__file__).with_name("freeze_evidence_packet.py")
FREEZER_SPEC = importlib.util.spec_from_file_location("freeze_evidence_packet_portfolio", FREEZER_PATH)
if FREEZER_SPEC is None or FREEZER_SPEC.loader is None:
    raise RuntimeError(f"cannot load {FREEZER_PATH}")
freezer = importlib.util.module_from_spec(FREEZER_SPEC)
FREEZER_SPEC.loader.exec_module(freezer)
validate_packet = freezer.validate_packet


SCHEMA_VERSION = 3
CONTRACT_VERSION = "4.4.0-rc1"
RUNTIME_ATTESTATION_VERSION = 1
LOW_INFORMATION_CODEPOINTS = (
    (21516, 31867, 39064, 26448, 26631, 26438, 20316, 21697),
    (22235, 23383, 20197, 19978, 20445, 35777, 26657, 39564, 36890, 36807),
    (26576, 20505, 36873), (26576, 20316, 21697), (20445, 35777, 26657, 39564),
)
TRUNCATED_END_CODEPOINTS = (
    (20294,), (21364,), (22240, 20026), (22914, 26524), (36890, 36807),
    (24182,), (20197, 21450), (20174, 32780), (23548, 33268), (20026, 20102), (27491, 22312),
)
LANES = {"short", "long"}
PORTFOLIO_TRACKS = {"general", "activity"}
TARGET_PLATFORMS = {"fanqie": "\u756a\u8304", "qimao": "\u4e03\u732b"}
AUDIENCE_CHANNELS = {"male", "female"}
ATOM_TYPES = {
    "desire", "anxiety", "identity_fantasy", "conflict_mechanism",
    "payoff_mode", "opening_form", "activity_constraint", "anti_signal",
}
MARKET_ATOM_TYPES = {"activity_constraint", "anti_signal"}
BRANCH_ROLES = {
    "A": "commercial_mechanism_innovator",
    "B": "causal_countertrope_inverter",
    "C": "cross_domain_emotional_transplanter",
}
BRANCH_GOALS = {
    "A": "Maximize verified reader return while changing the mechanism or its cost.",
    "B": "Maximize causal reversal across distinct reversal families; never repeat one universal satisfy-then-backlash scaffold.",
    "C": "Maximize cross-genre/cross-domain transfer and emotional impact using distant evidence combinations.",
}
FINGERPRINT_CORE = (
    "audience_desire", "protagonist_lack", "agency", "core_mechanism",
    "mechanism_cost", "opponent_interest", "escalation", "payoff_mode",
    "reaction_chain", "ending_reward",
)
FINGERPRINT_EXTRAS = {
    "short": ("opening_form", "short_closure"),
    "long": ("relationship_engine", "world_expansion", "stage_engine"),
}
FINGERPRINT_WEIGHTS = {
    "audience_desire": 1.0,
    "protagonist_lack": 1.0,
    "agency": 1.5,
    "core_mechanism": 2.5,
    "mechanism_cost": 2.5,
    "opponent_interest": 1.5,
    "escalation": 2.5,
    "payoff_mode": 2.5,
    "reaction_chain": 1.5,
    "ending_reward": 1.5,
    "opening_form": 0.5,
    "short_closure": 1.0,
    "relationship_engine": 1.0,
    "world_expansion": 0.5,
    "stage_engine": 1.5,
}
CAUSAL_DIMENSIONS = (
    "agency", "core_mechanism", "mechanism_cost", "opponent_interest",
    "escalation", "payoff_mode", "ending_reward",
)
MECHANISM_FAMILIES = {
    "memory": ("记忆", "回忆", "遗忘", "memory"),
    "identity": ("身份", "真假千金", "替身", "换身", "identity"),
    "contract_debt": ("契约", "合同", "债务", "欠债", "质押", "抵押", "contract", "debt"),
    "public_trial": ("直播", "公开审判", "舆论", "弹幕", "public trial", "livestream"),
    "rule_system": ("系统", "规则", "任务", "积分", "system", "rule"),
    "time_reset": ("重生", "穿越", "时间循环", "回到过去", "rebirth", "time loop"),
    "exchange_market": ("交易", "交换", "兑换", "拍卖", "市场", "exchange", "auction"),
    "evidence_ledger": ("账本", "证据链", "审计", "清算", "ledger", "audit"),
    "relationship_bond": ("婚姻", "亲子", "血缘", "关系绑定", "marriage", "kinship"),
    "survival_resource": ("生存", "末世", "资源", "庇护所", "survival", "resource"),
}
CLUSTER_POLICY = {
    "causal_average_floor": 0.65,
    "overall_floor": 0.62,
    "strong_dimension_floor": 0.72,
    "minimum_strong_causal_dimensions": 3,
}
OBJECTIVES = (
    "commercial_certainty", "structural_novelty", "emotional_impact",
    "producibility", "originality_risk",
)
MAXIMIZE = set(OBJECTIVES) - {"originality_risk"}
CARD_FIELDS = (
    "one_line_concept", "target_reader",
    "opening_300_beats", "reward_cycle", "three_payoffs",
    "closest_work", "causal_difference", "risks",
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"^auto(?:[-_].*)?$", re.I),
    re.compile(r"^(?:beat|step|payoff|risk|stage)\s*[-_ ]?\d+$", re.I),
    re.compile(r"^(?:\u98ce\u9669|\u5151\u73b0|\u8282\u62cd|\u6b65\u9aa4)\s*\d+$"),
    re.compile(r"^(?:unspecified|tbd|todo|n/?a|null|none)$", re.I),
    re.compile(r"^\u73b0\u6709\u4f5c\u54c1(?:\uff08\u8ddd\u79bb[^\uff09]*\uff09|\(\u8ddd\u79bb[^)]*\))?$"),
    re.compile(r"^(?:\u4f5c\u54c1|\u673a\u5236|\u5dee\u5f02)[a-zxy\d]$", re.I),
)
FORBIDDEN_ATOM_FIELDS = {
    "raw_title", "title", "full_summary", "synopsis", "recognizable_expression",
    "verbatim_excerpt", "source_text",
}
SCHEMA_LABEL_TOKENS = ATOM_TYPES | {
    "atom_type", "observation", "inference", "mechanism_signature", "premise",
    "causal_chain", "reader_payoff", "execution_plan", "one_line_concept",
    "target_reader", "reward_cycle", "three_payoffs", "closest_work",
    "causal_difference", "risks", "activity_route",
}
AUDIENCE_DESCRIPTOR_PATTERN = re.compile(
    r"(?:\u8bfb\u8005|\u53d7\u4f17|\u7528\u6237).{0,24}(?:\u504f\u597d|\u671f\u5f85|\u5bfb\u6c42|\u559c\u6b22)|"
    r"(?:reader|audience).{0,40}(?:prefer|expect|seek)",
    re.I,
)
GENERIC_LONG_STAGE_PATTERNS = (
    re.compile(r"^(?:\u5efa\u7acb|\u5b8c\u6210|\u63ed\u5f00|\u9762\u5bf9).{0,10}(?:\u4f53\u7cfb|\u4efb\u52a1|\u771f\u76f8|\u7ec8\u6781\u5bf9\u51b3)$"),
    re.compile(r".*(?:\u641e\u4e8b\u4e1a\u641e\u94b1|\u7b2c\u4e00\u4e2a\u4efb\u52a1|\u7cfb\u7edf\u6fc0\u6d3b)$"),
)
DELEGATION_ID_PATTERN = re.compile(r"^deleg_[0-9a-f]{8,}$", re.I)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seal(payload: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(payload)
    sealed.pop("output_hash", None)
    sealed["output_hash"] = canonical_hash(sealed)
    return sealed


def verify_seal(payload: dict[str, Any]) -> bool:
    expected = payload.get("output_hash")
    unsigned = dict(payload)
    unsigned.pop("output_hash", None)
    return isinstance(expected, str) and expected == canonical_hash(unsigned)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def placeholder(value: Any) -> bool:
    return nonempty(value) and any(pattern.fullmatch(value.strip()) for pattern in PLACEHOLDER_PATTERNS)


def substantive(value: Any, *, min_length: int = 3) -> bool:
    if not nonempty(value) or placeholder(value):
        return False
    return len(normalize_text(value)) >= min_length


def low_information(value: Any) -> bool:
    text = str(value or '').strip().casefold()
    tokens = tuple(''.join(map(chr, points)) for points in LOW_INFORMATION_CODEPOINTS)
    normalized_label = re.sub(r"[\s-]+", "_", text)
    return bool(text) and (
        normalized_label in SCHEMA_LABEL_TOKENS
        or any(token in text for token in tokens + ('placeholder', 'generic work'))
    )


def concept_truncated(value: Any) -> bool:
    text = str(value or '').strip()
    endings = tuple(''.join(map(chr, points)) for points in TRUNCATED_END_CODEPOINTS)
    if any(text.rstrip(', :;-').endswith(token) for token in endings):
        return True
    pairs = tuple((chr(left), chr(right)) for left, right in ((12298, 12299), (8220, 8221), (65288, 65289), (40, 41)))
    return any(text.count(left) != text.count(right) for left, right in pairs)


def substantive_list(value: Any, expected: int | None = None, *, min_length: int = 3) -> bool:
    return (
        isinstance(value, list)
        and (expected is None or len(value) == expected)
        and bool(value)
        and all(substantive(item, min_length=min_length) for item in value)
    )


def canonical_platform(value: Any) -> str | None:
    normalized = str(value or "").strip().casefold()
    aliases = {
        "fanqie": "fanqie", "\u756a\u8304": "fanqie", "\u756a\u8304\u5c0f\u8bf4": "fanqie",
        "qimao": "qimao", "\u4e03\u732b": "qimao", "\u4e03\u732b\u5c0f\u8bf4": "qimao",
    }
    return aliases.get(normalized)


def profile_slug(profile: dict[str, Any]) -> str:
    base = "-".join((
        str(profile.get("lane") or ""),
        str(profile.get("target_platform") or ""),
        str(profile.get("audience_channel") or ""),
        str(profile.get("portfolio_track") or ""),
    ))
    if profile.get("portfolio_track") == "activity":
        activity_id = str((profile.get("activity") or {}).get("activity_id") or "")
        safe_activity = re.sub(r"[^a-z0-9]+", "-", activity_id.casefold()).strip("-")
        if safe_activity:
            base = f"{base}-{safe_activity}"
    return base


def output_dir_failures(output_dir: Path, profile: dict[str, Any]) -> list[dict[str, Any]]:
    expected = profile.get("profile_slug") or profile_slug(profile)
    if output_dir.name != expected:
        return [{
            "reason": "PROFILE_OUTPUT_DIR_NOT_ISOLATED",
            "expected": expected,
            "observed": output_dir.name,
        }]
    return []


def make_profile(
    lane: str, track: str, target_platform: str, audience_channel: str,
    *, activity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if lane not in LANES:
        raise ValueError("PROFILE_LANE_INVALID")
    if track not in PORTFOLIO_TRACKS:
        raise ValueError("PROFILE_TRACK_INVALID")
    platform = canonical_platform(target_platform)
    if platform not in TARGET_PLATFORMS:
        raise ValueError("PROFILE_PLATFORM_NOT_PRIMARY")
    if audience_channel not in AUDIENCE_CHANNELS:
        raise ValueError("PROFILE_AUDIENCE_CHANNEL_INVALID")
    payload = {
        'production_contract_version': CONTRACT_VERSION,
        "stage": "portfolio_profile", "schema_version": SCHEMA_VERSION,
        "lane": lane, "portfolio_track": track, "target_platform": platform,
        "target_platform_label": TARGET_PLATFORMS[platform],
        "audience_channel": audience_channel, "activity": activity,
    }
    payload["profile_slug"] = profile_slug(payload)
    failures = profile_failures(payload)
    if failures:
        raise ValueError(f"PROFILE_INVALID: {[item['reason'] for item in failures]}")
    return seal(payload)


def profile_failures(profile: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if profile.get('production_contract_version') != CONTRACT_VERSION:
        failures.append({'reason': 'PROFILE_PRODUCTION_CONTRACT_OUTDATED'})
    if profile.get("stage") != "portfolio_profile" or profile.get("schema_version") != SCHEMA_VERSION:
        failures.append({"reason": "PROFILE_CONTRACT_INVALID"})
    if profile.get("lane") not in LANES:
        failures.append({"reason": "PROFILE_LANE_INVALID"})
    if profile.get("portfolio_track") not in PORTFOLIO_TRACKS:
        failures.append({"reason": "PROFILE_TRACK_INVALID"})
    if canonical_platform(profile.get("target_platform")) not in TARGET_PLATFORMS:
        failures.append({"reason": "PROFILE_PLATFORM_NOT_PRIMARY"})
    elif profile.get("target_platform_label") != TARGET_PLATFORMS[canonical_platform(profile.get("target_platform"))]:
        failures.append({"reason": "PROFILE_PLATFORM_LABEL_INVALID"})
    if profile.get("audience_channel") not in AUDIENCE_CHANNELS:
        failures.append({"reason": "PROFILE_AUDIENCE_CHANNEL_INVALID"})
    if profile.get("profile_slug") != profile_slug(profile):
        failures.append({"reason": "PROFILE_SLUG_INVALID"})
    activity = profile.get("activity")
    if profile.get("portfolio_track") == "general":
        if activity not in (None, {}):
            failures.append({"reason": "GENERAL_PROFILE_MUST_NOT_EMBED_ACTIVITY"})
    elif not isinstance(activity, dict):
        failures.append({"reason": "ACTIVITY_PROFILE_MISSING"})
    else:
        for field in ("activity_id", "name", "source_url", "rule_hash", "retrieved_at", "submission_window_status"):
            if not substantive(activity.get(field)):
                failures.append({"reason": f"ACTIVITY_{field.upper()}_INVALID"})
        if not re.fullmatch(r"[0-9a-f]{64}", str(activity.get("rule_hash") or "")):
            failures.append({"reason": "ACTIVITY_RULE_HASH_INVALID"})
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", str(activity.get("retrieved_at") or "")):
            failures.append({"reason": "ACTIVITY_RETRIEVED_AT_INVALID"})
        source_url = str(activity.get("source_url") or "").casefold()
        platform = canonical_platform(profile.get("target_platform"))
        official_domain = (
            "fanqienovel.com" in source_url if platform == "fanqie"
            else any(domain in source_url for domain in ("qimao.com", "qm989.com"))
        )
        if not source_url.startswith("https://") or not official_domain:
            failures.append({"reason": "ACTIVITY_OFFICIAL_SOURCE_INVALID"})
        if activity.get("submission_window_status") != "open":
            failures.append({"reason": "ACTIVITY_SUBMISSION_WINDOW_NOT_OPEN"})
        if not substantive_list(activity.get("rule_evidence_ids")) or not substantive_list(activity.get("requirements")):
            failures.append({"reason": "ACTIVITY_RULE_EVIDENCE_INCOMPLETE"})
        if profile.get("lane") not in set(activity.get("allowed_lanes") or []):
            failures.append({"reason": "ACTIVITY_LANE_NOT_ELIGIBLE"})
        if profile.get("audience_channel") not in set(activity.get("allowed_channels") or []):
            failures.append({"reason": "ACTIVITY_CHANNEL_NOT_ELIGIBLE"})
        if canonical_platform(activity.get("platform")) != canonical_platform(profile.get("target_platform")):
            failures.append({"reason": "ACTIVITY_PLATFORM_MISMATCH"})
    return failures


def recursive_evidence(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        evidence_id = value.get("evidence_id") or value.get("id")
        if evidence_id:
            yield value
        for child in value.values():
            yield from recursive_evidence(child)
    elif isinstance(value, list):
        for child in value:
            yield from recursive_evidence(child)


def evidence_index(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in recursive_evidence(packet.get("evidence")):
        evidence_id = str(row.get("evidence_id") or row.get("id"))
        result[evidence_id] = row
    return result


def normalize_reference_url(value: Any) -> str | None:
    try:
        parts = urlsplit(str(value or "").strip())
    except ValueError:
        return None
    if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname:
        return None
    host = parts.hostname.casefold()
    port = f":{parts.port}" if parts.port and parts.port not in {80, 443} else ""
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted(
        (key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
    ))
    return urlunsplit((parts.scheme.casefold(), host + port, path, query, ""))


def evidence_reference_registry(packet: dict[str, Any]) -> dict[str, set[str]]:
    evidence_ids = set(evidence_index(packet))
    urls: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.casefold() in {"url", "direct_url", "source_url", "canonical_url"}:
                    normalized = normalize_reference_url(child)
                    if normalized:
                        urls.add(normalized)
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(packet)
    return {"evidence_ids": evidence_ids, "urls": urls}


def cohort_index(packet: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    source_to_cohort: dict[str, str] = {}
    cohorts: dict[str, dict[str, Any]] = {}
    for cohort, definition in (packet.get("source_mix_policy") or {}).items():
        if not isinstance(definition, dict):
            continue
        cohorts[str(cohort)] = definition
        for source_id in definition.get("source_ids", []):
            source_id = str(source_id)
            if source_id in source_to_cohort and source_to_cohort[source_id] != cohort:
                raise ValueError(f"source belongs to multiple cohorts: {source_id}")
            source_to_cohort[source_id] = str(cohort)
    return source_to_cohort, cohorts


def cohort_for_source(source_to_cohort: dict[str, str], source_id: Any) -> str | None:
    """Resolve an evidence source_id to its declared cohort, tolerating a leading
    scan-entity prefix (2026-09-02 fix): new scan packets write source_id as
    '20260830T100729Z-long:fanqie_public_web_ranks' while source_mix_policy declares
    the bare name 'fanqie_public_web_ranks'. Strip at most 3 leading ':'-separated
    segments and re-check against the policy keys. Legacy bare-name packets resolve
    by exact match and are unaffected. Only source_id is normalized — evidence_id
    (which may legitimately contain 'https://...') is NEVER touched here."""
    if not source_id:
        return None
    value = str(source_id)
    hit = source_to_cohort.get(value)
    if hit is not None:
        return hit
    remainder = value
    for _ in range(3):
        if ":" not in remainder:
            break
        remainder = remainder.split(":", 1)[1]
        if not remainder:
            break
        hit = source_to_cohort.get(remainder)
        if hit is not None:
            return hit
    return None


def atom_failures(packet: dict[str, Any], bundle: dict[str, Any], lane: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packet_hash = validate_packet(packet, lane)
    failures: list[dict[str, Any]] = []
    if bundle.get("schema_version") != SCHEMA_VERSION:
        failures.append({"reason": "ATOM_SCHEMA_VERSION_INVALID"})
    if bundle.get("stage") != "evidence_atoms" or bundle.get("lane") != lane:
        failures.append({"reason": "ATOM_STAGE_OR_LANE_INVALID"})
    if bundle.get("evidence_packet_hash") != packet_hash:
        failures.append({"reason": "ATOM_PACKET_HASH_MISMATCH"})
    if not nonempty(bundle.get("run_id")):
        failures.append({"reason": "ATOM_RUN_ID_MISSING"})
    if bundle.get("input_hash") != packet_hash:
        failures.append({"reason": "ATOM_INPUT_HASH_INVALID"})
    if not verify_seal(bundle):
        failures.append({"reason": "ATOM_OUTPUT_HASH_INVALID"})

    evidence = evidence_index(packet)
    source_to_cohort, cohorts = cohort_index(packet)
    atoms = bundle.get("atoms")
    if not isinstance(atoms, list) or not atoms:
        failures.append({"reason": "ATOMS_MISSING"})
        atoms = []
    ids: set[str] = set()
    claim_groups: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    distribution: dict[str, int] = defaultdict(int)
    platforms: dict[str, int] = defaultdict(int)
    atom_sources: dict[str, set[str]] = {}
    semantic_signatures: dict[str, list[str]] = defaultdict(list)

    for atom in atoms:
        if not isinstance(atom, dict):
            failures.append({"reason": "ATOM_NOT_OBJECT"})
            continue
        atom_id = str(atom.get("atom_id") or "")
        if not atom_id or atom_id in ids:
            failures.append({"reason": "ATOM_ID_INVALID_OR_DUPLICATE", "atom_id": atom_id})
            continue
        ids.add(atom_id)
        if atom.get("lane") != lane:
            failures.append({"reason": "ATOM_LANE_MISMATCH", "atom_id": atom_id})
        if atom.get("atom_type") not in ATOM_TYPES:
            failures.append({"reason": "ATOM_TYPE_INVALID", "atom_id": atom_id})
        forbidden = sorted(FORBIDDEN_ATOM_FIELDS & set(atom))
        if forbidden:
            failures.append({"reason": "RAW_EXPRESSION_LEAKED_TO_ATOM", "atom_id": atom_id, "fields": forbidden})
        if atom.get("generation_safe") is not True:
            failures.append({"reason": "ATOM_NOT_MARKED_GENERATION_SAFE", "atom_id": atom_id})
        if low_information(atom.get("observation")) or low_information(atom.get("inference")):
            failures.append({"reason": "ATOM_CONTENT_LOW_INFORMATION", "atom_id": atom_id})
        elif not substantive(atom.get("observation"), min_length=12) or not substantive(atom.get("inference"), min_length=12):
            failures.append({"reason": "FACT_INFERENCE_BOUNDARY_MISSING", "atom_id": atom_id})
        elif atom["observation"].strip().casefold() == atom["inference"].strip().casefold():
            failures.append({"reason": "FACT_INFERENCE_NOT_SEPARATED", "atom_id": atom_id})
        else:
            signature = canonical_hash([
                normalize_text(atom.get("observation")), normalize_text(atom.get("inference")),
            ])
            semantic_signatures[signature].append(atom_id)
        if re.search(r"\u300a[^\u300b]{1,80}\u300b", str(atom.get("observation") or "")):
            failures.append({"reason": "RAW_TITLE_TEXT_LEAKED_TO_ATOM", "atom_id": atom_id})
        confidence = atom.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            failures.append({"reason": "ATOM_CONFIDENCE_INVALID", "atom_id": atom_id})
        if not nonempty(atom.get("freshness")):
            failures.append({"reason": "ATOM_FRESHNESS_MISSING", "atom_id": atom_id})
        if not nonempty(atom.get("claim_key")) or atom.get("stance") not in {"support", "counter", "mixed"}:
            failures.append({"reason": "ATOM_CLAIM_OR_STANCE_INVALID", "atom_id": atom_id})
        else:
            claim_groups[str(atom["claim_key"])][str(atom["stance"])].add(atom_id)

        primary_id = str(atom.get("evidence_id") or "")
        source_item_id = str(atom.get("source_item_id") or "")
        source = evidence.get(primary_id)
        if source is None:
            failures.append({"reason": "ATOM_EVIDENCE_UNKNOWN", "atom_id": atom_id, "evidence_id": primary_id})
            source_id = ""
        else:
            source_id = str(source.get("source_id") or source.get("manifest_id") or "")
            frozen_item_id = str(source.get("source_item_id") or "")
            if frozen_item_id and source_item_id != frozen_item_id:
                failures.append({"reason": "ATOM_SOURCE_ITEM_MISMATCH", "atom_id": atom_id})
        if str(atom.get("source_id") or "") != source_id:
            failures.append({"reason": "ATOM_SOURCE_ID_MISMATCH", "atom_id": atom_id})
        expected_cohort = cohort_for_source(source_to_cohort, source_id)
        if not expected_cohort or atom.get("source_cohort") != expected_cohort:
            failures.append({"reason": "ATOM_SOURCE_COHORT_MISMATCH", "atom_id": atom_id})
        else:
            distribution[expected_cohort] += 1
        platform = str(atom.get("platform") or "")
        if not platform:
            failures.append({"reason": "ATOM_PLATFORM_MISSING", "atom_id": atom_id})
        else:
            platforms[platform] += 1

        supporting = {str(value) for value in atom.get("supporting_evidence_ids", [])}
        counters = {str(value) for value in atom.get("counter_evidence_ids", [])}
        if primary_id not in supporting:
            failures.append({"reason": "PRIMARY_EVIDENCE_NOT_IN_SUPPORT_SET", "atom_id": atom_id})
        unknown = sorted((supporting | counters) - set(evidence))
        if unknown:
            failures.append({"reason": "ATOM_RELATED_EVIDENCE_UNKNOWN", "atom_id": atom_id, "evidence_ids": unknown})
        atom_sources[atom_id] = {
            str(evidence[value].get("source_id") or evidence[value].get("manifest_id") or "")
            for value in supporting | counters if value in evidence
        }

    for claim_key, stances in claim_groups.items():
        support_ids = stances.get("support", set()) | stances.get("mixed", set())
        counter_ids = stances.get("counter", set()) | stances.get("mixed", set())
        if support_ids and counter_ids:
            for atom in atoms:
                if atom.get("claim_key") != claim_key:
                    continue
                linked = set(map(str, atom.get("contradicting_atom_ids", [])))
                required = counter_ids if atom.get("stance") == "support" else support_ids
                if atom.get("stance") != "mixed" and not linked.intersection(required):
                    failures.append({"reason": "CROSS_SOURCE_CONTRADICTION_NOT_LINKED", "atom_id": atom.get("atom_id")})

    for atom_ids in semantic_signatures.values():
        if len(atom_ids) > 1:
            failures.append({"reason": "ATOM_SEMANTIC_DUPLICATE", "atom_ids": sorted(atom_ids)})

    total = len(atoms)
    cohort_distribution = {
        cohort: {
            "atom_count": distribution.get(cohort, 0),
            "share_of_all_atoms": round(distribution.get(cohort, 0) / total, 6) if total else 0,
            "policy_cap": definition.get("cap"),
            "allocated_influence": round(float(definition.get("cap") or 0), 6) if distribution.get(cohort, 0) else 0,
            "per_atom_influence": round(float(definition.get("cap") or 0) / distribution.get(cohort, 1), 6) if distribution.get(cohort, 0) else 0,
            "missing": distribution.get(cohort, 0) == 0,
        }
        for cohort, definition in cohorts.items()
    }
    allocated_influence = round(sum(row["allocated_influence"] for row in cohort_distribution.values()), 6)
    cross_source_atoms = sorted(atom_id for atom_id, sources in atom_sources.items() if len(sources) >= 2)
    audit = {
        "stage": "evidence_atom_audit",
        "schema_version": SCHEMA_VERSION,
        "lane": lane,
        "run_id": bundle.get("run_id"),
        "input_hash": bundle.get("output_hash"),
        "evidence_packet_hash": packet_hash,
        "atom_count": total,
        "cohort_distribution": cohort_distribution,
        "allocated_influence": allocated_influence,
        "unallocated_influence": round(max(0.0, 1.0 - allocated_influence), 6),
        "platform_distribution": dict(sorted(platforms.items())),
        "cross_source_supported_atom_ids": cross_source_atoms,
        "missing_cohorts_are_not_redistributed": True,
        "failures": failures,
        "status": "passed" if not failures else "blocked",
    }
    return failures, seal(audit)


def safe_atom(atom: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "atom_id", "lane", "atom_type", "source_cohort", "platform",
        "inference", "confidence", "freshness", "claim_key",
        "stance", "supporting_evidence_ids", "counter_evidence_ids",
        "channel", "channel_basis",
    }
    return {key: atom[key] for key in sorted(allowed & set(atom))}


def sampling_config(requested: str, vs_outcome: str, vs_gain: float | None) -> dict[str, Any]:
    if requested != "verbalized_sampling":
        return {"requested": requested, "effective": "standard_stratified", "fallback_reason": None}
    if vs_outcome != "valid":
        return {"requested": requested, "effective": "standard_stratified", "fallback_reason": f"VS_{vs_outcome.upper()}"}
    if vs_gain is None or vs_gain < 0.10:
        return {"requested": requested, "effective": "standard_stratified", "fallback_reason": "VS_DIVERSITY_GAIN_INSUFFICIENT"}
    return {"requested": requested, "effective": requested, "fallback_reason": None, "measured_diversity_gain": round(vs_gain, 4)}


def select_context_atoms(
    atoms: list[dict[str, Any]], branch_id: str, priority: dict[str, int],
    target_platform: str, track: str, *,
    audience_channel: str = "male",
    prior_used_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    # Channel filter (2026-08-15 L2): male run consumes male + neutral atoms only;
    # female run consumes female + neutral. Neutral = source carries no gender signal
    # (综合榜/作家榜/小红书/B站) or legacy frozen packets without channel fields.
    eligible = [
        atom for atom in atoms
        if (atom.get("channel") or "neutral") in {audience_channel, "neutral"}
    ]
    if len(eligible) >= 6:
        atoms = eligible
    creative_pool = [atom for atom in atoms if atom.get("atom_type") not in MARKET_ATOM_TYPES]
    take = min(60, max(6, math.ceil(len(creative_pool) * 0.25)))
    creative_types = sorted(
        (atom_type for atom_type in ATOM_TYPES if atom_type not in MARKET_ATOM_TYPES),
        key=lambda atom_type: (priority.get(atom_type, 9), atom_type),
    )
    buckets: dict[str, list[dict[str, Any]]] = {}
    for atom_type in creative_types:
        buckets[atom_type] = sorted(
            [atom for atom in creative_pool if atom.get("atom_type") == atom_type],
            key=lambda atom: canonical_hash([branch_id, atom.get("source_cohort"), atom.get("claim_key"), atom.get("atom_id")]),
        )
    prior_ids = prior_used_ids or set()
    max_overlap = max(2, take // 3)

    def round_robin(candidates_fn, budget: int) -> list[dict[str, Any]]:
        picked: list[dict[str, Any]] = []
        seen_claims: set[str] = set()
        while len(picked) < budget and any(candidates_fn(t) for t in creative_types):
            progressed = False
            for atom_type in creative_types:
                bucket = candidates_fn(atom_type)
                while bucket:
                    atom = bucket.pop(0)
                    claim_key = str(atom.get("claim_key") or atom.get("source_item_id") or atom.get("atom_id"))
                    if claim_key in seen_claims:
                        continue
                    picked.append(atom)
                    seen_claims.add(claim_key)
                    progressed = True
                    break
                if len(picked) == budget:
                    break
            if not progressed:
                break
        return picked

    fresh_buckets = {
        t: [a for a in buckets[t] if str(a.get("atom_id")) not in prior_ids]
        for t in creative_types
    }
    selected = round_robin(lambda t: fresh_buckets[t], take)
    if len(selected) < take:
        selected_ids = {str(a.get("atom_id")) for a in selected}
        overlap_budget = min(max_overlap, take - len(selected))
        overlap_buckets = {
            t: [a for a in buckets[t] if str(a.get("atom_id")) in prior_ids and str(a.get("atom_id")) not in selected_ids]
            for t in creative_types
        }
        selected.extend(round_robin(lambda t: overlap_buckets[t], overlap_budget))
    if len(selected) < take:
        selected_ids = {str(a.get("atom_id")) for a in selected}
        fallback_buckets = {
            t: [a for a in buckets[t] if str(a.get("atom_id")) not in selected_ids]
            for t in creative_types
        }
        selected.extend(round_robin(lambda t: fallback_buckets[t], take - len(selected)))
    if len(selected) < min(4, len(creative_pool)):
        raise ValueError("CONTEXT_DIVERSITY_INSUFFICIENT")
    if len({atom.get("atom_type") for atom in selected}) < min(3, len({atom.get("atom_type") for atom in creative_pool})):
        raise ValueError("CONTEXT_ATOM_TYPE_COVERAGE_INSUFFICIENT")
    return selected


def build_contexts(
    packet: dict[str, Any], bundle: dict[str, Any], profile: dict[str, Any], lane: str, run_id: str,
    *, requested_sampling: str = "standard_stratified", vs_outcome: str = "not_run",
    vs_gain: float | None = None,
) -> dict[str, Any]:
    profile_errors = profile_failures(profile)
    if profile_errors or not verify_seal(profile) or profile.get("lane") != lane:
        raise ValueError(f"PROFILE_INVALID: {[item['reason'] for item in profile_errors]}")
    failures, audit = atom_failures(packet, bundle, lane)
    if failures:
        raise ValueError(f"ATOM_AUDIT_BLOCKED: {[item['reason'] for item in failures]}")
    atoms = list(bundle["atoms"])
    if len(atoms) < 6:
        raise ValueError("ATOMS_INSUFFICIENT_FOR_THREE_DIVERGENT_CONTEXTS")
    audience_channel = str(profile.get("audience_channel") or "male")
    eligible = [
        atom for atom in atoms
        if (atom.get("channel") or "neutral") in {audience_channel, "neutral"}
    ]
    channel_filter_fallback = len(eligible) < 6
    pool = eligible if not channel_filter_fallback else atoms
    priority = {
        "A": {"desire": 0, "payoff_mode": 1, "anxiety": 2, "conflict_mechanism": 3, "identity_fantasy": 4, "opening_form": 5},
        "B": {"conflict_mechanism": 0, "payoff_mode": 1, "anxiety": 2, "desire": 3, "identity_fantasy": 4, "opening_form": 5},
        "C": {"identity_fantasy": 0, "opening_form": 1, "anxiety": 2, "conflict_mechanism": 3, "desire": 4, "payoff_mode": 5},
    }
    market_atoms = [atom for atom in pool if atom.get("atom_type") in MARKET_ATOM_TYPES]
    contexts: dict[str, Any] = {}
    all_prior_ids: set[str] = set()
    config = sampling_config(requested_sampling, vs_outcome, vs_gain)
    for branch_id in ("A", "B", "C"):
        selected = select_context_atoms(
            pool, branch_id, priority[branch_id],
            str(profile["target_platform"]), str(profile["portfolio_track"]),
            audience_channel=audience_channel,
            prior_used_ids=all_prior_ids,
        )
        selected_ids = {str(atom["atom_id"]) for atom in selected}
        all_prior_ids.update(selected_ids)
        context = {
            "stage": "generation_context",
            "schema_version": SCHEMA_VERSION,
            "lane": lane,
            "run_id": run_id,
            "branch_id": branch_id,
            "generator_role": BRANCH_ROLES[branch_id],
            "goal": BRANCH_GOALS[branch_id],
            "independent_context": True,
            "visible_branch_ids": [branch_id],
            "input_hash": bundle["output_hash"],
            "evidence_packet_hash": validate_packet(packet, lane),
            "target_profile_hash": profile["output_hash"],
            "target_profile": {
                "portfolio_track": profile["portfolio_track"],
                "target_platform": profile["target_platform"],
                "target_platform_label": profile["target_platform_label"],
                "audience_channel": profile["audience_channel"],
                "activity": profile.get("activity"),
            },
            "input_atom_ids": sorted(selected_ids),
            "sampling_config": config,
            "channel_filter": audience_channel,
            "channel_filter_fallback": channel_filter_fallback,
            "channel_distribution": {
                channel: sum(1 for atom in atoms if (atom.get("channel") or "neutral") == channel)
                for channel in ("male", "female", "neutral")
            },
            "forbidden_context": sorted(FORBIDDEN_ATOM_FIELDS),
            "source_balance_rule": "cohort influence is capped by frozen policy; missing or unselected influence is not redistributed",
            "cohort_distribution": audit["cohort_distribution"],
            "unallocated_influence": audit["unallocated_influence"],
            "atoms": [
                {
                    **safe_atom(atom),
                    "cohort_influence_weight": audit["cohort_distribution"][atom["source_cohort"]]["per_atom_influence"],
                }
                for atom in selected
            ],
            "shared_market_constraints": [safe_atom(atom) for atom in market_atoms],
        }
        contexts[branch_id] = seal(context)
    creative_count = len([a for a in pool if a.get("atom_type") not in MARKET_ATOM_TYPES])
    take_per_branch = min(60, max(6, math.ceil(creative_count * 0.25)))
    if creative_count >= take_per_branch * 2:
        if len({tuple(contexts[key]["input_atom_ids"]) for key in contexts}) != 3:
            raise ValueError("GENERATION_CONTEXT_SLICES_NOT_DIVERGENT")
    else:
        ordered_sequences = [
            tuple(atom["atom_id"] for atom in contexts[key]["atoms"]) for key in contexts
        ]
        if len(set(ordered_sequences)) != 3:
            raise ValueError("GENERATION_CONTEXT_SLICES_NOT_DIVERGENT")
    return seal({
        "stage": "generation_contexts",
        "schema_version": SCHEMA_VERSION,
        "lane": lane,
        "run_id": run_id,
        "input_hash": audit["output_hash"],
        "evidence_packet_hash": validate_packet(packet, lane),
        "target_profile_hash": profile["output_hash"],
        "contexts": contexts,
        "recovery_status": "contexts_ready",
    })


def candidate_card_shape_failures(
    candidate: dict[str, Any], lane: str, profile: dict[str, Any],
) -> list[str]:
    card = candidate.get("candidate_card")
    if not isinstance(card, dict):
        return ["CANDIDATE_CARD_MISSING"]
    reasons: list[str] = []
    for field in CARD_FIELDS:
        if field not in card:
            reasons.append(f"CARD_FIELD_MISSING:{field}")
    for field in ("one_line_concept", "target_reader", "closest_work", "causal_difference"):
        value = card.get(field)
        if not substantive(value):
            detail = f"'{str(value)[:80]}' normalizes to {len(normalize_text(value))} chars, min required: 3"
            reasons.append(f"CARD_{field.upper()}_NOT_SUBSTANTIVE:{detail}")
    concept = str(card.get("one_line_concept") or "")
    target_reader = str(card.get("target_reader") or "")
    if (
        normalize_text(concept) == normalize_text(target_reader)
        or AUDIENCE_DESCRIPTOR_PATTERN.search(concept)
    ):
        reasons.append("CARD_ONE_LINE_CONCEPT_IS_AUDIENCE_DESCRIPTION")
    if not re.search(r"[\u3400-\u9fff]", concept):
        reasons.append("CARD_ONE_LINE_CONCEPT_LANGUAGE_INVALID")
    if concept_truncated(concept):
        reasons.append('CARD_ONE_LINE_CONCEPT_TRUNCATED')
    if low_information(card.get('closest_work')):
        reasons.append('CARD_CLOSEST_WORK_PLACEHOLDER')
    if low_information(card.get('causal_difference')):
        reasons.append('CARD_CAUSAL_DIFFERENCE_PLACEHOLDER')
    if card.get("target_platform") != profile.get("target_platform"):
        reasons.append("CARD_TARGET_PLATFORM_MISMATCH")
    if card.get("audience_channel") != profile.get("audience_channel"):
        reasons.append("CARD_AUDIENCE_CHANNEL_MISMATCH")
    if card.get("portfolio_track") != profile.get("portfolio_track"):
        reasons.append("CARD_PORTFOLIO_TRACK_MISMATCH")
    if card.get("target_profile_hash") != profile.get("output_hash"):
        reasons.append("CARD_TARGET_PROFILE_HASH_MISMATCH")
    route = card.get("activity_route")
    if profile.get("portfolio_track") == "general" and route not in (None, "", "not_applicable"):
        reasons.append("GENERAL_CARD_ACTIVITY_ROUTE_INVALID")
    if profile.get("portfolio_track") == "activity" and not isinstance(route, dict):
        reasons.append("ACTIVITY_CARD_ROUTE_MISSING")
    if not substantive_list(card.get("opening_300_beats"), min_length=12) or len(card["opening_300_beats"]) < 3:
        reasons.append("CARD_OPENING_300_INVALID")
    if not substantive_list(card.get("reward_cycle"), 6):
        reasons.append("CARD_REWARD_CYCLE_INVALID")
    if not substantive_list(card.get("three_payoffs"), 3):
        reasons.append("CARD_THREE_PAYOFFS_INVALID")
    risks = card.get("risks")
    if not (substantive(risks) or substantive_list(risks)):
        reasons.append("CARD_RISKS_NOT_SUBSTANTIVE")
    if lane == "short":
        if not substantive(card.get("short_closure")):
            reasons.append("CARD_SHORT_CLOSURE_INVALID")
    else:
        stages = card.get("long_run_stages")
        if not isinstance(stages, dict) or set(stages) != {"300k", "800k", "1500k"}:
            reasons.append("CARD_LONG_RUN_STAGES_INVALID")
        else:
            required = {"goal", "relationship_change", "world_expansion", "irreversible_change", "stage_payoff"}
            for stage, row in stages.items():
                values = [str(row.get(field) or "") for field in required] if isinstance(row, dict) else []
                if (
                    not isinstance(row, dict)
                    or any(not substantive(row.get(field), min_length=6) for field in required)
                    or len({normalize_text(value) for value in values}) != len(values)
                    or any(pattern.fullmatch(value.strip()) for value in values for pattern in GENERIC_LONG_STAGE_PATTERNS)
                ):
                    reasons.append(f"CARD_LONG_STAGE_NOT_SUBSTANTIVE:{stage}")
    return reasons



def story_review_passed(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"通过[。.!！]?", value.strip()) is not None


def story_contract_failures(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the controller-owned story -> review -> card trace."""
    failures: list[dict[str, Any]] = []
    candidate_id = str(candidate.get("candidate_id") or candidate.get("id") or "")
    kernel_id = str(candidate.get("kernel_id") or "")
    story = candidate.get("story_proposal")
    review = candidate.get("story_review")
    trace = candidate.get("story_trace")
    if not nonempty(story):
        failures.append({"reason": "STORY_PROPOSAL_MISSING", "candidate_id": candidate_id})
        return failures
    story_hash = canonical_hash(story.strip())
    if not isinstance(review, dict) or not verify_seal(review):
        failures.append({"reason": "STORY_REVIEW_RECEIPT_INVALID", "candidate_id": candidate_id})
        return failures
    if review.get("candidate_id") != candidate_id or review.get("kernel_id") != kernel_id:
        failures.append({"reason": "STORY_REVIEW_ID_MISMATCH", "candidate_id": candidate_id})
    if (
        review.get("status") != "passed"
        or not story_review_passed(review.get("review_text"))
        or review.get("reviewer_does_not_complete_story") is not True
    ):
        failures.append({"reason": "STORY_REVIEW_NOT_PASSED", "candidate_id": candidate_id})
    if review.get("story_hash") != story_hash:
        failures.append({"reason": "STORY_REVIEW_HASH_MISMATCH", "candidate_id": candidate_id})
    if not isinstance(trace, dict):
        failures.append({"reason": "STORY_TRACE_MISSING", "candidate_id": candidate_id})
        return failures
    expected_mapping_input_hash = canonical_hash({
        "candidate_id": candidate_id,
        "kernel_id": kernel_id,
        "story_hash": story_hash,
        "review_hash": review["output_hash"],
    })
    expected = {
        "candidate_id": candidate_id,
        "kernel_id": kernel_id,
        "story_hash": story_hash,
        "review_hash": review["output_hash"],
        "mapping_input_hash": expected_mapping_input_hash,
    }
    if any(trace.get(key) != value for key, value in expected.items()):
        failures.append({"reason": "STORY_TRACE_MISMATCH", "candidate_id": candidate_id})
    return failures

def branch_failures(
    branch: dict[str, Any], context: dict[str, Any], profile: dict[str, Any], lane: str,
    minimum_candidates: int = 3,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    branch_id = context["branch_id"]
    # Schema-level checks (not auto-fixable)
    if branch.get("stage") != "divergent_generation" or branch.get("schema_version") != SCHEMA_VERSION:
        failures.append({"reason": "GENERATOR_ARTIFACT_CONTRACT_INVALID", "branch_id": branch_id})
    # lane/run_id/branch_id/generator_role/evidence_packet_hash/context_hash/target_profile_hash/
    # input_atom_ids/sampling_config/independent_context/visible_branch_ids/output_hash
    # are all injected by controller — skip validation
    candidates = branch.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        failures.append({"reason": "GENERATOR_CANDIDATES_MISSING", "branch_id": branch_id})
        return failures
    if len(candidates) < minimum_candidates:
        failures.append({
            "reason": "GENERATOR_CANDIDATE_COUNT_INSUFFICIENT",
            "branch_id": branch_id,
            "required": minimum_candidates,
        })
    input_atoms = set(context["input_atom_ids"])
    for candidate in candidates:
        if not isinstance(candidate, dict):
            failures.append({"reason": "GENERATOR_CANDIDATE_NOT_OBJECT", "branch_id": branch_id})
            continue
        candidate_id = str(candidate.get("candidate_id") or candidate.get("id") or "")
        if not candidate_id:
            failures.append({"reason": "GENERATOR_CANDIDATE_ID_MISSING", "branch_id": branch_id})
        # generator_branch and cited_atom_ids are injected by controller — skip validation
        failures.extend(story_contract_failures(candidate))
        fingerprint = candidate.get("structural_fingerprint")
        required = set(FINGERPRINT_CORE + FINGERPRINT_EXTRAS[lane])
        if not isinstance(fingerprint, dict) or any(not substantive(fingerprint.get(key)) for key in required):
            failures.append({"reason": "CANDIDATE_STRUCTURAL_FINGERPRINT_INCOMPLETE", "candidate_id": candidate_id})
        for reason in candidate_card_shape_failures(candidate, lane, profile):
            failures.append({"reason": reason, "candidate_id": candidate_id})
        # evidence_atom_ids and cited_atom_ids are injected by controller — skip CARD_ATOM_CITATION_MISMATCH
    return failures


def normalize_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = " ".join(map(str, value))
    elif isinstance(value, dict):
        value = " ".join(str(value[key]) for key in sorted(value))
    return re.sub(r"[\W_]+", "", str(value or "").casefold(), flags=re.UNICODE)


def mechanism_family_labels(value: Any) -> tuple[str, ...]:
    text = str(value or "").casefold()
    return tuple(sorted(
        family
        for family, aliases in MECHANISM_FAMILIES.items()
        if any(alias.casefold() in text for alias in aliases)
    ))


def normalized_similarity(left: Any, right: Any) -> float:
    left_text, right_text = normalize_text(left), normalize_text(right)
    if not left_text or not right_text:
        return 0.0
    matcher = difflib.SequenceMatcher(None, left_text, right_text)
    longest = matcher.find_longest_match(0, len(left_text), 0, len(right_text)).size
    containment = longest / min(len(left_text), len(right_text))
    return max(matcher.ratio(), containment)


def first_value(candidate: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value: Any = candidate
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if nonempty(value) or isinstance(value, (list, dict)) and value:
            return value
    return "unspecified"


def derive_structural_fingerprint(candidate: dict[str, Any], lane: str) -> dict[str, str]:
    """Compatibility mapper for inventory tools; v3 formal generation must provide explicit fields."""
    fingerprint = {
        "audience_desire": first_value(candidate, "audience_desire", "core_desire", "emotional_engine", "target_reader"),
        "protagonist_lack": first_value(candidate, "protagonist_lack", "core_desire", "premise"),
        "agency": first_value(candidate, "agency", "craft.irreversible_choice", "irreversible_choice"),
        "core_mechanism": first_value(candidate, "core_mechanism", "mechanism", "premise"),
        "mechanism_cost": first_value(candidate, "mechanism_cost", "mechanism_limit", "aftermath.cost"),
        "opponent_interest": first_value(candidate, "opponent_interest", "craft.antagonist_self_interest", "main_conflict"),
        "escalation": first_value(candidate, "escalation", "scene_chain", "world_expansion"),
        "payoff_mode": first_value(candidate, "payoff_mode", "payoff", "stage_closures"),
        "reaction_chain": first_value(candidate, "reaction_chain", "craft.reaction_parties", "aftermath.social_reaction"),
        "ending_reward": first_value(candidate, "ending_reward", "stage_closures", "aftermath.next_state"),
    }
    if lane == "short":
        fingerprint.update({
            "opening_form": first_value(candidate, "opening_form", "craft.opening_action", "promise_300"),
            "short_closure": first_value(candidate, "short_closure", "aftermath", "closure"),
        })
    else:
        fingerprint.update({
            "relationship_engine": first_value(candidate, "relationship_engine"),
            "world_expansion": first_value(candidate, "world_expansion"),
            "stage_engine": first_value(candidate, "long_run_stages", "stage_closures"),
        })
    return {key: str(value) for key, value in fingerprint.items()}

def shingles(value: Any) -> set[str]:
    text = normalize_text(value)
    if len(text) <= 2:
        return {text} if text else set()
    return {text[index:index + 2] for index in range(len(text) - 1)}


def dimension_similarity(left: Any, right: Any) -> float:
    left_norm, right_norm = normalize_text(left), normalize_text(right)
    if left_norm and left_norm == right_norm:
        return 1.0
    left_families = set(mechanism_family_labels(left))
    right_families = set(mechanism_family_labels(right))
    if left_families or right_families:
        return (
            len(left_families & right_families) / len(left_families | right_families)
            if left_families and right_families else 0.0
        )
    left_set, right_set = shingles(left), shingles(right)
    return len(left_set & right_set) / len(left_set | right_set) if left_set and right_set else 0.0


def fingerprint_similarity(left: dict[str, Any], right: dict[str, Any], lane: str) -> dict[str, Any]:
    dimensions = FINGERPRINT_CORE + FINGERPRINT_EXTRAS[lane]
    scores = {key: round(dimension_similarity(left.get(key), right.get(key)), 6) for key in dimensions}
    denominator = sum(FINGERPRINT_WEIGHTS[key] for key in dimensions)
    overall = sum(scores[key] * FINGERPRINT_WEIGHTS[key] for key in dimensions) / denominator
    causal_average = sum(scores[key] for key in CAUSAL_DIMENSIONS) / len(CAUSAL_DIMENSIONS)
    strong = sum(scores[key] >= CLUSTER_POLICY["strong_dimension_floor"] for key in CAUSAL_DIMENSIONS)
    merge = (
        causal_average >= CLUSTER_POLICY["causal_average_floor"]
        and overall >= CLUSTER_POLICY["overall_floor"]
        and strong >= CLUSTER_POLICY["minimum_strong_causal_dimensions"]
    )
    strongest = sorted(scores, key=lambda key: (-scores[key] * FINGERPRINT_WEIGHTS[key], key))[:4]
    return {
        "overall": round(overall, 6),
        "causal_average": round(causal_average, 6),
        "strong_causal_dimensions": strong,
        "dimensions": scores,
        "merge": merge,
        "reason": "shared causal mechanism/cost/escalation/payoff" if merge else "material causal divergence",
        "strongest_dimensions": strongest,
    }


def candidate_quality_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (str(candidate.get("candidate_id") or candidate.get("id")),)


def cluster_candidates(candidates: list[dict[str, Any]], lane: str, run_id: str, input_hash: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ids = [str(item.get("candidate_id") or item.get("id")) for item in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("CANDIDATE_IDS_DUPLICATE_ACROSS_BRANCHES")
    edges: dict[str, set[str]] = {candidate_id: set() for candidate_id in ids}
    pairs: list[dict[str, Any]] = []
    nearest: dict[str, tuple[str, float]] = {}
    for index, left in enumerate(candidates):
        left_id = ids[index]
        for right_index in range(index + 1, len(candidates)):
            right, right_id = candidates[right_index], ids[right_index]
            result = fingerprint_similarity(left["structural_fingerprint"], right["structural_fingerprint"], lane)
            pairs.append({"left": left_id, "right": right_id, **result})
            if result["merge"]:
                edges[left_id].add(right_id)
                edges[right_id].add(left_id)
            for source, target in ((left_id, right_id), (right_id, left_id)):
                if source not in nearest or result["overall"] > nearest[source][1]:
                    nearest[source] = (target, result["overall"])
    by_id = dict(zip(ids, candidates))
    visited: set[str] = set()
    clusters: list[dict[str, Any]] = []
    representatives: list[dict[str, Any]] = []
    for candidate_id in sorted(ids):
        if candidate_id in visited:
            continue
        stack, component = [candidate_id], []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            stack.extend(sorted(edges[current] - visited))
        representative_id = sorted(component, key=lambda item: candidate_quality_key(by_id[item]))[0]
        representatives.append(by_id[representative_id])
        clusters.append({
            "cluster_id": f"CL-{len(clusters) + 1:03d}",
            "members": sorted(component),
            "representative_id": representative_id,
            "representative_rule": "stable candidate id within a validated structural cluster; generator scores are ignored; independent scores start after clustering",
            "reason": "structural causal cluster" if len(component) > 1 else "no merge-level structural neighbor",
        })
    audit = seal({
        "stage": "structural_cluster_audit",
        "schema_version": SCHEMA_VERSION,
        "lane": lane,
        "run_id": run_id,
        "input_hash": input_hash,
        "policy": CLUSTER_POLICY,
        "dimension_weights": FINGERPRINT_WEIGHTS,
        "pairwise_similarity": pairs,
        "nearest_neighbors": {
            candidate_id: {"candidate_id": value[0], "similarity": value[1]}
            for candidate_id, value in sorted(nearest.items())
        },
        "clusters": clusters,
        "representative_ids": [str(item.get("candidate_id") or item.get("id")) for item in representatives],
    })
    return representatives, audit


def validate_audit_envelope(
    audit: dict[str, Any], stage: str, reviewer_kind: str, candidate_ids: set[str],
    lane: str, run_id: str, input_hash: str, packet_hash: str, profile_hash: str,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    expected = {
        "stage": stage, "schema_version": SCHEMA_VERSION, "lane": lane,
        "run_id": run_id, "input_hash": input_hash, "evidence_packet_hash": packet_hash,
        "target_profile_hash": profile_hash,
    }
    for key, value in expected.items():
        if audit.get(key) != value:
            failures.append({"reason": f"{stage.upper()}_{key.upper()}_INVALID"})
    if not verify_seal(audit):
        failures.append({"reason": f"{stage.upper()}_OUTPUT_HASH_INVALID"})
    receipt = audit.get("reviewer_receipt") if isinstance(audit, dict) else None
    if not isinstance(receipt, dict):
        return [*failures, {"reason": "REVIEWER_RECEIPT_MISSING", "reviewer_kind": reviewer_kind}]
    delegation_id = str(receipt.get("delegation_id") or "")
    task_index = receipt.get("task_index")
    controller_receipt = all(key in receipt for key in ("job_id", "session_id", "attempt"))
    controller_invalid = controller_receipt and (
        not substantive(receipt.get("job_id"))
        or not substantive(receipt.get("session_id"))
        or not isinstance(receipt.get("attempt"), int)
        or receipt.get("attempt") < 1
        or receipt.get("reviewer_run_id") != receipt.get("session_id")
    )
    legacy_invalid = not controller_receipt and (
        not delegation_id
        or delegation_id.casefold().startswith(("manual", "synthetic", "fix"))
        or not isinstance(task_index, int)
        or receipt.get("reviewer_run_id") != f"{delegation_id}:{task_index}"
    )
    if (
        receipt.get("reviewer_kind") != reviewer_kind
        or receipt.get("independent_context") is not True
        or receipt.get("evidence_packet_hash") != packet_hash
        or set(map(str, receipt.get("reviewed_candidate_ids", []))) != candidate_ids
        or str(receipt.get("status") or "").strip().casefold() not in ("passed", "pass")
        or not isinstance(receipt.get("findings"), list)
        or controller_invalid
        or legacy_invalid
        or not substantive(receipt.get("reviewer_agent_id"))
        or not substantive(receipt.get("delegated_task_id"))
    ):
        failures.append({"reason": "REVIEWER_RECEIPT_INVALID", "reviewer_kind": reviewer_kind})
    return failures


def validate_market_audit(
    audit: dict[str, Any], candidate_ids: set[str], lane: str, run_id: str,
    input_hash: str, packet_hash: str, profile: dict[str, Any], *, allow_rejections: bool = False,
) -> list[dict[str, Any]]:
    failures = validate_audit_envelope(
        audit, "market_editor_review", "market_coverage", candidate_ids,
        lane, run_id, input_hash, packet_hash, profile["output_hash"],
    )
    records = audit.get("candidates") if isinstance(audit, dict) else None
    if not isinstance(records, dict) or set(records) != candidate_ids:
        return [*failures, {"reason": "MARKET_EDITOR_CANDIDATE_SET_MISMATCH"}]
    calibrated_vectors: list[tuple[float, ...]] = []
    for candidate_id, record in records.items():
        if not isinstance(record, dict):
            failures.append({"reason": "MARKET_EDITOR_RECORD_INVALID", "candidate_id": candidate_id})
            continue
        required = {"entry_promise", "reward_cycle", "platform_fit", "activity_fit"}
        required.add("short_closure" if lane == "short" else "three_stage_engine")
        checks = record.get("checks") if isinstance(record, dict) else None
        status_value = str(record.get("status") or "").strip().casefold()
        if not allow_rejections and (status_value not in ("passed", "pass") or not isinstance(checks, dict) or any(checks.get(key) is not True for key in required)):
            failures.append({"reason": "MARKET_EDITOR_REJECTED", "candidate_id": candidate_id})
        is_rejected = allow_rejections and status_value == "rejected"
        # L3 channel enforcement (2026-09-02, ported from 8/16 design): every market
        # record must carry an explicit channel verdict and protagonist perspective.
        # These checks live OUTSIDE `if not is_rejected` on purpose: a mismatch record's
        # legal expression IS status=rejected, so rejecting records are exactly the ones
        # that must still be validated here.
        cvd = str(record.get("channel_verdict") or "").strip().casefold()
        persp = str(record.get("protagonist_perspective") or "").strip().casefold()
        if cvd not in {"fit", "partial", "mismatch"}:
            failures.append({"reason": "MARKET_CHANNEL_VERDICT_INVALID", "candidate_id": candidate_id})
        if persp not in {"male", "female", "neutral"}:
            failures.append({"reason": "MARKET_PROTAGONIST_PERSPECTIVE_INVALID", "candidate_id": candidate_id})
        if cvd == "mismatch" and status_value != "rejected":
            failures.append({"reason": "CHANNEL_MISMATCH_NOT_REJECTED", "candidate_id": candidate_id})
        run_channel = str(profile.get("audience_channel") or "").casefold()
        opposite = {"male": "female", "female": "male"}
        if (
            cvd == "fit"
            and persp in opposite
            and opposite[persp] == run_channel
        ):
            # Same as 8/16 semantics: opposite gender + full fit is a contradiction;
            # partial is acceptable (male channel can host female leads and vice versa).
            failures.append({"reason": "CHANNEL_VERDICT_CONTRADICTS_PERSPECTIVE", "candidate_id": candidate_id})
        cycle = record.get("reward_cycle") if isinstance(record, dict) else None
        if not is_rejected and not (isinstance(cycle, list) and 4 <= len(cycle) <= 6 and all(substantive(item) for item in cycle)):
            failures.append({"reason": "READING_RETURN_CYCLE_INVALID", "candidate_id": candidate_id})
        if not is_rejected:
            for field in ("entry_promise", "platform_fit", "channel_fit", "causal_consistency"):
                if not substantive(record.get(field)):
                    failures.append({"reason": f"MARKET_{field.upper()}_NOT_SUBSTANTIVE", "candidate_id": candidate_id})
        if record.get("contradictions") != [] and not is_rejected:
            failures.append({"reason": "MARKET_CAUSAL_CONTRADICTION_PRESENT", "candidate_id": candidate_id})
        objectives = record.get("calibrated_objectives")
        rationales = record.get("objective_rationales")
        if not is_rejected:
            if not isinstance(objectives, dict):
                failures.append({"reason": "MARKET_CALIBRATED_OBJECTIVES_MISSING", "candidate_id": candidate_id})
            else:
                vector_valid = True
                for objective in OBJECTIVES:
                    raw_value = objectives.get(objective)
                    value = raw_value.get("score") if isinstance(raw_value, dict) else raw_value
                    if isinstance(value, str):
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            try:
                                value = float(value)
                            except (ValueError, TypeError):
                                pass
                    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 1 <= value <= 5:
                        failures.append({"reason": "MARKET_CALIBRATED_OBJECTIVE_INVALID", "candidate_id": candidate_id, "objective": objective})
                        vector_valid = False
                    rationale_value = (rationales or {}).get(objective) if isinstance(rationales, dict) else None
                    if not substantive(rationale_value):
                        nested_rationale = raw_value.get("rationale") if isinstance(raw_value, dict) else None
                        if not substantive(nested_rationale):
                            failures.append({"reason": "MARKET_OBJECTIVE_RATIONALE_MISSING", "candidate_id": candidate_id, "objective": objective})
                if vector_valid:
                    calibrated_vectors.append(tuple(float(objectives.get(obj).get("score") if isinstance(objectives.get(obj), dict) else objectives.get(obj)) for obj in OBJECTIVES))
            if lane == "short":
                budget = record.get("complexity_budget")
                mechanism_count = budget.get("mechanism_count") if isinstance(budget, dict) else None
                if isinstance(mechanism_count, str):
                    try:
                        mechanism_count = int(mechanism_count)
                    except (ValueError, TypeError):
                        pass
                if (
                    not isinstance(budget, dict)
                    or not isinstance(mechanism_count, int)
                    or not 1 <= mechanism_count <= 3
                    or not substantive(budget.get("assessment"))
                ):
                    failures.append({"reason": "SHORT_COMPLEXITY_BUDGET_INVALID", "candidate_id": candidate_id})
            else:
                stages = record.get("three_stage_engine")
                required_stage_fields = {"goal", "relationship_change", "world_expansion", "irreversible_change", "stage_payoff"}
                if not isinstance(stages, dict) or set(stages) != {"300k", "800k", "1500k"}:
                    failures.append({"reason": "LONG_THREE_STAGE_REVIEW_MISSING", "candidate_id": candidate_id})
                elif any(
                    not isinstance(row, dict) or any(not substantive(row.get(field)) for field in required_stage_fields)
                    for row in stages.values()
                ):
                    failures.append({"reason": "LONG_THREE_STAGE_REVIEW_NOT_SUBSTANTIVE", "candidate_id": candidate_id})
            activity_fit = record.get("activity_fit")
            if profile.get("portfolio_track") == "general":
                if activity_fit != "not_applicable":
                    failures.append({"reason": "GENERAL_REVIEW_ACTIVITY_FIT_INVALID", "candidate_id": candidate_id})
            elif (
                not isinstance(activity_fit, dict)
                or activity_fit.get("activity_id") != profile["activity"].get("activity_id")
                or not substantive_list(activity_fit.get("matched_requirements"))
                or activity_fit.get("violations") != []
            ):
                failures.append({"reason": "ACTIVITY_REVIEW_FIT_INVALID", "candidate_id": candidate_id})
    if len(calibrated_vectors) >= 4:
        frequencies = {vector: calibrated_vectors.count(vector) for vector in set(calibrated_vectors)}
        most_used = max(frequencies.values())
        if len(frequencies) == 1:
            failures.append({'reason': 'MARKET_SCORE_VECTORS_UNIFORM'})
        elif most_used >= 3 and most_used * 2 > len(calibrated_vectors):
            failures.append({'reason': 'MARKET_SCORE_VECTOR_OVERUSED', 'observed': most_used, 'reviewed': len(calibrated_vectors)})
    return failures


def validate_originality_audit(
    audit: dict[str, Any], candidate_ids: set[str], lane: str, run_id: str,
    input_hash: str, packet_hash: str, profile: dict[str, Any],
    reference_registry: dict[str, set[str]], *, allow_rejections: bool = False,
) -> list[dict[str, Any]]:
    failures = validate_audit_envelope(
        audit, "originality_redteam", "originality_craft", candidate_ids,
        lane, run_id, input_hash, packet_hash, profile["output_hash"],
    )
    records = audit.get("candidates") if isinstance(audit, dict) else None
    if not isinstance(records, dict) or set(records) != candidate_ids:
        return [*failures, {"reason": "ORIGINALITY_REDTEAM_CANDIDATE_SET_MISMATCH"}]
    for candidate_id, record in records.items():
        if not isinstance(record, dict):
            failures.append({"reason": "ORIGINALITY_RECORD_INVALID", "candidate_id": candidate_id})
            continue
        layers = record.get("layers") if isinstance(record, dict) else None
        required_layers = {"expression", "semantic", "structural", "causal"}
        if not isinstance(layers, dict) or set(layers) != required_layers:
            failures.append({"reason": "ORIGINALITY_LAYER_ORDER_INVALID", "candidate_id": candidate_id})
            continue
        if not allow_rejections and any(not isinstance(layers[name], dict) or str(layers[name].get("status") or "").strip().casefold() not in ("passed", "pass") for name in layers):
            failures.append({"reason": "ORIGINALITY_REDTEAM_REJECTED", "candidate_id": candidate_id})
        if not allow_rejections and any(isinstance(layers[name], dict) and layers[name].get("high_recognition_collision") is True for name in layers):
            failures.append({"reason": "HIGH_RECOGNITION_COLLISION", "candidate_id": candidate_id})
        if (
            not substantive(record.get('closest_work'))
            or not substantive(record.get('causal_difference'))
            or low_information(record.get('closest_work'))
            or low_information(record.get('causal_difference'))
        ):
            failures.append({"reason": "CAUSAL_DIFFERENCE_AUDIT_MISSING", "candidate_id": candidate_id})
        reference = record.get("closest_work_reference")
        if isinstance(reference, dict):
            evidence_id = str(reference.get("evidence_id") or "")
            direct_url = normalize_reference_url(reference.get("direct_url"))
            reference_valid = (
                substantive(reference.get("identifier"))
                and (
                    evidence_id in reference_registry["evidence_ids"]
                    or direct_url in reference_registry["urls"]
                )
            )
        elif isinstance(reference, str) and substantive(reference):
            normalized_url = normalize_reference_url(reference)
            reference_valid = (
                reference in reference_registry["evidence_ids"]
                or normalized_url in reference_registry["urls"]
            )
        else:
            reference_valid = False
        if not reference_valid:
            failures.append({"reason": "CLOSEST_WORK_REFERENCE_INVALID", "candidate_id": candidate_id})
        risk = record.get("calibrated_originality_risk")
        if isinstance(risk, str):
            try:
                risk = int(risk)
            except (ValueError, TypeError):
                try:
                    risk = float(risk)
                except (ValueError, TypeError):
                    pass
        if not isinstance(risk, (int, float)) or isinstance(risk, bool) or not 1 <= risk <= 5:
            failures.append({"reason": "ORIGINALITY_RISK_CALIBRATION_INVALID", "candidate_id": candidate_id})
        if not substantive(record.get("originality_risk_rationale")):
            failures.append({"reason": "ORIGINALITY_RISK_RATIONALE_MISSING", "candidate_id": candidate_id})
        evidence_methods = set(map(str, record.get("evidence_methods", [])))
        if evidence_methods & {"perplexity", "ai_detector", "ai_probability"}:
            failures.append({"reason": "AI_STYLE_METRIC_USED_AS_ORIGINALITY_EVIDENCE", "candidate_id": candidate_id})
    return failures

def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_values, right_values = left["portfolio_objectives"], right["portfolio_objectives"]
    no_worse = all(
        left_values[key] >= right_values[key] if key in MAXIMIZE else left_values[key] <= right_values[key]
        for key in OBJECTIVES
    )
    strictly_better = any(
        left_values[key] > right_values[key] if key in MAXIMIZE else left_values[key] < right_values[key]
        for key in OBJECTIVES
    )
    return no_worse and strictly_better


def pareto_frontier(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [candidate for candidate in candidates if not any(dominates(other, candidate) for other in candidates if other is not candidate)]


def mechanism_signature(candidate: dict[str, Any]) -> str:
    fingerprint = candidate.get("structural_fingerprint") or {}
    families = {
        family
        for key in CAUSAL_DIMENSIONS
        for family in mechanism_family_labels(fingerprint.get(key))
    }
    return "+".join(sorted(families)) if families else "unclassified"


def select_frontier_portfolio(frontier: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """Select only nondominated candidates while preferring branch/mechanism diversity."""
    ranked = sorted(frontier, key=lambda row: str(row.get("candidate_id") or row.get("id")))
    selected: list[dict[str, Any]] = []
    branches: set[str] = set()
    signatures: set[str] = set()
    for candidate in ranked:
        branch = str(candidate.get("generator_branch") or "")
        signature = mechanism_signature(candidate)
        if branch not in branches or signature not in signatures:
            selected.append(candidate)
            branches.add(branch)
            signatures.add(signature)
        if len(selected) >= limit:
            break
    for candidate in ranked:
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected[:limit]


def pareto_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    return math.sqrt(sum((float(left["portfolio_objectives"][key]) - float(right["portfolio_objectives"][key])) ** 2 for key in OBJECTIVES))


def cap_frontier(frontier: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    if len(frontier) <= limit:
        return sorted(frontier, key=lambda item: str(item.get("candidate_id") or item.get("id")))
    selected: list[dict[str, Any]] = []
    for objective in OBJECTIVES:
        ordered = sorted(
            frontier,
            key=lambda item: (
                -float(item["portfolio_objectives"][objective]) if objective in MAXIMIZE else float(item["portfolio_objectives"][objective]),
                str(item.get("candidate_id") or item.get("id")),
            ),
        )
        if ordered[0] not in selected:
            selected.append(ordered[0])
        if len(selected) == limit:
            break
    while len(selected) < limit:
        remaining = [item for item in frontier if item not in selected]
        chosen = max(
            remaining,
            key=lambda item: (min(pareto_distance(item, prior) for prior in selected), str(item.get("candidate_id") or item.get("id"))),
        )
        selected.append(chosen)
    return selected


def cap_frontier_with_branch_coverage(frontier: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    if len(frontier) <= limit:
        return sorted(frontier, key=lambda item: str(item.get("candidate_id") or item.get("id")))
    selected: list[dict[str, Any]] = []
    for branch_id in sorted(BRANCH_ROLES):
        choices = [item for item in frontier if item.get("generator_branch") == branch_id]
        chosen = min(
            choices,
            key=lambda item: (
                -sum(float(item["portfolio_objectives"][key]) for key in MAXIMIZE)
                + float(item["portfolio_objectives"]["originality_risk"]),
                str(item.get("candidate_id") or item.get("id")),
            ),
        )
        selected.append(chosen)
    for candidate in cap_frontier(frontier, limit):
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) == limit:
            break
    return selected


def validate_card(
    candidate: dict[str, Any], lane: str, originality: dict[str, Any], profile: dict[str, Any],
) -> list[str]:
    reasons = candidate_card_shape_failures(candidate, lane, profile)
    card = candidate.get("candidate_card") or {}
    similarity = normalized_similarity(card.get("one_line_concept"), originality.get("closest_work"))
    risk = originality.get("calibrated_originality_risk")
    if similarity >= 0.72 and (not isinstance(risk, (int, float)) or risk < 4):
        reasons.append("CARD_CLOSEST_WORK_COLLISION_UNRESOLVED")
    if card.get("evidence_atom_ids") != candidate.get("cited_atom_ids"):
        reasons.append("CARD_ATOM_CITATION_MISMATCH")
    return reasons


def make_delegation_provenance(
    run_id: str,
    generator_delegation_id: str,
    reviewer_delegation_id: str,
    branches: list[dict[str, Any]],
    market_audit: dict[str, Any],
    originality_audit: dict[str, Any],
) -> dict[str, Any]:
    if not DELEGATION_ID_PATTERN.fullmatch(generator_delegation_id):
        raise ValueError("GENERATOR_DELEGATION_ID_INVALID")
    if not DELEGATION_ID_PATTERN.fullmatch(reviewer_delegation_id):
        raise ValueError("REVIEWER_DELEGATION_ID_INVALID")
    if generator_delegation_id == reviewer_delegation_id:
        raise ValueError("DELEGATION_BATCHES_MUST_BE_DISTINCT")
    branch_hashes = {
        str(branch.get("branch_id")): branch.get("output_hash")
        for branch in branches
        if isinstance(branch, dict)
    }
    return seal({
        "stage": "delegation_provenance",
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generator_batch": {
            "delegation_id": generator_delegation_id,
            "task_count": 3,
            "artifact_hashes": branch_hashes,
        },
        "reviewer_batch": {
            "delegation_id": reviewer_delegation_id,
            "task_count": 2,
            "artifact_hashes": {
                "market_coverage": market_audit.get("output_hash"),
                "originality_craft": originality_audit.get("output_hash"),
            },
        },
    })


def make_job_provenance(
    run_id: str,
    generator_receipts: dict[str, dict[str, Any]],
    reviewer_receipts: dict[str, dict[str, Any]],
    branches: list[dict[str, Any]],
    market_audit: dict[str, Any],
    originality_audit: dict[str, Any],
) -> dict[str, Any]:
    if set(generator_receipts) != set(BRANCH_ROLES):
        raise ValueError("GENERATOR_JOB_RECEIPTS_INVALID")
    if set(reviewer_receipts) != {"market_coverage", "originality_craft"}:
        raise ValueError("REVIEWER_JOB_RECEIPTS_INVALID")
    receipts = [*generator_receipts.values(), *reviewer_receipts.values()]
    sessions = [str(row.get("session_id") or "") for row in receipts]
    if any(not value for value in sessions) or len(set(sessions)) != len(sessions):
        raise ValueError("JOB_SESSIONS_NOT_ISOLATED")
    return seal({
        "stage": "delegation_provenance",
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "job_receipts": {
            "generation": generator_receipts,
            "review": reviewer_receipts,
        },
        "artifact_hashes": {
            "generation": {
                str(branch.get("branch_id")): branch.get("output_hash")
                for branch in branches
                if isinstance(branch, dict)
            },
            "review": {
                "market_coverage": market_audit.get("output_hash"),
                "originality_craft": originality_audit.get("output_hash"),
            },
        },
    })


def delegation_provenance_failures(
    provenance: dict[str, Any] | None,
    run_id: str,
    branches: list[dict[str, Any]],
    market_audit: dict[str, Any],
    originality_audit: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(provenance, dict):
        return [{"reason": "DELEGATION_PROVENANCE_MISSING"}]
    failures: list[dict[str, Any]] = []
    if (
        provenance.get("stage") != "delegation_provenance"
        or provenance.get("schema_version") != SCHEMA_VERSION
        or provenance.get("run_id") != run_id
        or not verify_seal(provenance)
    ):
        failures.append({"reason": "DELEGATION_PROVENANCE_INVALID"})
        return failures
    job_receipts = provenance.get("job_receipts")
    if isinstance(job_receipts, dict):
        generation = job_receipts.get("generation")
        review = job_receipts.get("review")
        if not isinstance(generation, dict) or set(generation) != set(BRANCH_ROLES):
            failures.append({"reason": "GENERATOR_JOB_RECEIPTS_INVALID"})
        if not isinstance(review, dict) or set(review) != {"market_coverage", "originality_craft"}:
            failures.append({"reason": "REVIEWER_JOB_RECEIPTS_INVALID"})
        rows = [
            row for group in (generation, review) if isinstance(group, dict)
            for row in group.values() if isinstance(row, dict)
        ]
        sessions = [str(row.get("session_id") or "") for row in rows]
        if any(not value for value in sessions) or len(set(sessions)) != len(sessions):
            failures.append({"reason": "JOB_SESSIONS_NOT_ISOLATED"})
        expected = {
            "generation": {
                str(branch.get("branch_id")): branch.get("output_hash")
                for branch in branches if isinstance(branch, dict)
            },
            "review": {
                "market_coverage": market_audit.get("output_hash"),
                "originality_craft": originality_audit.get("output_hash"),
            },
        }
        if provenance.get("artifact_hashes") != expected:
            failures.append({"reason": "JOB_ARTIFACT_PROVENANCE_MISMATCH"})
        return failures
    generator_batch = provenance.get("generator_batch")
    reviewer_batch = provenance.get("reviewer_batch")
    if not isinstance(generator_batch, dict) or not isinstance(reviewer_batch, dict):
        return [{"reason": "DELEGATION_PROVENANCE_BATCHES_INVALID"}]
    generator_id = str(generator_batch.get("delegation_id") or "")
    reviewer_id = str(reviewer_batch.get("delegation_id") or "")
    if (
        not DELEGATION_ID_PATTERN.fullmatch(generator_id)
        or not DELEGATION_ID_PATTERN.fullmatch(reviewer_id)
        or generator_id == reviewer_id
    ):
        failures.append({"reason": "DELEGATION_PROVENANCE_IDS_INVALID"})
    expected_branch_hashes = {
        str(branch.get("branch_id")): branch.get("output_hash")
        for branch in branches
        if isinstance(branch, dict)
    }
    if generator_batch.get("task_count") != 3 or generator_batch.get("artifact_hashes") != expected_branch_hashes:
        failures.append({"reason": "GENERATOR_DELEGATION_PROVENANCE_MISMATCH"})
    expected_review_hashes = {
        "market_coverage": market_audit.get("output_hash"),
        "originality_craft": originality_audit.get("output_hash"),
    }
    if reviewer_batch.get("task_count") != 2 or reviewer_batch.get("artifact_hashes") != expected_review_hashes:
        failures.append({"reason": "REVIEWER_DELEGATION_PROVENANCE_MISMATCH"})
    market_receipt = market_audit.get("reviewer_receipt", {})
    originality_receipt = originality_audit.get("reviewer_receipt", {})
    if (
        market_receipt.get("delegation_id") != reviewer_id
        or originality_receipt.get("delegation_id") != reviewer_id
        or market_receipt.get("task_index") != 0
        or originality_receipt.get("task_index") != 1
    ):
        failures.append({"reason": "REVIEWER_RUNTIME_DELEGATION_ID_MISMATCH"})
    return failures


def cluster_generation(
    packet: dict[str, Any], atom_bundle: dict[str, Any], contexts_bundle: dict[str, Any],
    branches: list[dict[str, Any]], profile: dict[str, Any], lane: str, run_id: str,
    minimum_candidates: int = 3,
) -> dict[str, Any]:
    failures, atom_audit = atom_failures(packet, atom_bundle, lane)
    failures.extend(profile_failures(profile))
    if not verify_seal(profile):
        failures.append({"reason": "PROFILE_OUTPUT_HASH_INVALID"})
    packet_hash = validate_packet(packet, lane)
    if (
        contexts_bundle.get("stage") != "generation_contexts"
        or contexts_bundle.get("lane") != lane
        or contexts_bundle.get("run_id") != run_id
        or contexts_bundle.get("evidence_packet_hash") != packet_hash
        or contexts_bundle.get("target_profile_hash") != profile.get("output_hash")
        or not verify_seal(contexts_bundle)
    ):
        failures.append({"reason": "GENERATION_CONTEXTS_INVALID"})
    contexts = contexts_bundle.get("contexts") if isinstance(contexts_bundle.get("contexts"), dict) else {}
    by_branch = {str(branch.get("branch_id")): branch for branch in branches}
    if set(by_branch) != set(BRANCH_ROLES):
        failures.append({"reason": "THREE_GENERATION_BRANCHES_REQUIRED", "observed": sorted(by_branch)})
    candidates: list[dict[str, Any]] = []
    for branch_id in sorted(BRANCH_ROLES):
        context, branch = contexts.get(branch_id), by_branch.get(branch_id)
        if not isinstance(context, dict) or not isinstance(branch, dict):
            continue
        failures.extend(branch_failures(branch, context, profile, lane, minimum_candidates))
        candidates.extend(branch.get("candidates") or [])
    input_hash = canonical_hash([by_branch[key].get("output_hash") for key in sorted(by_branch)])
    if failures:
        return seal({
            "stage": "clustered_representatives", "schema_version": SCHEMA_VERSION,
            "lane": lane, "run_id": run_id, "input_hash": input_hash,
            "evidence_packet_hash": packet_hash, "atom_audit_hash": atom_audit.get("output_hash"),
            "status": "blocked", "failures": failures, "diagnostic_only": True,
        })
    representatives, cluster_audit = cluster_candidates(candidates, lane, run_id, input_hash)
    representative_counts = {
        branch_id: sum(item.get("generator_branch") == branch_id for item in representatives)
        for branch_id in BRANCH_ROLES
    }
    for branch_id, count in representative_counts.items():
        if count < 1:
            failures.append({
                "reason": "BRANCH_REPRESENTATIVE_DIVERSITY_INSUFFICIENT",
                "branch_id": branch_id, "observed": count, "required": 1,
            })
    if failures:
        return seal({
            "stage": "clustered_representatives", "schema_version": SCHEMA_VERSION,
            "lane": lane, "run_id": run_id, "input_hash": input_hash,
            "evidence_packet_hash": packet_hash, "target_profile_hash": profile.get("output_hash"),
            "atom_audit_hash": atom_audit.get("output_hash"), "status": "blocked",
            "failures": failures, "cluster_audit": cluster_audit, "diagnostic_only": True,
        })
    return seal({
        "stage": "clustered_representatives", "schema_version": SCHEMA_VERSION,
        "lane": lane, "run_id": run_id, "input_hash": input_hash,
        "evidence_packet_hash": packet_hash, "atom_audit_hash": atom_audit["output_hash"],
        "target_profile_hash": profile["output_hash"],
        "status": "representatives_ready", "failures": [],
        "cluster_audit": cluster_audit,
        "representative_ids": [str(item.get("candidate_id") or item.get("id")) for item in representatives],
        "representatives": representatives,
        "recovery_status": "cluster_checkpoint",
    })

def assemble_portfolio(
    packet: dict[str, Any], atom_bundle: dict[str, Any], contexts_bundle: dict[str, Any],
    branches: list[dict[str, Any]], market_audit: dict[str, Any], originality_audit: dict[str, Any],
    profile: dict[str, Any], lane: str, run_id: str,
    provenance: dict[str, Any] | None = None, clustered: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clustered = clustered or cluster_generation(packet, atom_bundle, contexts_bundle, branches, profile, lane, run_id)
    failures = list(clustered.get("failures", []))
    if (
        clustered.get("status") != "representatives_ready"
        or clustered.get("lane") != lane
        or clustered.get("run_id") != run_id
        or clustered.get("target_profile_hash") != profile.get("output_hash")
        or not verify_seal(clustered)
    ):
        if not failures:
            failures.append({"reason": "CLUSTER_CHECKPOINT_INVALID"})
        return seal({
            "stage": "candidate_portfolio_gate", "schema_version": SCHEMA_VERSION,
            "lane": lane, "run_id": run_id, "input_hash": clustered.get("output_hash"),
            "portfolio_track": profile.get("portfolio_track"), "target_profile_hash": profile.get("output_hash"),
            "status": "candidate_generation_failed", "formal_candidate_generation": "blocked",
            "failures": failures, "diagnostic_only": True,
        })
    atom_audit_hash = clustered["atom_audit_hash"]
    representatives = clustered["representatives"]
    cluster_audit = clustered["cluster_audit"]
    representative_ids = {str(item.get("candidate_id") or item.get("id")) for item in representatives}
    packet_hash = validate_packet(packet, lane)
    failures.extend(delegation_provenance_failures(
        provenance, run_id, branches, market_audit, originality_audit,
    ))
    market_failures = validate_market_audit(
        market_audit, representative_ids, lane, run_id, cluster_audit["output_hash"], packet_hash, profile,
        allow_rejections=True,
    )
    originality_failures = validate_originality_audit(
        originality_audit, representative_ids, lane, run_id, cluster_audit["output_hash"], packet_hash, profile,
        evidence_reference_registry(packet),
        allow_rejections=True,
    )
    market_receipt = market_audit.get("reviewer_receipt", {})
    originality_receipt = originality_audit.get("reviewer_receipt", {})
    if market_receipt.get("reviewer_run_id") == originality_receipt.get("reviewer_run_id"):
        failures.append({"reason": "REVIEWER_CONTEXTS_NOT_ISOLATED"})
    failures.extend(market_failures + originality_failures)
    if failures:
        return seal({
            "stage": "candidate_portfolio_gate", "schema_version": SCHEMA_VERSION,
            "lane": lane, "run_id": run_id, "input_hash": cluster_audit["output_hash"],
            "portfolio_track": profile["portfolio_track"], "target_profile_hash": profile["output_hash"],
            "status": "candidate_generation_failed", "formal_candidate_generation": "blocked",
            "failures": failures, "cluster_audit": cluster_audit, "diagnostic_only": True,
        })

    # Veto only on explicit rejection markers. Any other status vocabulary
    # (pass / passed / acceptable / 通过 / ok / yes / ...) is a pass variant —
    # status wording is model-surface drift and must never veto a candidate.
    _MARKET_REJECT_STATUSES = {"reject", "rejected", "fail", "failed", "blocked", "deny", "denied"}
    market_vetoes = {
        candidate_id for candidate_id, record in market_audit["candidates"].items()
        if (
            isinstance(record.get("checks"), dict)
            and any(value is False for value in record["checks"].values())
        )
        or str(record.get("status", "")).strip().casefold() in _MARKET_REJECT_STATUSES
        # L3 (2026-09-02): channel mismatch vetoes the candidate even if status wording
        # drifts; validator guarantees mismatch ⇒ status=rejected, this is explicit policy.
        or str(record.get("channel_verdict", "")).strip().casefold() == "mismatch"
    }
    _ORIGINALITY_VETO_STATUSES = {"collision", "rejected", "plagiarism"}
    originality_vetoes = {
        candidate_id for candidate_id, record in originality_audit["candidates"].items()
        if not isinstance(record.get("layers"), dict)
        or any(
            isinstance(layer, dict)
            and str(layer.get("status", "")).lower() in _ORIGINALITY_VETO_STATUSES
            for layer in record.get("layers", {}).values()
        )
    }
    vetoed_ids = market_vetoes | originality_vetoes
    calibrated: list[dict[str, Any]] = []
    for candidate in representatives:
        candidate_id = str(candidate.get("candidate_id") or candidate.get("id"))
        if candidate_id in vetoed_ids:
            continue
        reviewed = dict(candidate)
        reviewer_record = originality_audit["candidates"][candidate_id]
        generator_card = dict(candidate.get("candidate_card") or {})
        reviewed_card = dict(generator_card)
        reviewed_card["closest_work"] = reviewer_record["closest_work"]
        reviewed_card["causal_difference"] = reviewer_record["causal_difference"]
        reviewed_card["closest_work_reference"] = reviewer_record["closest_work_reference"]
        reviewed["candidate_card"] = reviewed_card
        reviewed["originality_audit"] = {
            "generator_hypothesis": {
                "closest_work": generator_card.get("closest_work"),
                "causal_difference": generator_card.get("causal_difference"),
            },
            "reviewer_finding": {
                "closest_work": reviewer_record["closest_work"],
                "causal_difference": reviewer_record["causal_difference"],
                "closest_work_reference": reviewer_record["closest_work_reference"],
            },
        }
        objectives = dict(market_audit["candidates"][candidate_id]["calibrated_objectives"])
        objectives["originality_risk"] = reviewer_record["calibrated_originality_risk"]
        reviewed["portfolio_objectives"] = objectives
        calibrated.append(reviewed)
    # V4.4.1 branch-constrained Pareto: each source branch competes within itself.
    # This retains only independently market/originality-passed records and uses
    # nondominated choices within each branch. Global Pareto remains diagnostic.
    frontier = pareto_frontier(calibrated)
    branch_frontier = [
        row for branch_id in sorted(BRANCH_ROLES)
        for row in pareto_frontier([
            item for item in calibrated if item.get("generator_branch") == branch_id
        ])
    ]
    selected = select_frontier_portfolio(branch_frontier, 6) if len(branch_frontier) >= 3 else []
    if len(selected) < 3:
        failures.append({"reason": "QUALIFIED_CANDIDATES_INSUFFICIENT", "observed": len(selected), "required": 3})
    observed_branches = sorted({str(item.get("generator_branch")) for item in selected})
    if set(observed_branches) != set(BRANCH_ROLES):
        failures.append({"reason": "FINAL_BRANCH_COVERAGE_INSUFFICIENT",
                         "observed": observed_branches,
                         "missing": sorted(set(BRANCH_ROLES) - set(observed_branches)),
                         "required": sorted(BRANCH_ROLES)})
    observed_signatures = sorted({mechanism_signature(item) for item in selected})
    if len(observed_signatures) < 3:
        failures.append({"reason": "FINAL_MECHANISM_DIVERSITY_INSUFFICIENT", "observed": len(observed_signatures), "required": 3})
    originality_records = originality_audit["candidates"]
    for candidate in selected:
        candidate_id = str(candidate.get("candidate_id") or candidate.get("id"))
        for reason in validate_card(candidate, lane, originality_records[candidate_id], profile):
            failures.append({"reason": reason, "candidate_id": candidate_id})
    if failures:
        selected = []
    cards = [
        {
            "candidate_id": str(candidate.get("candidate_id") or candidate.get("id")),
            "generator_branch": candidate["generator_branch"],
            "mechanism_signature": mechanism_signature(candidate),
            "pareto_objectives": candidate["portfolio_objectives"],
            **candidate["candidate_card"],
            "originality_audit": candidate["originality_audit"],
        }
        for candidate in selected
    ]
    return seal({
        "stage": "candidate_portfolio_gate",
        "schema_version": SCHEMA_VERSION,
        "lane": lane,
        "run_id": run_id,
        "portfolio_track": profile["portfolio_track"],
        "target_profile_hash": profile["output_hash"],
        "target_profile": {
            "target_platform": profile["target_platform"],
            "target_platform_label": profile["target_platform_label"],
            "audience_channel": profile["audience_channel"],
            "activity": profile.get("activity"),
        },
        "input_hash": cluster_audit["output_hash"],
        "evidence_packet_hash": validate_packet(packet, lane),
        "atom_audit_hash": atom_audit_hash,
        "delegation_provenance_hash": provenance.get("output_hash") if isinstance(provenance, dict) else None,
        "cluster_audit": cluster_audit,
        "pareto_frontier_ids": [str(item.get("candidate_id") or item.get("id")) for item in frontier],
        "branch_frontier_ids": [str(item.get("candidate_id") or item.get("id")) for item in branch_frontier],
        "qualified_candidate_branches": sorted({
            str(item.get("generator_branch")) for item in calibrated
        }),
        "reviewed_representative_ids": sorted(representative_ids),
        "vetoed_candidate_ids": sorted(vetoed_ids),
        "generated_count": sum(len(branch.get("candidates") or []) for branch in branches),
        "passed_review_count": len(calibrated),
        "selected_for_delivery_count": len(cards),
        "usable_candidate_count": len(cards) if not failures else 0,
        "candidate_cards": cards,
        "status": "awaiting_user_choice" if not failures else "candidate_generation_failed",
        "formal_candidate_generation": "allowed" if not failures else "blocked",
        "failures": failures,
        "diagnostic_only": bool(failures),
        "route": "await_user_selection" if not failures else None,
        "resume_route": "short-story-writer" if lane == "short" else "novel-init",
        "auto_route_before_user_selection": False,
        "recovery_status": "idempotent_pause_checkpoint" if not failures else "fail_closed",
    })


def make_cards_bundle(portfolio: dict[str, Any]) -> dict[str, Any]:
    cards_stage = "activity_candidate_cards" if portfolio.get("portfolio_track") == "activity" else "pareto_candidate_cards"
    return seal({
        "stage": cards_stage, "schema_version": SCHEMA_VERSION,
        "run_id": portfolio.get("run_id"), "lane": portfolio.get("lane"),
        "input_hash": portfolio.get("output_hash"),
        "portfolio_track": portfolio.get("portfolio_track"),
        "target_profile_hash": portfolio.get("target_profile_hash"),
        "generated_count": portfolio.get("generated_count", 0),
        "passed_review_count": portfolio.get("passed_review_count", 0),
        "selected_for_delivery_count": portfolio.get("selected_for_delivery_count", 0),
        "usable_candidate_count": portfolio.get("usable_candidate_count", 0),
        "status": portfolio.get("status"), "cards": portfolio.get("candidate_cards", []),
        "route": portfolio.get("route"), "resume_route": portfolio.get("resume_route"),
    })


def delivery_failures(
    gate: dict[str, Any], cards_bundle: dict[str, Any], profile: dict[str, Any], output_dir: Path,
) -> list[dict[str, Any]]:
    failures = output_dir_failures(output_dir, profile) + profile_failures(profile)
    if not verify_seal(profile):
        failures.append({"reason": "PROFILE_SEAL_INVALID"})
    if not isinstance(gate, dict) or not verify_seal(gate):
        failures.append({"reason": "PORTFOLIO_GATE_SEAL_INVALID"})
        return failures
    if (
        gate.get("stage") != "candidate_portfolio_gate"
        or gate.get("status") != "awaiting_user_choice"
        or gate.get("formal_candidate_generation") != "allowed"
        or gate.get("failures") != []
        or gate.get("target_profile_hash") != profile.get("output_hash")
        or not substantive(gate.get("input_hash"))
        or not 3 <= len(gate.get("candidate_cards") or []) <= 6
    ):
        failures.append({"reason": "PORTFOLIO_GATE_NOT_DELIVERABLE"})
    if not isinstance(cards_bundle, dict) or not verify_seal(cards_bundle):
        failures.append({"reason": "CANDIDATE_CARDS_SEAL_INVALID"})
        return failures
    expected_stage = "activity_candidate_cards" if profile.get("portfolio_track") == "activity" else "pareto_candidate_cards"
    if (
        cards_bundle.get("stage") != expected_stage
        or cards_bundle.get("input_hash") != gate.get("output_hash")
        or cards_bundle.get("target_profile_hash") != profile.get("output_hash")
        or cards_bundle.get("portfolio_track") != profile.get("portfolio_track")
        or cards_bundle.get("status") != gate.get("status")
        or cards_bundle.get("route") != gate.get("route")
        or cards_bundle.get("resume_route") != gate.get("resume_route")
        or cards_bundle.get("cards") != gate.get("candidate_cards")
    ):
        failures.append({"reason": "CANDIDATE_CARDS_GATE_MISMATCH"})
    return failures


def render_cards(portfolio: dict[str, Any]) -> str:
    title = "Activity candidate zone" if portfolio.get("portfolio_track") == "activity" else "General Pareto candidate cards"
    lines = [f"# {portfolio.get('lane')} {title}", ""]
    if portfolio.get("status") != "awaiting_user_choice":
        return "\n".join(lines + ["Formal candidates are blocked; inspect the diagnostic artifact.", ""])
    lines.extend(["Status: awaiting user choice. No writer route has been started.", ""])
    for index, card in enumerate(portfolio["candidate_cards"], 1):
        lines.extend([
            f"## {index}. {card['one_line_concept']}", "",
            f"- Reader/platform: {card['target_reader']} / {card['target_platform']}",
            f"- Opening 300 beats: {' -> '.join(card['opening_300_beats'])}",
            f"- Reading-return loop: {' -> '.join(card['reward_cycle'])}",
            f"- Three payoffs: {'; '.join(card['three_payoffs'])}",
            f"- Closest work / causal difference: {card['closest_work']} / {card['causal_difference']}",
            f"- Risks: {card['risks']}",
            f"- Activity route: {card['activity_route']}", "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    profile_cmd = sub.add_parser("create-profile")
    profile_cmd.add_argument("--lane", choices=sorted(LANES), required=True)
    profile_cmd.add_argument("--track", choices=sorted(PORTFOLIO_TRACKS), required=True)
    profile_cmd.add_argument("--platform", choices=sorted(TARGET_PLATFORMS), required=True)
    profile_cmd.add_argument("--channel", choices=sorted(AUDIENCE_CHANNELS), required=True)
    profile_cmd.add_argument("--activity", type=Path)
    profile_cmd.add_argument("--output", type=Path, required=True)

    atoms = sub.add_parser("audit-atoms")
    atoms.add_argument("--packet", type=Path, required=True)
    atoms.add_argument("--atoms", type=Path, required=True)
    atoms.add_argument("--lane", choices=sorted(LANES), required=True)
    atoms.add_argument("--output", type=Path, required=True)

    contexts = sub.add_parser("build-contexts")
    contexts.add_argument("--packet", type=Path, required=True)
    contexts.add_argument("--atoms", type=Path, required=True)
    contexts.add_argument("--profile", type=Path, required=True)
    contexts.add_argument("--lane", choices=sorted(LANES), required=True)
    contexts.add_argument("--run-id", required=True)
    contexts.add_argument("--sampling", choices=("standard_stratified", "verbalized_sampling"), default="standard_stratified")
    contexts.add_argument("--vs-outcome", default="not_run")
    contexts.add_argument("--vs-gain", type=float)
    contexts.add_argument("--output", type=Path, required=True)

    cluster = sub.add_parser("cluster")
    cluster.add_argument("--packet", type=Path, required=True)
    cluster.add_argument("--atoms", type=Path, required=True)
    cluster.add_argument("--contexts", type=Path, required=True)
    cluster.add_argument("--profile", type=Path, required=True)
    cluster.add_argument("--branch", type=Path, action="append", required=True)
    cluster.add_argument("--lane", choices=sorted(LANES), required=True)
    cluster.add_argument("--run-id", required=True)
    cluster.add_argument("--output-dir", type=Path, required=True)
    provenance_cmd = sub.add_parser("record-provenance")
    provenance_cmd.add_argument("--run-id", required=True)
    provenance_cmd.add_argument("--generator-delegation-id", required=True)
    provenance_cmd.add_argument("--reviewer-delegation-id", required=True)
    provenance_cmd.add_argument("--branch", type=Path, action="append", required=True)
    provenance_cmd.add_argument("--market-audit", type=Path, required=True)
    provenance_cmd.add_argument("--originality-audit", type=Path, required=True)
    provenance_cmd.add_argument("--output", type=Path, required=True)
    assemble = sub.add_parser("assemble")
    assemble.add_argument("--packet", type=Path, required=True)
    assemble.add_argument("--atoms", type=Path, required=True)
    assemble.add_argument("--contexts", type=Path, required=True)
    assemble.add_argument("--profile", type=Path, required=True)
    assemble.add_argument("--branch", type=Path, action="append", required=True)
    assemble.add_argument("--market-audit", type=Path, required=True)
    assemble.add_argument("--originality-audit", type=Path, required=True)
    assemble.add_argument("--provenance", type=Path, required=True)
    assemble.add_argument("--lane", choices=sorted(LANES), required=True)
    assemble.add_argument("--run-id", required=True)
    assemble.add_argument("--output-dir", type=Path, required=True)
    verify = sub.add_parser("verify-delivery")
    verify.add_argument("--gate", type=Path, required=True)
    verify.add_argument("--cards", type=Path, required=True)
    verify.add_argument("--profile", type=Path, required=True)
    verify.add_argument("--output-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "create-profile":
        activity = load_json(args.activity) if args.activity else None
        try:
            result = make_profile(args.lane, args.track, args.platform, args.channel, activity=activity)
        except ValueError as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
            return 2
        save_json(args.output, result)
        print(json.dumps({"status": "profile_ready", "output_hash": result["output_hash"]}, ensure_ascii=False))
        return 0
    if args.command == "record-provenance":
        result = make_delegation_provenance(
            args.run_id, args.generator_delegation_id, args.reviewer_delegation_id,
            [load_json(path) for path in args.branch],
            load_json(args.market_audit), load_json(args.originality_audit),
        )
        save_json(args.output, result)
        print(json.dumps({"status": "provenance_recorded", "output_hash": result["output_hash"]}, ensure_ascii=False))
        return 0
    if args.command == "verify-delivery":
        failures = delivery_failures(load_json(args.gate), load_json(args.cards), load_json(args.profile), args.output_dir)
        print(json.dumps({"status": "passed" if not failures else "blocked", "failures": failures}, ensure_ascii=False, indent=2))
        return 0 if not failures else 2
    packet = load_json(args.packet)
    atom_bundle = load_json(args.atoms)
    if args.command == "audit-atoms":
        failures, result = atom_failures(packet, atom_bundle, args.lane)
        save_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not failures else 2
    if args.command == "build-contexts":
        try:
            result = build_contexts(
                packet, atom_bundle, load_json(args.profile), args.lane, args.run_id,
                requested_sampling=args.sampling, vs_outcome=args.vs_outcome, vs_gain=args.vs_gain,
            )
        except ValueError as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
            return 2
        save_json(args.output, result)
        print(json.dumps({"status": "contexts_ready", "output_hash": result["output_hash"]}, ensure_ascii=False))
        return 0
    if args.command == "cluster":
        profile = load_json(args.profile)
        path_failures = output_dir_failures(args.output_dir, profile)
        if path_failures:
            print(json.dumps({"status": "blocked", "failures": path_failures}, ensure_ascii=False, indent=2))
            return 2
        result = cluster_generation(
            packet, atom_bundle, load_json(args.contexts), [load_json(path) for path in args.branch],
            profile, args.lane, args.run_id,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        save_json(args.output_dir / "clustered_representatives.json", result)
        if result.get("cluster_audit"):
            save_json(args.output_dir / "structural_cluster_audit.json", result["cluster_audit"])
        print(json.dumps({
            "status": result["status"], "representatives": len(result.get("representatives", [])),
            "failures": result["failures"],
        }, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "representatives_ready" else 2
    profile = load_json(args.profile)
    path_failures = output_dir_failures(args.output_dir, profile)
    if path_failures:
        print(json.dumps({"status": "blocked", "failures": path_failures}, ensure_ascii=False, indent=2))
        return 2
    result = assemble_portfolio(
        packet, atom_bundle, load_json(args.contexts), [load_json(path) for path in args.branch],
        load_json(args.market_audit), load_json(args.originality_audit), profile, args.lane, args.run_id,
        load_json(args.provenance),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    activity_track = result.get("portfolio_track") == "activity"
    gate_name = "activity_portfolio_gate.json" if activity_track else "candidate_portfolio_gate.json"
    cards_stem = "activity_candidate_cards" if activity_track else "pareto_candidate_cards"
    save_json(args.output_dir / gate_name, result)
    if result.get("cluster_audit"):
        save_json(args.output_dir / "structural_cluster_audit.json", result["cluster_audit"])
    cards_bundle = make_cards_bundle(result)
    save_json(args.output_dir / f"{cards_stem}.json", cards_bundle)
    (args.output_dir / f"{cards_stem}.md").write_text(render_cards(result), encoding="utf-8")
    verification = delivery_failures(result, cards_bundle, profile, args.output_dir)
    print(json.dumps({"status": result["status"] if not verification else "blocked", "cards": len(result.get("candidate_cards", [])), "failures": result["failures"] + verification}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "awaiting_user_choice" and not verification else 2


if __name__ == "__main__":
    raise SystemExit(main())
