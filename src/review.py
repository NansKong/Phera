"""
Phera — Human Review Module

Provides CLI-based human review checkpoints:
- Checkpoint A: Review and approve/flag analysis results
- Checkpoint B: Review and approve/flag each generated section

A successful API call does not make a section final —
human approval is required.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Review actions
ACTION_APPROVE = "approve"
ACTION_FLAG = "flag"
ACTION_REGENERATE = "regenerate"


def _display_separator() -> None:
    """Print a visual separator."""
    print("\n" + "=" * 72)


def _display_json_summary(data: dict[str, Any], max_depth: int = 2) -> None:
    """Pretty-print a JSON-like summary of analysis data."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:3000])
    if len(json.dumps(data, default=str)) > 3000:
        print("... (truncated for display)")


def review_analysis_results(analysis_results: dict[str, Any]) -> dict[str, Any]:
    """
    Checkpoint A: Human review of deterministic analysis results.

    Displays key analysis figures and prompts the reviewer to
    approve or flag the results before they become approved evidence.

    Args:
        analysis_results: Dictionary from analyze().

    Returns:
        Review result with:
        - status: 'approved' | 'flagged'
        - notes: Optional reviewer notes
    """
    _display_separator()
    print("CHECKPOINT A — Analysis Results Review")
    _display_separator()

    # Show key summary figures
    summary = {
        "product_name": analysis_results.get("product_name"),
        "reporting_period": f"{analysis_results.get('reporting_period_start')} to {analysis_results.get('reporting_period_end')}",
        "total_cases": analysis_results.get("total_cases"),
        "serious_cases": analysis_results.get("serious_cases"),
        "non_serious_cases": analysis_results.get("non_serious_cases"),
        "serious_pct": analysis_results.get("serious_pct"),
        "sex_breakdown": analysis_results.get("sex_breakdown"),
        "age_breakdown": analysis_results.get("age_breakdown"),
        "top_5_reactions": dict(list(analysis_results.get("top_reactions", {}).items())[:5]),
        "alert_case_count": analysis_results.get("alert_case_count"),
        "counting_note": analysis_results.get("counting_note"),
    }

    print("\nKey Analysis Figures:")
    _display_json_summary(summary)

    print("\n[1] Approve analysis results")
    print("[2] Flag analysis results (add notes)")

    while True:
        choice = input("\nAction (1/2): ").strip()

        if choice == "1":
            logger.info("Analysis results APPROVED by reviewer")
            return {"status": "approved", "notes": None}
        elif choice == "2":
            notes = input("Reviewer notes: ").strip()
            logger.info("Analysis results FLAGGED by reviewer: %s", notes)
            return {"status": "flagged", "notes": notes}
        else:
            print("Invalid choice. Enter 1 or 2.")


def review_generated_section(section: dict[str, Any]) -> dict[str, Any]:
    """
    Checkpoint B: Human review of a single generated section.

    Displays the section content and validation results, then prompts
    the reviewer to approve, flag, or request regeneration.

    Args:
        section: Generated section dictionary.

    Returns:
        Review result with:
        - status: 'approved' | 'flagged' | 'regenerate'
        - notes: Optional reviewer notes
    """
    _display_separator()
    print(f"CHECKPOINT B — Section Review: {section.get('title', 'Unknown')}")
    print(f"Section ID: {section.get('section_id', 'unknown')}")
    print(f"Mode: {section.get('mode', 'unknown')}")
    print(f"Generation Status: {section.get('status', 'unknown')}")
    _display_separator()

    content = section.get("content", "")
    if content:
        print("\nGenerated Content:")
        print("-" * 40)
        print(content)
        print("-" * 40)
    else:
        print("\n[WARNING] No content generated for this section.")

    # Show validation results if available
    validation = section.get("validation")
    if validation:
        print(f"\nValidation: {validation.get('overall_status', 'unknown').upper()}")
        for check_name, check_result in validation.get("checks", {}).items():
            status = check_result.get("status", "unknown")
            icon = "[OK]" if status == "pass" else "[!]"
            print(f"  {icon} {check_name}: {status}")
            if check_result.get("unsupported_numbers"):
                print(f"    Numbers not in evidence: {check_result['unsupported_numbers']}")
            if check_result.get("flagged_phrases"):
                print(f"    Flagged phrases: {check_result['flagged_phrases']}")

    print("\n[1] Approve section")
    print("[2] Flag section (add notes)")
    print("[3] Regenerate section")

    while True:
        choice = input("\nAction (1/2/3): ").strip()

        if choice == "1":
            logger.info("Section '%s' APPROVED", section.get("section_id"))
            return {"status": "approved", "notes": None}
        elif choice == "2":
            notes = input("Reviewer notes: ").strip()
            logger.info("Section '%s' FLAGGED: %s", section.get("section_id"), notes)
            return {"status": "flagged", "notes": notes}
        elif choice == "3":
            notes = input("Regeneration notes (optional): ").strip() or None
            logger.info("Section '%s' marked for REGENERATION", section.get("section_id"))
            return {"status": "regenerate", "notes": notes}
        else:
            print("Invalid choice. Enter 1, 2, or 3.")


def review_all_sections(
    generated_sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Run Checkpoint B on all generated sections.

    Args:
        generated_sections: List of generated section dictionaries.

    Returns:
        List of review results, one per section.
    """
    reviews = []

    print(f"\n{'='*72}")
    print(f"CHECKPOINT B — Reviewing {len(generated_sections)} generated sections")
    print(f"{'='*72}")

    for section in generated_sections:
        review = review_generated_section(section)
        review["section_id"] = section.get("section_id")
        reviews.append(review)

    # Summary
    approved = sum(1 for r in reviews if r["status"] == "approved")
    flagged = sum(1 for r in reviews if r["status"] == "flagged")
    regen = sum(1 for r in reviews if r["status"] == "regenerate")

    print(f"\nReview Summary: {approved} approved, {flagged} flagged, {regen} for regeneration")

    return reviews
