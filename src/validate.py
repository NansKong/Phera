"""
Phera — Validation Module

Implements automated checks on generated sections:
1. Numeric consistency — numbers in generated text match the evidence packet
2. Unsupported claim detection — flags conclusion language without evidence
3. Counting level mismatch — reaction/outcome frequencies mislabeled as case-level
4. MedDRA term integrity — detect typos/splits in Preferred Terms
5. Dangling content — detect incomplete bullet points
6. Completeness — every required section was generated and non-empty
7. Cross-section consistency — verify agreement between independently generated
   sections (e.g., serious + non_serious == total for every PT)

These are screening mechanisms that prioritize human review,
not replacements for human review.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Language patterns that indicate unsupported safety conclusions
UNSUPPORTED_CLAIM_PATTERNS = [
    r"\bno\s+safety\s+concern",
    r"\bsafety\s+signal\b",
    r"\bsignal\b",
    r"\bconfirmed\b",
    r"\bcausal\b",
    r"\bcaused\s+by\b",
    r"\bcausally\s+related\b",
    r"\bno\s+concern\b",
    r"\bconcern\s+identified\b",
    r"\bno\s+risk\b",
    r"\bestablished\s+relationship\b",
]


def extract_numbers_from_text(text: str) -> list[str]:
    """
    Extract all numeric values from generated text.
    Handles integers, decimals, and percentages.

    Returns:
        List of number strings found in the text.
    """
    # Match numbers including percentages and decimals
    # but exclude things like dates (2024-12-27) and version numbers
    numbers = re.findall(r'\b(\d+(?:,\d{3})*(?:\.\d+)?%?)(?=\s|$|[^0-9%])', text)
    return numbers


def _normalize_number(num_str: str) -> str:
    """Strip thousands-separator commas from a number string for comparison.
    E.g. '1,024' -> '1024', '1,280' -> '1280', '99.9%' -> '99.9%'.
    """
    return num_str.replace(",", "")


# Numbers that appear in regulatory citations (e.g. "21 CFR 314.80")
# and are never present in the evidence packet.
REGULATORY_CITATION_NUMBERS = {"21", "314.80", "314", "80"}


def validate_numeric_consistency(
    section_content: str,
    evidence_packet: dict[str, Any],
) -> dict[str, Any]:
    """
    Check that numbers in the generated text appear in the evidence packet.

    Normalizes comma-formatted numbers (e.g. '1,024' matches '1024') and
    exempts well-known regulatory citation numbers (e.g. '21 CFR 314.80').

    Args:
        section_content: Generated text for a section.
        evidence_packet: The scoped evidence that was provided to the model.

    Returns:
        Validation result with:
        - status: 'pass' | 'warn' | 'fail'
        - found_numbers: numbers found in text
        - evidence_numbers: numbers found in evidence
        - unsupported_numbers: numbers in text but not in evidence
    """
    # Extract numbers from generated text
    text_numbers = set(extract_numbers_from_text(section_content))

    # Extract numbers from the evidence packet (flatten all values)
    evidence_str = _flatten_to_string(evidence_packet)
    evidence_numbers = set(extract_numbers_from_text(evidence_str))

    # Build a normalized evidence set (commas stripped) for comparison
    normalized_evidence = {_normalize_number(n) for n in evidence_numbers}

    # Find numbers in text whose normalized form doesn't appear in evidence
    unsupported = {
        n for n in text_numbers
        if _normalize_number(n) not in normalized_evidence
    }

    # Filter out trivial formatting numbers and regulatory citations
    trivial_numbers = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}
    exempt = trivial_numbers | REGULATORY_CITATION_NUMBERS
    significant_unsupported = unsupported - exempt

    if significant_unsupported:
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "found_numbers": sorted(text_numbers),
        "evidence_numbers": sorted(evidence_numbers),
        "unsupported_numbers": sorted(significant_unsupported),
    }


def validate_unsupported_claims(section_content: str) -> dict[str, Any]:
    """
    Check for conclusion language that is not supported by evidence.

    Flags terms like 'no safety concern', 'signal', 'confirmed', 'causal'
    unless the evidence explicitly establishes that framing.

    Args:
        section_content: Generated text for a section.

    Returns:
        Validation result with:
        - status: 'pass' | 'warn'
        - flagged_phrases: list of matched phrases
    """
    flagged = []
    content_lower = section_content.lower()

    for pattern in UNSUPPORTED_CLAIM_PATTERNS:
        matches = re.findall(pattern, content_lower)
        flagged.extend(matches)

    status = "warn" if flagged else "pass"

    return {
        "status": status,
        "flagged_phrases": flagged,
    }


def validate_counting_level_mismatch(
    section_content: str,
    evidence_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Semantic, config-driven validator for counting-level consistency.

    Understands valid terms when supported by counting definitions:
      - 'case-level frequency' / 'case-level reaction frequency'
      - 'counted once per case' / 'deduplicated within each case'
      - 'reaction occurrences'
      - 'outcome entries'

    Flags genuinely contradictory claims such as:
      - 'X cases experienced [reaction]' / 'X cases reported [reaction]'
        UNLESS X matches the verified case-level count for that reaction in evidence_packet
        AND reaction_counting_method is 'case_level_deduplicated'.
      - Mislabeling outcome distribution as '(case level)' when outcomes are multi-entry.
    """
    flagged = []
    content_lower = section_content.lower()

    counting_method = "case_level_deduplicated"
    verified_case_counts: dict[str, int] = {}

    if evidence_packet:
        counting_method = evidence_packet.get("reaction_counting_method", "case_level_deduplicated")
        for key in [
            "top_reactions",
            "top_serious_reactions",
            "reaction_breakdown",
            "serious_reaction_breakdown",
            "non_serious_reaction_breakdown",
        ]:
            breakdown = evidence_packet.get(key)
            if isinstance(breakdown, dict):
                for pt, count in breakdown.items():
                    if isinstance(count, (int, float)):
                        verified_case_counts[str(pt).lower()] = int(count)

    # Check 1: Claims like "X cases experienced/reported [reaction]" or "[reaction] was reported in X cases"
    patterns_cases_reaction = [
        r"(\d+)\s+cases\s+(?:experienced|reported|had|presented\s+with)\s+([a-z0-9\s\-/]+)",
        r"([a-z0-9\s\-/]+)\s+(?:was\s+|were\s+)?(?:experienced|reported|observed)\s+in\s+(\d+)\s+cases",
    ]

    for pat in patterns_cases_reaction:
        for match in re.finditer(pat, content_lower):
            if pat.startswith(r"(\d+)"):
                num_str, raw_pt = match.group(1), match.group(2).strip()
            else:
                raw_pt, num_str = match.group(1).strip(), match.group(2)

            try:
                num = int(num_str)
            except ValueError:
                continue

            raw_pt_clean = re.sub(r"[^\w\s\-/]", "", raw_pt).strip()

            matched_count = None
            for pt_name, count in verified_case_counts.items():
                pt_clean = re.sub(r"[^\w\s\-/]", "", pt_name).strip()
                if pt_clean in raw_pt_clean or raw_pt_clean in pt_clean:
                    matched_count = count
                    break

            if counting_method != "case_level_deduplicated":
                flagged.append(match.group(0))
            elif matched_count is not None and num != matched_count:
                flagged.append(match.group(0))
            elif matched_count is None and evidence_packet is not None and verified_case_counts:
                flagged.append(match.group(0))

    # Check 2: Mislabeling outcomes as case-level when they are multi-entry
    outcome_case_level_patterns = [
        r"outcomes?\s+\(case\s+level\)",
        r"outcome\s+distribution\s+\(case\s+level\)",
        r"outcomes\s+by\s+case\s+count",
    ]
    for pat in outcome_case_level_patterns:
        matches = re.findall(pat, content_lower)
        flagged.extend(matches)

    status = "warn" if flagged else "pass"
    return {
        "status": status,
        "flagged_phrases": flagged,
    }


