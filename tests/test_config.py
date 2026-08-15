"""
Tests for the configuration system — the V1 core feature.
Validates that YAML configs load correctly, section IDs are unique,
and all referenced instruction files exist.
"""

import pytest
from pathlib import Path

from src.context_builder import load_report_config, load_system_prompt, load_instruction

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config"


class TestConfigLoads:
    """Test that the PADER configuration loads correctly."""

    def test_pader_config_loads(self):
        config = load_report_config("pader")
        assert config is not None
        assert config["report_type"] == "pader"
        assert config["version"] == "1.0"

    def test_config_has_generation_settings(self):
        config = load_report_config("pader")
        gen = config["generation"]
        assert gen["provider"] == "replicate"
        assert gen["model"] == "openai/gpt-5.6-luna"
        assert "max_completion_tokens" in gen

    def test_config_has_sections(self):
        config = load_report_config("pader")
        assert "sections" in config
        assert len(config["sections"]) == 9  # 7 LLM + 2 deterministic

    def test_invalid_report_type_raises(self):
        with pytest.raises(FileNotFoundError):
            load_report_config("nonexistent_report_type")


class TestSectionIdsUnique:
    """Test that all section IDs in the config are unique."""

    def test_section_ids_unique(self):
        config = load_report_config("pader")
        ids = [s["id"] for s in config["sections"]]
        assert len(ids) == len(set(ids)), f"Duplicate section IDs: {ids}"

    def test_all_sections_have_required_fields(self):
        config = load_report_config("pader")
        for section in config["sections"]:
            assert "id" in section, f"Section missing 'id': {section}"
            assert "title" in section, f"Section missing 'title': {section}"
            assert "mode" in section, f"Section missing 'mode': {section}"


class TestInstructionFilesExist:
    """Test that all referenced instruction files exist."""

    def test_system_prompt_exists(self):
        prompt = load_system_prompt()
        assert len(prompt) > 0

    def test_all_instruction_files_exist(self):
        config = load_report_config("pader")
        for section in config["sections"]:
            if section["mode"] == "llm":
                assert "instruction_file" in section, (
                    f"LLM section '{section['id']}' missing instruction_file"
                )
                instruction = load_instruction(section["instruction_file"])
                assert len(instruction) > 0, (
                    f"Empty instruction for section '{section['id']}'"
                )

    def test_llm_sections_have_evidence(self):
        config = load_report_config("pader")
        for section in config["sections"]:
            if section["mode"] == "llm":
                assert "evidence" in section, (
                    f"LLM section '{section['id']}' missing evidence keys"
                )
                assert len(section["evidence"]) > 0, (
                    f"Empty evidence list for section '{section['id']}'"
                )

    def test_deterministic_section_has_no_instruction(self):
        config = load_report_config("pader")
        for section in config["sections"]:
            if section["mode"] == "deterministic":
                assert "instruction_file" not in section or section.get("instruction_file") is None, (
                    f"Deterministic section '{section['id']}' should not have instruction_file"
                )
