"""
Phera — LLM Generation Module

Wraps the Replicate API with the openai/gpt-5.6-luna model for
section-by-section regulatory prose generation.

The generator ONLY phrases precomputed evidence — it never calculates.
All provider-specific logic is isolated here.
"""

import logging
import os
from typing import Any

import replicate

from .context_builder import (
    build_prompt,
    build_section_context,
    load_instruction,
    load_system_prompt,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-5.6-luna"


class ReplicateGenerator:
    """
    LLM generator using Replicate's API.

    Wraps the openai/gpt-5.6-luna model with appropriate settings
    for constrained regulatory prose generation.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        """
        Initialize the generator.

        Args:
            model: Replicate model identifier.

        Raises:
            EnvironmentError: If REPLICATE_API_TOKEN is not set.
        """
        self.model = model

        if not os.environ.get("REPLICATE_API_TOKEN"):
            raise EnvironmentError(
                "REPLICATE_API_TOKEN environment variable is not set. "
                "Copy .env.example to .env and add your token."
            )

        logger.info("Initialized ReplicateGenerator with model: %s", self.model)

    def generate(
        self,
        system_prompt: str,
        prompt: str,
        *,
        max_completion_tokens: int = 1200,
        reasoning_effort: str = "low",
        verbosity: str = "low",
    ) -> str:
        """
        Generate text using the Replicate model.

        Uses prompt + system_prompt pattern (not messages) as recommended
        for simple single-turn section generation.

        Args:
            system_prompt: Shared grounding rules.
            prompt: Section-specific prompt with evidence.
            max_completion_tokens: Maximum tokens in response.
            reasoning_effort: Model reasoning effort level.
            verbosity: Model verbosity level.

        Returns:
            Generated text string.
        """
        logger.info(
            "Generating with %s (max_tokens=%d)",
            self.model,
            max_completion_tokens,
        )

        output = replicate.run(
            self.model,
            input={
                "prompt": prompt,
                "system_prompt": system_prompt,
                "reasoning_effort": reasoning_effort,
                "verbosity": verbosity,
                "max_completion_tokens": max_completion_tokens,
            },
        )

        # Normalize output: Replicate returns string[] for this model
        if isinstance(output, list):
            result = "".join(str(item) for item in output).strip()
        else:
            result = str(output).strip()

        if not result:
            logger.warning("Empty generation received from model")

        logger.info("Generated %d characters", len(result))
        return result


def render_deterministic_section(
    section_config: dict[str, Any],
    analysis_results: dict[str, Any],
) -> str:
    """
    Render a deterministic section (no LLM call).
    Handles Case Index and Summary Tabulation.

    Args:
        section_config: Section configuration from YAML.
        analysis_results: Full analysis results.

    Returns:
        Rendered section content as a Markdown string.
    """
    section_id = section_config["id"]

    if section_id == "case_index":
        return _render_case_index(analysis_results)

    if section_id == "summary_tabulation":
        return _render_summary_tabulation(analysis_results)

    raise ValueError(f"Unknown deterministic section: {section_id}")


def _render_summary_tabulation(analysis_results: dict[str, Any]) -> str:
    """
    Render the Summary Tabulation of Adverse Events as a Markdown table.
    Lists reactions (MedDRA Preferred Terms) with serious/non-serious counts.
    Generated directly from structured data -- no LLM involved.

    Uses actual per-PT serious and non-serious counts from the analysis
    engine rather than ratio approximation. This ensures exact agreement
    with the evidence packet used by LLM sections.
    """
    reaction_breakdown = analysis_results.get("reaction_breakdown", {})

    if not reaction_breakdown:
        return "*No adverse event data available for tabulation.*"

    serious_reaction_breakdown = analysis_results.get("serious_reaction_breakdown", {})
    non_serious_reaction_breakdown = analysis_results.get("non_serious_reaction_breakdown", {})

    lines = [
        "Summary Tabulation of Adverse Drug Reactions from Postmarketing Sources",
        "",
        "Adverse reactions are presented by MedDRA Preferred Term. System Organ Class "
        "(SOC) grouping is not available in the supplied dataset. Counts represent "
        "case-level reaction frequencies during the current reporting interval "
        "(each Preferred Term counted once per case); "
        "a single case may contribute multiple reactions.",
        "",
        "| Preferred Term | Serious (Interval) | Non-Serious (Interval) | Total |",
        "|---|---:|---:|---:|",
    ]

    grand_serious = 0
    grand_non_serious = 0
    grand_total = 0

    for pt, count in reaction_breakdown.items():
        s_count = serious_reaction_breakdown.get(pt, 0)
        ns_count = non_serious_reaction_breakdown.get(pt, 0)

        # Warn if the sum doesn't match (indicates a dedup inconsistency)
        if s_count + ns_count != count:
            logger.warning(
                "Tabulation mismatch for '%s': serious(%d) + non_serious(%d) = %d, expected %d",
                pt, s_count, ns_count, s_count + ns_count, count,
            )

        grand_serious += s_count
        grand_non_serious += ns_count
        grand_total += count

        lines.append(f"| {pt} | {s_count} | {ns_count} | {count} |")

    lines.append(f"| **Total** | **{grand_serious}** | **{grand_non_serious}** | **{grand_total}** |")
    lines.append("")
    lines.append(
        "*Source: Spontaneous postmarketing surveillance. Interval = current "
        "reporting period only. Serious cases: events meeting ICH E2A seriousness criteria.*"
    )

    return "\n".join(lines)


def _render_case_index(analysis_results: dict[str, Any]) -> str:
    """
    Render the Case Index/Listing as a Markdown table.
    Generated directly from structured data -- no LLM involved.

    Reactions and outcomes are shown as semicolon-separated values
    for readability instead of raw comma-packed format.
    """
    case_index = analysis_results.get("case_index", [])

    if not case_index:
        return "*No cases available for listing.*"

    lines = [
        "| Case ID | Reaction(s) | Serious | Report Date | Country | Outcome(s) |",
        "|---------|-------------|---------|-------------|---------|------------|",
    ]

    for case in case_index:
        # Clean up comma-packed values for readability
        reactions = case.get("reaction", "")
        outcomes = case.get("outcome", "")

        # Replace commas with semicolons for table readability
        if reactions:
            reactions = reactions.replace(",", "; ")
        if outcomes:
            outcomes = outcomes.replace(",", "; ")

        # Truncate very long fields for table display
        if len(reactions) > 120:
            reaction_parts = reactions.split("; ")
            reactions = "; ".join(reaction_parts[:5]) + f" (+{len(reaction_parts) - 5} more)"
        if len(outcomes) > 80:
            outcome_parts = outcomes.split("; ")
            outcomes = "; ".join(outcome_parts[:3]) + f" (+{len(outcome_parts) - 3} more)"

        lines.append(
            f"| {case['case_id']} "
            f"| {reactions} "
            f"| {case['serious']} "
            f"| {case['report_date']} "
            f"| {case['country']} "
            f"| {outcomes} |"
        )

    return "\n".join(lines)


def generate_report_sections(
    config: dict[str, Any],
    analysis_results: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Generate all report sections according to the configuration.

    Routes each section to either LLM generation or deterministic
    rendering based on the section's mode.

    Args:
        config: Full report configuration (from pader.yaml).
        analysis_results: Full analysis results dictionary.

    Returns:
        List of generated section dictionaries with:
        - section_id
        - title
        - mode
        - content
        - evidence_keys (for LLM sections)
        - model (for LLM sections)
        - status
    """
    generation_config = config.get("generation", {})
    model = generation_config.get("model", DEFAULT_MODEL)
    max_tokens = generation_config.get("max_completion_tokens", 1200)
    reasoning = generation_config.get("reasoning_effort", "minimal")
    verb = generation_config.get("verbosity", "low")

    generator = ReplicateGenerator(model=model)
    system_prompt = load_system_prompt()

    generated: list[dict[str, Any]] = []

    for section in config.get("sections", []):
        section_id = section["id"]
        title = section["title"]
        mode = section.get("mode", "llm")

        logger.info("Processing section: %s (mode=%s)", section_id, mode)

        if mode == "deterministic":
            content = render_deterministic_section(section, analysis_results)
            generated.append({
                "section_id": section_id,
                "title": title,
                "mode": mode,
                "content": content,
                "status": "generated",
            })
        else:
            # LLM generation
            try:
                evidence = build_section_context(section, analysis_results)
                instruction = load_instruction(section["instruction_file"])

                prompt = build_prompt(
                    config["report_type"],
                    section,
                    evidence,
                    instruction,
                )

                content = generator.generate(
                    system_prompt=system_prompt,
                    prompt=prompt,
                    max_completion_tokens=max_tokens,
                    reasoning_effort=reasoning,
                    verbosity=verb,
                )

                generated.append({
                    "section_id": section_id,
                    "title": title,
                    "mode": mode,
                    "content": content,
                    "evidence_keys": section.get("evidence", []),
                    "model": model,
                    "status": "generated" if content else "empty",
                })

            except Exception as e:
                logger.error("Generation failed for section '%s': %s", section_id, e)
                generated.append({
                    "section_id": section_id,
                    "title": title,
                    "mode": mode,
                    "content": "",
                    "error": str(e),
                    "status": "failed",
                })

    return generated