def validate_meddra_term_integrity(section_content: str) -> dict[str, Any]:
    """
    Check for known typos or split words in MedDRA Preferred Terms.
    For example: 'bradi cardia', 'brdycardia', 'brardycardia', 'dys pnoea', meta notes like '[note:'.
    """
    flagged = []
    content_lower = section_content.lower()

    typo_patterns = [
        r"\bbradi\s+cardia\b",
        r"\bbrdycardia\b",
        r"\bbrardycardia\b",
        r"\bdys\s+pnoea\b",
        r"\bdiar\s+rhoea\b",
        r"\[note:",
    ]

    for pattern in typo_patterns:
        matches = re.findall(pattern, content_lower)
        flagged.extend(matches)

    status = "warn" if flagged else "pass"
    return {
        "status": status,
        "flagged_phrases": flagged,
    }


def validate_dangling_content(section_content: str) -> dict[str, Any]:
    """
    Check if section content ends with an incomplete/dangling bullet point or case ID.
    E.g. '- Case 25066459:' at the end of the text.
    """
    flagged = []
    trimmed = section_content.strip()

    # Pattern matching a trailing bullet point ending with a colon or empty details
    dangling_patterns = [
        r"-\s*case\s+\d+:\s*$",
        r"-\s*case\s+:\s*$",
        r"-\s*:\s*$",
    ]

    for pattern in dangling_patterns:
        if re.search(pattern, trimmed, re.IGNORECASE):
            flagged.append(trimmed.split("\n")[-1])

    status = "warn" if flagged else "pass"
    return {
        "status": status,
        "flagged_phrases": flagged,
    }


