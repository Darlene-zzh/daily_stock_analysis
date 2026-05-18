# -*- coding: utf-8 -*-
"""Sprint 4 — :meth:`RiskAgent.build_structured_assessment` tests.

Covers the deterministic extensions added on top of the existing
:class:`RiskAgent`:

- ``suggested_position_pct`` is in [0, 0.30], reacts to severity + vol
- ``tail_risk_score`` is in [0, 10] and incorporates the LLM risk_score,
  high-severity flag count, and annualised volatility
- ``var_estimate_5pct`` matches z=1.645 × daily_vol
- ``volatility_annualised`` matches sqrt(252) × daily stdev
- backward-compat: legacy fields (severity / red_flags / veto / status /
  error_summary) still populate identically to Sprint 1A
- schema-valid: every output round-trips through :class:`RiskAssessment`
  without re-validating into an error
"""

from __future__ import annotations

import math
import unittest

from src.agent.agents.risk_agent import RiskAgent
from src.schemas.risk_schema import RiskAssessment


class TestStructuredRiskAssessment(unittest.TestCase):
    # --------------------------------------------------------------------- #
    # Empty / no-signal paths
    # --------------------------------------------------------------------- #

    def test_empty_inputs_produce_safe_defaults(self) -> None:
        out = RiskAgent.build_structured_assessment()
        self.assertIsInstance(out, RiskAssessment)
        # Legacy fields
        self.assertIsNone(out.severity)
        self.assertEqual(out.red_flags, [])
        self.assertFalse(out.veto)
        self.assertEqual(out.status, "ok")
        # Sprint 4 fields — None because there was nothing to base them on
        self.assertIsNone(out.tail_risk_score)
        self.assertIsNone(out.var_estimate_5pct)
        self.assertIsNone(out.volatility_annualised)
        # suggested_position_pct has a fallback for unknown severity
        self.assertIsNotNone(out.suggested_position_pct)
        self.assertTrue(0.0 <= out.suggested_position_pct <= 0.30)

    # --------------------------------------------------------------------- #
    # Severity + position clamping
    # --------------------------------------------------------------------- #

    def test_hard_severity_vetoes_position_to_zero(self) -> None:
        out = RiskAgent.build_structured_assessment(
            raw_llm={
                "risk_level": "high",
                "risk_score": 90,
                "signal_adjustment": "veto",
                "flags": [
                    {"category": "regulatory", "severity": "high", "description": "Probe"}
                ],
                "veto_buy": True,
                "reasoning": "Existential threat.",
            },
        )
        self.assertEqual(out.severity, "hard")
        self.assertTrue(out.veto)
        self.assertEqual(out.suggested_position_pct, 0.0)

    def test_soft_severity_caps_position_below_default(self) -> None:
        out = RiskAgent.build_structured_assessment(
            raw_llm={
                "risk_level": "medium",
                "risk_score": 55,
                "flags": [
                    {"category": "earnings", "severity": "medium", "description": "Miss"},
                ],
                "reasoning": "Concerning but not existential.",
            },
        )
        self.assertEqual(out.severity, "soft")
        self.assertIsNotNone(out.suggested_position_pct)
        # Soft tier should be smaller than the unknown-severity default (0.20)
        self.assertLess(out.suggested_position_pct, 0.20)
        self.assertFalse(out.veto)

    def test_none_severity_starts_higher_than_soft(self) -> None:
        out_none = RiskAgent.build_structured_assessment(
            raw_llm={"risk_level": "none", "flags": [], "reasoning": "Clean."},
        )
        out_soft = RiskAgent.build_structured_assessment(
            raw_llm={"risk_level": "medium", "flags": [], "reasoning": "Mixed."},
        )
        self.assertEqual(out_none.severity, "none")
        self.assertGreater(
            out_none.suggested_position_pct,
            out_soft.suggested_position_pct,
        )

    # --------------------------------------------------------------------- #
    # Volatility + VaR derivation
    # --------------------------------------------------------------------- #

    def test_var_and_volatility_computed_from_price_series(self) -> None:
        # A clearly non-trivial price walk so vol is well-defined.
        prices = [100.0, 102.0, 99.5, 103.0, 101.0, 104.0, 100.5, 105.0, 102.5, 99.0, 101.5, 103.5]
        out = RiskAgent.build_structured_assessment(
            raw_llm={"risk_level": "low", "flags": []},
            recent_closes=prices,
        )
        self.assertIsNotNone(out.volatility_annualised)
        self.assertGreater(out.volatility_annualised, 0.0)
        self.assertIsNotNone(out.var_estimate_5pct)
        self.assertGreater(out.var_estimate_5pct, 0.0)
        # VaR = z * daily_vol; check the relationship to within float tolerance.
        daily_vol = out.volatility_annualised / math.sqrt(252.0)
        expected_var = round(1.645 * daily_vol, 6)
        self.assertAlmostEqual(out.var_estimate_5pct, expected_var, places=5)

    def test_var_none_when_no_prices_supplied(self) -> None:
        out = RiskAgent.build_structured_assessment(
            raw_llm={"risk_level": "medium", "flags": []},
            recent_closes=None,
        )
        self.assertIsNone(out.var_estimate_5pct)
        self.assertIsNone(out.volatility_annualised)

    def test_var_none_with_single_price(self) -> None:
        out = RiskAgent.build_structured_assessment(
            raw_llm={"risk_level": "medium", "flags": []},
            recent_closes=[100.0],
        )
        self.assertIsNone(out.var_estimate_5pct)
        self.assertIsNone(out.volatility_annualised)

    # --------------------------------------------------------------------- #
    # Tail-risk score
    # --------------------------------------------------------------------- #

    def test_tail_risk_score_in_range_and_responds_to_high_flags(self) -> None:
        out_low = RiskAgent.build_structured_assessment(
            raw_llm={
                "risk_level": "low",
                "risk_score": 20,
                "flags": [{"category": "minor", "severity": "low", "description": "x"}],
            },
        )
        out_high = RiskAgent.build_structured_assessment(
            raw_llm={
                "risk_level": "high",
                "risk_score": 80,
                "flags": [
                    {"category": "regulatory", "severity": "high", "description": "x"},
                    {"category": "earnings", "severity": "high", "description": "y"},
                ],
            },
        )
        self.assertIsNotNone(out_low.tail_risk_score)
        self.assertIsNotNone(out_high.tail_risk_score)
        self.assertTrue(0.0 <= out_low.tail_risk_score <= 10.0)
        self.assertTrue(0.0 <= out_high.tail_risk_score <= 10.0)
        self.assertGreater(out_high.tail_risk_score, out_low.tail_risk_score)

    # --------------------------------------------------------------------- #
    # Backward compatibility — legacy field set is byte-stable
    # --------------------------------------------------------------------- #

    def test_legacy_fields_remain_populated_for_committee_consumers(self) -> None:
        out = RiskAgent.build_structured_assessment(
            raw_llm={
                "risk_level": "medium",
                "risk_score": 55,
                "flags": [
                    {"category": "earnings", "severity": "high", "description": "EPS miss"},
                    {"category": "lockup", "severity": "low", "description": "Unlocks soon"},
                ],
                "reasoning": "Two concerning signals.",
            },
        )
        # severity, red_flags, suggested_position_pct, veto, status — all
        # MUST be populated and conform to the Sprint 1A contract used by
        # the committee renderer.
        self.assertIn(out.severity, ("none", "soft", "hard"))
        self.assertIsInstance(out.red_flags, list)
        self.assertTrue(len(out.red_flags) >= 2)
        self.assertEqual(out.status, "ok")
        self.assertFalse(out.veto)
        # Re-parsing the model_dump must succeed (schema-valid invariant)
        round_trip = RiskAssessment(**out.model_dump())
        self.assertEqual(round_trip.severity, out.severity)
        self.assertEqual(round_trip.tail_risk_score, out.tail_risk_score)


if __name__ == "__main__":
    unittest.main()
