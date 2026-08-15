"""
Tests for the context builder — the critical V1 configurable instructions boundary.

The most important test here is test_context_contains_only_declared_keys,
which verifies that each section receives ONLY its configured evidence.
"""

import pytest
from pathlib import Path

from src.context_builder import (
    build_prompt,
    build_section_context,
    load_report_config,
)
from src.ingest import ingest
from src.analyze import analyze

DATASET_PATH = Path(__file__).parent.parent / "docs" / "Bisoprolol_icsr_sample_1068rows.xlsx"


@pytest.fixture(scope="module")
def analysis_results():
    if not DATASET_PATH.exists():
        pytest.skip("Dataset file not available")
    ingest_result = ingest(DATASET_PATH)
    return analyze(ingest_result)


@pytest.fixture(scope="module")
def config():
    return load_report_config("pader")


class TestContextContainsOnlyDeclaredKeys:
    """
    THE critical V1 test.

    Verifies that build_section_context returns ONLY the keys
    declared in the section's evidence configuration — no raw
    DataFrame, no other sections' data, nothing extra.
    """

    def test_context_contains_only_declared_keys(self, config, analysis_results):
        """Every section's context must contain exactly its declared keys."""
        for section in config["sections"]:
            if section["mode"] == "deterministic":
                continue  # Skip deterministic sections (no evidence)

            declared_keys = set(section["evidence"])
            context = build_section_context(section, analysis_results)
            context_keys = set(context.keys())

            assert context_keys == declared_keys, (
                f"Section '{section['id']}' context mismatch.\n"
                f"  Declared: {sorted(declared_keys)}\n"
                f"  Got:      {sorted(context_keys)}\n"
                f"  Extra:    {sorted(context_keys - declared_keys)}\n"
                f"  Missing:  {sorted(declared_keys - context_keys)}"
            )


class TestMissingEvidenceKeyFails:
    """Test that missing evidence keys raise KeyError."""

    def test_missing_key_raises(self, analysis_results):
        section_config = {
            "id": "test",
            "evidence": ["nonexistent_key"],
        }
        with pytest.raises(KeyError):
            build_section_context(section_config, analysis_results)

    def test_empty_evidence_returns_empty(self, analysis_results):
        section_config = {
            "id": "test",
            "evidence": [],
        }
        context = build_section_context(section_config, analysis_results)
        assert context == {}


class TestAllEvidenceKeysExist:
    """Test that all evidence keys declared in config exist in analysis results."""

    def test_all_evidence_keys_in_analysis(self, config, analysis_results):
        for section in config["sections"]:
            if section["mode"] == "deterministic":
                continue

            for key in section["evidence"]:
                assert key in analysis_results, (
                    f"Section '{section['id']}' declares evidence key '{key}' "
                    f"which is not in analysis results"
                )


class TestBuildPrompt:
    """Test prompt assembly."""

    def test_prompt_contains_section_title(self, config, analysis_results):
        section = config["sections"][0]  # reporting_period
        evidence = build_section_context(section, analysis_results)
        prompt = build_prompt("pader", section, evidence, "Test instruction")

        assert "pader" in prompt.lower()
        assert section["title"] in prompt
        assert "Test instruction" in prompt

    def test_prompt_contains_evidence(self, config, analysis_results):
        section = config["sections"][0]
        evidence = build_section_context(section, analysis_results)
        prompt = build_prompt("pader", section, evidence, "Test instruction")

        assert "Bisoprolol" in prompt
        assert "Approved analysis results" in prompt