def validate_cross_section_consistency(
    analysis_results: dict[str, Any],
) -> dict[str, Any]:
    """
    Cross-section consistency check.

    Verifies that independently computed data layers agree with each other.
    Currently checks:
    - For every PT in reaction_breakdown:
        serious_count + non_serious_count == total_count
    - serious_count matches serious_reaction_breakdown[PT]

    This catches contradictions like:
      reaction_breakdown['Drug ineffective'] = 54
      serious_reaction_breakdown['Drug ineffective'] = 53
      → non_serious should be 1, not 0

    Args:
        analysis_results: Full analysis results dictionary.

    Returns:
        Validation result with:
        - status: 'pass' | 'fail'
        - mismatches: list of per-PT mismatch descriptions
    """
    reaction_breakdown = analysis_results.get("reaction_breakdown", {})
    serious_breakdown = analysis_results.get("serious_reaction_breakdown", {})
    non_serious_breakdown = analysis_results.get("non_serious_reaction_breakdown", {})

    mismatches: list[str] = []

    for pt, total in reaction_breakdown.items():
        s_count = serious_breakdown.get(pt, 0)
        ns_count = non_serious_breakdown.get(pt, 0)
        computed_total = s_count + ns_count

        if computed_total != total:
            mismatches.append(
                f"{pt}: serious({s_count}) + non_serious({ns_count}) = {computed_total}, "
                f"expected total = {total}"
            )

    status = "fail" if mismatches else "pass"

    return {
        "status": status,
        "mismatches": mismatches,
        "pts_checked": len(reaction_breakdown),
    }


