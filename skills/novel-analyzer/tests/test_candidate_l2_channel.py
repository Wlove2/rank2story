from __future__ import annotations

"""L2 channel-enforcement regression tests (8/15 fix, ported to 4.4.0-rc1 base).

Covers: select_context_atoms channel filter (male/female), eligible<6 fallback,
safe_atom passing channel/channel_basis through while NOT exposing observation,
and neutral-only compatibility. These tests are the persisted form of the
verified-once ad-hoc checks from the 2026-09-02 rollback.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PORTFOLIO = load("candidate_portfolio")

CREATIVE_TYPES = ["desire", "anxiety", "conflict_mechanism", "identity_fantasy", "opening_form", "payoff_mode"]
PRIORITY = {t: i for i, t in enumerate(CREATIVE_TYPES)}


def make_atom(i: int, atype: str, channel: str) -> dict:
    return {
        "atom_id": f"a-{i:04d}", "atom_type": atype, "channel": channel,
        "channel_basis": "test", "source_cohort": "c1", "platform": "fanqie",
        "inference": "x", "confidence": 0.6, "freshness": "recent",
        "claim_key": f"ck-{i:04d}", "stance": "supporting",
        "supporting_evidence_ids": ["ev"], "counter_evidence_ids": [],
    }


def build_pool(n_per_type: int, channels) -> list[dict]:
    atoms, i = [], 0
    for t in CREATIVE_TYPES:
        for _ in range(n_per_type):
            atoms.append(make_atom(i, t, channels[i % len(channels)]))
            i += 1
    return atoms


class L2ChannelFilterTests(unittest.TestCase):
    def test_male_filter_keeps_only_male_and_neutral(self):
        atoms = build_pool(2, ["male", "female", "neutral", "male"])
        sel = PORTFOLIO.select_context_atoms(atoms, "A", PRIORITY, "fanqie", "general", audience_channel="male")
        channels = {a.get("channel") or "neutral" for a in sel}
        self.assertEqual(channels, {"male", "neutral"})
        self.assertGreaterEqual(len(sel), 6)

    def test_female_filter_keeps_only_female_and_neutral(self):
        atoms = build_pool(2, ["male", "female", "neutral", "male"])
        sel = PORTFOLIO.select_context_atoms(atoms, "B", PRIORITY, "fanqie", "general", audience_channel="female")
        channels = {a.get("channel") or "neutral" for a in sel}
        self.assertEqual(channels, {"female", "neutral"})

    def test_eligible_below_six_falls_back_to_full_pool(self):
        atoms = build_pool(1, ["male", "female", "female", "female", "female", "female"])
        sel = PORTFOLIO.select_context_atoms(atoms, "A", PRIORITY, "fanqie", "general", audience_channel="male")
        self.assertIn("female", {a.get("channel") for a in sel})  # fallback keeps female

    def test_neutral_only_pool_is_compatible(self):
        atoms = build_pool(1, ["neutral"])
        sel = PORTFOLIO.select_context_atoms(atoms, "C", PRIORITY, "qimao", "general", audience_channel="male")
        self.assertGreaterEqual(len(sel), 6)

    def test_safe_atom_keeps_channel_fields(self):
        sa = PORTFOLIO.safe_atom(make_atom(99, "desire", "male"))
        self.assertEqual(sa.get("channel"), "male")
        self.assertEqual(sa.get("channel_basis"), "test")

    def test_safe_atom_does_not_expose_observation(self):
        sa = PORTFOLIO.safe_atom({**make_atom(99, "desire", "male"), "observation": "secret"})
        self.assertNotIn("observation", sa)

    def test_select_context_atoms_defaults_to_male_channel(self):
        atoms = build_pool(2, ["male", "female"])
        sel = PORTFOLIO.select_context_atoms(atoms, "A", PRIORITY, "fanqie", "general")
        self.assertEqual({a.get("channel") for a in sel}, {"male"})


if __name__ == "__main__":
    unittest.main()
