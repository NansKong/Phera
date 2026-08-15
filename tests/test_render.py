"""
Tests for the report renderer module.
Tests template rendering, fallback rendering, and case index generation.
"""

import pytest

from src.render import render_report, _fallback_render


class TestRenderReport:
    """Test report rendering with mock data."""

    @pytest.fixture
    def mock_sections(self):
        return [
            {
                "section_id": "reporting_period",
                "title": "Reporting Period",
                "mode": "llm",
                "content": "This report covers Bisoprolol for the period 2024-12-27 to 2025-12-26.",
                "status": "generated",
            },
            {
                "section_id": "case_index",
                "title": "Case Index/Listing",
                "mode": "deterministic",
                "content": "| Case ID | Reaction |\n|---------|----------|\n| 12345 | Coma |",
                "status": "generated",
            },
        ]

    @pytest.fixture
    def mock_analysis(self):
        return {
            "product_name": "Bisoprolol",
            "reporting_period_start": "2024-12-27",
            "reporting_period_end": "2025-12-26",
            "total_cases": 1024,
            "counting_note": "Case-level counts.",
        }

    @pytest.fixture
    def mock_config(self):
        return {
            "report_type": "pader",
            "display_name": "PADER Report",
            "generation": {"model": "openai/gpt-5-nano"},
        }

    def test_fallback_render_includes_all_sections(self, mock_sections, mock_analysis, mock_config):
        context = {
            "report_type": "PADER Report",
            "product_name": "Bisoprolol",
            "reporting_period_start": "2024-12-27",
            "reporting_period_end": "2025-12-26",
            "total_cases": 1024,
            "generated_date": "2025-01-01",
            "model": "openai/gpt-5-nano",
            "counting_note": "Case-level counts.",
        }
        result = _fallback_render(mock_sections, context)

        assert "Bisoprolol" in result
        assert "Reporting Period" in result
        assert "Case Index" in result
        assert "2024-12-27" in result

    def test_render_report_produces_output(self, mock_sections, mock_analysis, mock_config):
        result = render_report(mock_sections, mock_analysis, mock_config)
        assert len(result) > 0
        assert "Bisoprolol" in result

    def test_render_report_includes_flagged_sections_with_callout(self, mock_sections, mock_analysis, mock_config):
        reviews = [
            {"section_id": "reporting_period", "status": "flagged", "notes": "Needs work"},
            {"section_id": "case_index", "status": "approved", "notes": None},
        ]
        result = render_report(mock_sections, mock_analysis, mock_config, reviews)
        # Flagged section should be included with REVIEW REQUIRED marker
        assert "REVIEW REQUIRED - FLAGGED" in result
        assert "Needs work" in result
        assert "Case Index" in result
