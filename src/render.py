"""
Phera — Report Renderer Module

Renders approved sections into a final PADER report using
Jinja2 templates. Supports Markdown output (HTML/PDF can be
added as extensions).

The Case Index is rendered deterministically — no LLM involved.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

# Template directory
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def create_jinja_env(template_dir: Path | None = None) -> Environment:
    """Create a configured Jinja2 environment."""
    tpl_dir = template_dir or TEMPLATE_DIR

    if not tpl_dir.exists():
        tpl_dir.mkdir(parents=True, exist_ok=True)

    return Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(disabled_extensions=("md", "txt")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_report(
    generated_sections: list[dict[str, Any]],
    analysis_results: dict[str, Any],
    config: dict[str, Any],
    reviews: list[dict[str, Any]] | None = None,
    template_name: str = "pader_report.md.j2",
) -> str:
    """
    Render the final report from approved sections.

    Args:
        generated_sections: List of generated section dictionaries.
        analysis_results: Full analysis results (for metadata).
        config: Report configuration.
        reviews: Section review results (optional).
        template_name: Jinja2 template filename.

    Returns:
        Rendered report as a Markdown string.
    """
    env = create_jinja_env()

    # Build review lookup
    review_lookup: dict[str, dict[str, Any]] = {}
    if reviews:
        for review in reviews:
            review_lookup[review.get("section_id", "")] = review

    # Include all generated sections, attaching review status
    processed_sections = []
    for section in generated_sections:
        sid = section.get("section_id", "")
        review = review_lookup.get(sid, {})
        sec_copy = dict(section)
        sec_copy["review_status"] = review.get("status", "approved")
        sec_copy["review_notes"] = review.get("notes")
        processed_sections.append(sec_copy)

    context = {
        "report_type": config.get("display_name", config.get("report_type", "PADER")),
        "product_name": analysis_results.get("product_name", "Unknown"),
        "reporting_period_start": analysis_results.get("reporting_period_start", "Unknown"),
        "reporting_period_end": analysis_results.get("reporting_period_end", "Unknown"),
        "total_cases": analysis_results.get("total_cases", 0),
        "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "model": config.get("generation", {}).get("model", "Unknown"),
        "sections": processed_sections,
        "counting_note": analysis_results.get("counting_note", ""),
    }

    try:
        template = env.get_template(template_name)
        rendered = template.render(**context)
    except Exception as e:
        logger.error("Template rendering failed: %s", e)
        # Fallback: render without template
        rendered = _fallback_render(processed_sections, context)

    logger.info("Report rendered: %d characters, %d sections", len(rendered), len(processed_sections))
    return rendered


def _fallback_render(
    sections: list[dict[str, Any]],
    context: dict[str, Any],
) -> str:
    """
    Fallback renderer if Jinja2 template is not available.
    Generates a simple Markdown report.
    """
    lines = [
        f"# {context.get('report_type', 'Safety Report')}",
        "",
        f"**Product:** {context.get('product_name', 'Unknown')}",
        f"**Reporting Period:** {context.get('reporting_period_start')} to {context.get('reporting_period_end')}",
        f"**Total Cases:** {context.get('total_cases', 0)}",
        f"**Generated:** {context.get('generated_date', '')}",
        f"**Model:** {context.get('model', '')}",
        "",
        f"*{context.get('counting_note', '')}*",
        "",
        "---",
        "",
    ]

    for section in sections:
        lines.append(f"## {section.get('title', 'Untitled')}")
        lines.append("")
        lines.append(section.get("content", "*No content.*"))
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def save_report(
    report_content: str,
    output_path: str | Path,
) -> Path:
    """
    Save the rendered report to a file.

    Args:
        report_content: Rendered report string.
        output_path: Path to save the report.

    Returns:
        Path to the saved file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    logger.info("Report saved to %s", output_path)
    return output_path


def save_generation_metadata(
    generated_sections: list[dict[str, Any]],
    validation_results: dict[str, Any],
    reviews: list[dict[str, Any]] | None,
    output_path: str | Path,
) -> Path:
    """
    Save generation metadata for traceability.

    Includes: section IDs, models used, evidence keys, validation
    status, and review status for each section.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = {
        "generated_date": datetime.now().isoformat(),
        "sections": [],
    }

    for section in generated_sections:
        entry = {
            "section_id": section.get("section_id"),
            "title": section.get("title"),
            "mode": section.get("mode"),
            "model": section.get("model"),
            "evidence_keys": section.get("evidence_keys"),
            "generation_status": section.get("status"),
        }

        # Add review status
        if reviews:
            review = next(
                (r for r in reviews if r.get("section_id") == section.get("section_id")),
                None,
            )
            if review:
                entry["review_status"] = review.get("status")
                entry["review_notes"] = review.get("notes")

        metadata["sections"].append(entry)

    # Add validation summary (including per-section details for traceability)
    metadata["validation"] = {
        "overall_status": validation_results.get("overall_status"),
        "completeness": validation_results.get("completeness"),
        "cross_section_consistency": validation_results.get("cross_section_consistency"),
        "sections": validation_results.get("sections", []),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Generation metadata saved to %s", output_path)
    return output_path
