"""
Phera — Context Builder Module

Assembles scoped evidence packets for each section based on the
section's configured evidence keys. Each section receives ONLY its
declared evidence — never the raw DataFrame or other sections' data.

This is the critical boundary that makes the V1 configurable
instructions architecture work.
"""

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Base directory for configuration files
CONFIG_DIR = Path(__file__).parent / "config"


def load_report_config(report_type: str) -> dict[str, Any]:
    """
    Load a report type configuration from YAML.

    Args:
        report_type: Report type identifier (e.g., 'pader')

    Returns:
        Parsed YAML configuration dictionary.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
    """
    config_path = CONFIG_DIR / "report_types" / f"{report_type}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Report configuration not found: {config_path}\n"
            f"Available configs: {list((CONFIG_DIR / 'report_types').glob('*.yaml'))}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logger.info(
        "Loaded report config: %s v%s (%d sections)",
        config.get("report_type"),
        config.get("version"),
        len(config.get("sections", [])),
    )

    return config


def load_system_prompt() -> str:
    """Load the shared system prompt from the prompts directory."""
    prompt_path = CONFIG_DIR / "prompts" / "system_base.md"

    if not prompt_path.exists():
        raise FileNotFoundError(f"System prompt not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8").strip()


def load_instruction(instruction_file: str) -> str:
    """
    Load a section-specific instruction from the prompts directory.

    Args:
        instruction_file: Relative path from the config directory
                         (e.g., 'prompts/narrative_summary.md')

    Returns:
        Instruction text content.
    """
    instruction_path = CONFIG_DIR / instruction_file

    if not instruction_path.exists():
        raise FileNotFoundError(
            f"Instruction file not found: {instruction_path}"
        )

    return instruction_path.read_text(encoding="utf-8").strip()


def build_section_context(
    section_config: dict[str, Any],
    analysis_results: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a scoped evidence packet for a single section.

    Only includes keys that are declared in the section's 'evidence' list.
    Raises KeyError if a declared key is missing from analysis results.

    Args:
        section_config: Section configuration from pader.yaml
        analysis_results: Full analysis results dictionary

    Returns:
        Scoped evidence packet containing only declared keys.

    Raises:
        KeyError: If a required evidence key is missing from analysis results.
    """
    evidence_keys = section_config.get("evidence", [])
    packet: dict[str, Any] = {}

    for key in evidence_keys:
        if key not in analysis_results:
            raise KeyError(
                f"Missing analysis key '{key}' required by section "
                f"'{section_config.get('id', 'unknown')}'. "
                f"Available keys: {sorted(analysis_results.keys())}"
            )
        packet[key] = analysis_results[key]

    logger.debug(
        "Built context for section '%s': %d keys",
        section_config.get("id"),
        len(packet),
    )

    return packet


def build_prompt(
    report_type: str,
    section_config: dict[str, Any],
    evidence: dict[str, Any],
    instruction: str,
) -> str:
    """
    Assemble the final prompt for LLM generation.

    Combines report type, section title, JSON evidence, and
    section-specific instructions into a single prompt string.

    Args:
        report_type: Report type identifier (e.g., 'pader')
        section_config: Section configuration dictionary
        evidence: Scoped evidence packet
        instruction: Section-specific instruction text

    Returns:
        Assembled prompt string.
    """
    prompt = f"""Report type: {report_type}

Section: {section_config["title"]}

Approved analysis results:
{json.dumps(evidence, indent=2, ensure_ascii=False, default=str)}

Instructions:
{instruction}

Write only the requested section.
Use only the supplied evidence."""

    return prompt
