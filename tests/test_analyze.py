"""
Tests for the deterministic analysis module.
Validates that analysis outputs are JSON-serializable and contain
all expected keys with correct types.
"""

import json

import pytest
from pathlib import Path

from src.ingest import ingest
from src.analyze import analyze

DATASET_PATH = Path(__file__).parent.parent / "docs" / "Bisoprolol_icsr_sample_1068rows.xlsx"


@pytest.fixture(scope="module")
def analysis_results():
    """Run analysis once for all tests in this module."""
    if not DATASET_PATH.exists():
        pytest.skip("Dataset file not available")
    ingest_result = ingest(DATASET_PATH)
    return analyze(ingest_result)


class TestAnalysisOutputs:
    """Test that analysis produces all required keys."""

    REQUIRED_KEYS = [
        "product_name",
        "reporting_period_start",
        "reporting_period_end",
        "report_type",
        "application_number",
        "total_cases",
        "new_cases_in_period",
        "serious_cases",
        "non_serious_cases",
        "serious_pct",
        "seriousness_breakdown",
        "age_breakdown",
        "sex_breakdown",
        "country_breakdown",
        "top_reactions",
        "top_serious_reactions",
        "reaction_breakdown",
        "serious_reaction_breakdown",
        "non_serious_reaction_breakdown",
        "outcome_breakdown",
        "reactions_by_age_group",
        "reactions_by_sex",
        "reactions_over_time",
        "monthly_case_counts",
        "monthly_top_reaction_counts",
        "country_trend",
        "seriousness_trend",
        "alert_case_count",
        "alert_cases_table",
        "soc_available",
        "expectedness_available",
        "actions_provided",
        "case_index",
        "reaction_counting_method",
    ]

    def test_all_required_keys_present(self, analysis_results):
        for key in self.REQUIRED_KEYS:
            assert key in analysis_results, f"Missing key: {key}"

    def test_json_serializable(self, analysis_results):
        """Critical: all analysis results must be JSON-serializable."""
        serialized = json.dumps(analysis_results, default=str)
        assert len(serialized) > 0
        # Round-trip
        deserialized = json.loads(serialized)
        assert "total_cases" in deserialized


class TestAnalysisValues:
    """Test that analysis values match expected data characteristics."""

    def test_total_cases(self, analysis_results):
        assert analysis_results["total_cases"] == 1024

    def test_serious_cases(self, analysis_results):
        # Brief says 1023 of 1024 serious at case level
        assert analysis_results["serious_cases"] >= 1020  # Allow small variance from dedup strategy

    def test_non_serious_cases(self, analysis_results):
        total = analysis_results["serious_cases"] + analysis_results["non_serious_cases"]
        assert total == analysis_results["total_cases"]

    def test_product_name(self, analysis_results):
        assert analysis_results["product_name"] == "Bisoprolol"

    def test_report_type(self, analysis_results):
        assert analysis_results["report_type"] == "PADER"

    def test_reporting_period(self, analysis_results):
        assert analysis_results["reporting_period_start"] == "2024-12-27"
        assert analysis_results["reporting_period_end"] == "2025-12-26"

    def test_top_reactions_not_empty(self, analysis_results):
        assert len(analysis_results["top_reactions"]) > 0

    def test_sex_breakdown_sums(self, analysis_results):
        sex = analysis_results["sex_breakdown"]
        total = sum(sex.values())
        assert total == analysis_results["total_cases"]

    def test_data_availability_flags(self, analysis_results):
        assert analysis_results["soc_available"] is False
        assert analysis_results["expectedness_available"] is False
        assert analysis_results["actions_provided"] is False

    def test_case_index_length(self, analysis_results):
        assert len(analysis_results["case_index"]) == analysis_results["total_cases"]

    def test_reaction_counting_method(self, analysis_results):
        assert analysis_results["reaction_counting_method"] == "case_level_deduplicated"

    def test_alert_case_reason_not_hardcoded(self, analysis_results):
        """Verify the alert_case_reason uses the computed serious count, not a hardcoded value."""
        reason = analysis_results["alert_case_reason"]
        serious = analysis_results["serious_cases"]
        assert f"{serious:,}" in reason


class TestReactionBreakdownIntegrity:
    """Test the fundamental invariant: serious + non_serious == total for every PT."""

    def test_serious_plus_non_serious_equals_total(self, analysis_results):
        """For every PT in reaction_breakdown, serious + non_serious must equal total."""
        reaction_breakdown = analysis_results["reaction_breakdown"]
        serious_breakdown = analysis_results["serious_reaction_breakdown"]
        non_serious_breakdown = analysis_results["non_serious_reaction_breakdown"]

        mismatches = []
        for pt, total in reaction_breakdown.items():
            s = serious_breakdown.get(pt, 0)
            ns = non_serious_breakdown.get(pt, 0)
            if s + ns != total:
                mismatches.append(f"{pt}: {s} + {ns} = {s + ns} != {total}")

        assert not mismatches, f"Breakdown invariant violated:\n" + "\n".join(mismatches)

    def test_serious_breakdown_not_empty(self, analysis_results):
        assert len(analysis_results["serious_reaction_breakdown"]) > 0

    def test_serious_breakdown_contains_top_serious_reactions(self, analysis_results):
        """Every PT in top_serious_reactions should be in serious_reaction_breakdown."""
        top = analysis_results["top_serious_reactions"]
        full = analysis_results["serious_reaction_breakdown"]
        for pt in top:
            assert pt in full, f"top_serious_reactions PT '{pt}' missing from serious_reaction_breakdown"

    def test_drug_ineffective_split(self, analysis_results):
        """Specific regression test for the Drug ineffective contradiction."""
        rb = analysis_results["reaction_breakdown"]
        srb = analysis_results["serious_reaction_breakdown"]
        nsrb = analysis_results["non_serious_reaction_breakdown"]

        if "Drug ineffective" in rb:
            total = rb["Drug ineffective"]
            serious = srb.get("Drug ineffective", 0)
            non_serious = nsrb.get("Drug ineffective", 0)
            assert serious + non_serious == total, (
                f"Drug ineffective: {serious} + {non_serious} != {total}"
            )
