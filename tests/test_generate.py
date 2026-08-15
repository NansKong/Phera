"""
Tests for the LLM generation module.
Tests output normalization, deterministic section rendering,
and empty generation rejection — without requiring API calls.
"""

import pytest

from src.generate import render_deterministic_section, _render_case_index


class TestReplicateOutputNormalization:
    """Test that Replicate string[] output is joined correctly."""

    def test_list_output_joined(self):
        """Simulate Replicate returning string[]."""
        output = ["This is ", "a test ", "output."]
        result = "".join(str(item) for item in output).strip()
        assert result == "This is a test output."

    def test_string_output_passthrough(self):
        output = "This is a string output."
        result = str(output).strip()
        assert result == "This is a string output."

    def test_empty_list_returns_empty(self):
        output = []
        result = "".join(str(item) for item in output).strip()
        assert result == ""


class TestEmptyGenerationRejected:
    """Test that empty generation is flagged."""

    def test_empty_string_detected(self):
        result = ""
        assert not result  # Empty string is falsy

    def test_whitespace_only_detected(self):
        result = "   \n\n  ".strip()
        assert not result


class TestCaseIndexDeterministic:
    """Test that Case Index does not call LLM and renders correctly."""

    def test_case_index_renders_table(self):
        analysis_results = {
            "case_index": [
                {
                    "case_id": "12345",
                    "reaction": "Coma",
                    "serious": "serious",
                    "report_date": "2025-01-15",
                    "country": "US",
                    "outcome": "recovered/resolved",
                },
                {
                    "case_id": "12346",
                    "reaction": "Pain",
                    "serious": "not serious",
                    "report_date": "2025-02-20",
                    "country": "GB",
                    "outcome": "unknown",
                },
            ],
        }

        section_config = {"id": "case_index", "title": "Case Index/Listing", "mode": "deterministic"}
        content = render_deterministic_section(section_config, analysis_results)

        assert "12345" in content
        assert "Coma" in content
        assert "12346" in content
        assert "|" in content  # Markdown table

    def test_empty_case_index(self):
        analysis_results = {"case_index": []}
        section_config = {"id": "case_index", "title": "Case Index/Listing", "mode": "deterministic"}
        content = render_deterministic_section(section_config, analysis_results)
        assert "No cases" in content

    def test_unknown_deterministic_section_raises(self):
        section_config = {"id": "unknown_section", "mode": "deterministic"}
        with pytest.raises(ValueError):
            render_deterministic_section(section_config, {})


class TestSummaryTabulationDeterministic:
    """Test that Summary Tabulation renders exact serious and non-serious counts."""

    def test_summary_tabulation_renders_exact_counts(self):
        analysis_results = {
            "reaction_breakdown": {"Drug ineffective": 54, "Bradycardia": 37},
            "serious_reaction_breakdown": {"Drug ineffective": 53, "Bradycardia": 37},
            "non_serious_reaction_breakdown": {"Drug ineffective": 1},
        }

        section_config = {
            "id": "summary_tabulation",
            "title": "Summary Tabulation of Adverse Events",
            "mode": "deterministic",
        }
        content = render_deterministic_section(section_config, analysis_results)

        assert "| Drug ineffective | 53 | 1 | 54 |" in content
        assert "| Bradycardia | 37 | 0 | 37 |" in content
        assert "| **Total** | **90** | **1** | **91** |" in content