def validate_completeness(
    generated_sections: list[dict[str, Any]],
    config_sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Verify that every required section was generated and is non-empty.

    Args:
        generated_sections: List of generated section results.
        config_sections: List of section configs from YAML.

    Returns:
        Validation result with:
        - status: 'pass' | 'fail'
        - missing_sections: section IDs not found in output
        - empty_sections: section IDs with empty content
        - failed_sections: section IDs that failed generation
    """
    expected_ids = {s["id"] for s in config_sections}
    generated_ids = {s["section_id"] for s in generated_sections}

    missing = expected_ids - generated_ids
    empty = [
        s["section_id"]
        for s in generated_sections
        if not s.get("content", "").strip()
    ]
    failed = [
        s["section_id"]
        for s in generated_sections
        if s.get("status") == "failed"
    ]

    issues = missing or empty or failed
    status = "fail" if issues else "pass"

    return {
        "status": status,
        "missing_sections": sorted(missing),
        "empty_sections": empty,
        "failed_sections": failed,
    }


def validate_section(
    section: dict[str, Any],
    evidence_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run all validation checks on a single generated section.

    Args:
        section: Generated section dictionary.
        evidence_packet: Scoped evidence packet (for numeric check).

    Returns:
        Combined validation result for this section.
    """
    content = section.get("content", "")
    section_id = section.get("section_id", "unknown")

    result: dict[str, Any] = {
        "section_id": section_id,
        "checks": {},
    }

    # Numeric consistency (only for LLM sections with evidence)
    if evidence_packet and section.get("mode") != "deterministic":
        result["checks"]["numeric_consistency"] = validate_numeric_consistency(
            content, evidence_packet
        )

    # Unsupported claims (only for LLM sections)
    if section.get("mode") != "deterministic":
        result["checks"]["unsupported_claims"] = validate_unsupported_claims(content)
        result["checks"]["counting_level_mismatch"] = validate_counting_level_mismatch(
            content, evidence_packet
        )
        result["checks"]["meddra_term_integrity"] = validate_meddra_term_integrity(content)
        result["checks"]["dangling_content"] = validate_dangling_content(content)

    # Determine overall status
    statuses = [check["status"] for check in result["checks"].values()]
    if "fail" in statuses:
        result["overall_status"] = "fail"
    elif "warn" in statuses:
        result["overall_status"] = "warn"
    else:
        result["overall_status"] = "pass"

    return result


def validate_all_sections(
    generated_sections: list[dict[str, Any]],
    config: dict[str, Any],
    analysis_results: dict[str, Any],
) -> dict[str, Any]:
    """
    Run all validation checks on all generated sections.

    Args:
        generated_sections: List of generated section results.
        config: Report configuration.
        analysis_results: Full analysis results.

    Returns:
        Full validation report.
    """
    from .context_builder import build_section_context

    section_validations = []
    config_sections = config.get("sections", [])

    # Create section config lookup
    section_configs = {s["id"]: s for s in config_sections}

    for section in generated_sections:
        section_id = section["section_id"]
        section_cfg = section_configs.get(section_id, {})

        # Build evidence packet for numeric check
        evidence_packet = None
        if section_cfg.get("evidence") and section.get("mode") != "deterministic":
            try:
                evidence_packet = build_section_context(section_cfg, analysis_results)
            except KeyError:
                logger.warning(
                    "Could not build evidence for validation of section '%s'",
                    section_id,
                )

        validation = validate_section(section, evidence_packet)
        section_validations.append(validation)

    # Completeness check
    completeness = validate_completeness(generated_sections, config_sections)

    # Cross-section consistency check
    cross_section = validate_cross_section_consistency(analysis_results)
    if cross_section["status"] != "pass":
        for mismatch in cross_section["mismatches"]:
            logger.error("Cross-section mismatch: %s", mismatch)

    # Overall report
    all_statuses = [v["overall_status"] for v in section_validations]
    all_statuses.append(completeness["status"])
    all_statuses.append(cross_section["status"])

    if "fail" in all_statuses:
        overall = "fail"
    elif "warn" in all_statuses:
        overall = "warn"
    else:
        overall = "pass"

    return {
        "overall_status": overall,
        "completeness": completeness,
        "cross_section_consistency": cross_section,
        "sections": section_validations,
    }


def _flatten_to_string(obj: Any, depth: int = 0) -> str:
    """Recursively flatten a nested object to a string for number extraction."""
    if depth > 10:
        return str(obj)

    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            parts.append(str(k))
            parts.append(_flatten_to_string(v, depth + 1))
        return " ".join(parts)
    elif isinstance(obj, (list, tuple)):
        return " ".join(_flatten_to_string(item, depth + 1) for item in obj)
    else:
        return str(obj)
