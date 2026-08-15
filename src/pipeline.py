"""
Phera — Pipeline Orchestrator

Main entry point for the GenAR V1 pharmacovigilance safety report pipeline.

Usage:
    python -m src.pipeline --report-type pader
    python -m src.pipeline --report-type pader --skip-review
    python -m src.pipeline --report-type pader --analysis-only

All intermediate and output files are written to the project's output/ directory.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Load .env from the project root
load_dotenv(PROJECT_ROOT / ".env")

from .analyze import analyze, save_analysis_results
from .context_builder import load_report_config
from .generate import generate_report_sections
from .ingest import ingest
from .render import render_report, save_generation_metadata, save_report
from .review import review_all_sections, review_analysis_results
from .validate import validate_all_sections

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("phera")


def find_dataset(data_dir: Path, docs_dir: Path) -> Path:
    """
    Locate the dataset file. Checks data/ first, then docs/.

    Returns:
        Path to the dataset file.

    Raises:
        FileNotFoundError: If no dataset file is found.
    """
    # Check data/ directory first
    for ext in ("*.xlsx", "*.csv"):
        files = list(data_dir.glob(ext))
        if files:
            return files[0]

    # Fall back to docs/ directory
    for ext in ("*.xlsx", "*.csv"):
        files = list(docs_dir.glob(ext))
        if files:
            return files[0]

    raise FileNotFoundError(
        f"No dataset file found in {data_dir} or {docs_dir}. "
        "Place the Bisoprolol ICSR dataset (.xlsx or .csv) in the data/ directory."
    )


def run_pipeline(
    report_type: str = "pader",
    skip_review: bool = False,
    analysis_only: bool = False,
) -> None:
    """
    Execute the full Phera pipeline.

    Steps:
    1. Find and ingest dataset
    2. Run deterministic analysis
    3. Checkpoint A: Human review of analysis (unless skipped)
    4. Load report configuration
    5. Generate sections (LLM + deterministic)
    6. Validate generated sections
    7. Checkpoint B: Human review of sections (unless skipped)
    8. Render and save final report

    Args:
        report_type: Report type identifier (default: 'pader').
        skip_review: If True, skip human review checkpoints.
        analysis_only: If True, stop after analysis (no generation).
    """
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    data_dir = PROJECT_ROOT / "data"
    docs_dir = PROJECT_ROOT / "docs"

    # ─── Step 1: Ingest ─────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 1: Data Ingestion")
    logger.info("=" * 60)

    dataset_path = find_dataset(data_dir, docs_dir)
    logger.info("Using dataset: %s", dataset_path)

    ingest_result = ingest(dataset_path)
    logger.info(
        "Ingested: %d rows, %d cases, %d warnings",
        ingest_result["row_count"],
        ingest_result["case_count"],
        len(ingest_result["warnings"]),
    )

    if ingest_result["warnings"]:
        for warning in ingest_result["warnings"]:
            logger.warning("Ingestion warning: %s", warning)

    # ─── Step 2: Deterministic Analysis ──────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 2: Deterministic Analysis")
    logger.info("=" * 60)

    analysis_results = analyze(ingest_result)
    analysis_path = save_analysis_results(
        analysis_results, output_dir / "analysis_results.json"
    )
    logger.info("Analysis saved to %s", analysis_path)

    if analysis_only:
        logger.info("Analysis-only mode — stopping here.")
        print(f"\n[OK] Analysis complete. Results saved to: {analysis_path}")
        return

    # --- Step 3: Checkpoint A - Analysis Review ----------------------
    if not skip_review:
        logger.info("=" * 60)
        logger.info("STEP 3: Checkpoint A — Analysis Review")
        logger.info("=" * 60)

        review_result = review_analysis_results(analysis_results)

        if review_result["status"] == "flagged":
            logger.warning(
                "Analysis flagged by reviewer: %s",
                review_result.get("notes", "No notes"),
            )
            print("\n[WARNING] Analysis was flagged. Review the issues and re-run.")
            return
    else:
        logger.info("Skipping Checkpoint A (--skip-review)")

    # ─── Step 4: Load Report Configuration ───────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 4: Loading Report Configuration")
    logger.info("=" * 60)

    config = load_report_config(report_type)
    logger.info(
        "Loaded config: %s v%s (%d sections)",
        config.get("report_type"),
        config.get("version"),
        len(config.get("sections", [])),
    )

    # ─── Step 5: Generate Sections ───────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 5: Section Generation")
    logger.info("=" * 60)

    generated_sections = generate_report_sections(config, analysis_results)

    successful = sum(1 for s in generated_sections if s.get("status") == "generated")
    failed = sum(1 for s in generated_sections if s.get("status") == "failed")
    logger.info("Generated: %d successful, %d failed", successful, failed)

    # ─── Step 6: Validation ──────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 6: Validation")
    logger.info("=" * 60)

    validation_results = validate_all_sections(
        generated_sections, config, analysis_results
    )
    logger.info("Validation overall: %s", validation_results["overall_status"])

    # Attach validation to sections for review display
    validation_lookup = {
        v["section_id"]: v
        for v in validation_results.get("sections", [])
    }
    for section in generated_sections:
        section["validation"] = validation_lookup.get(section["section_id"])

    # ─── Step 7: Checkpoint B — Section Review ───────────────────────
    reviews = None
    if not skip_review:
        logger.info("=" * 60)
        logger.info("STEP 7: Checkpoint B — Section Review")
        logger.info("=" * 60)

        reviews = review_all_sections(generated_sections)

        # Handle regeneration requests
        regen_sections = [r for r in reviews if r["status"] == "regenerate"]
        if regen_sections:
            logger.info(
                "%d sections marked for regeneration (not implemented in this run)",
                len(regen_sections),
            )
    else:
        logger.info("Skipping Checkpoint B (--skip-review) - Auto-approving all generated sections")
        reviews = [
            {"section_id": s["section_id"], "status": "approved", "notes": None}
            for s in generated_sections
        ]

    # ─── Step 8: Render Report ───────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 8: Report Rendering")
    logger.info("=" * 60)

    report_content = render_report(
        generated_sections, analysis_results, config, reviews
    )
    report_path = save_report(report_content, output_dir / "report_output.md")

    # Save generation metadata
    metadata_path = save_generation_metadata(
        generated_sections,
        validation_results,
        reviews,
        output_dir / "generation_metadata.json",
    )

    # ─── Done ────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 60)

    print(f"\n[OK] Pipeline complete!")
    print(f"  Report:    {report_path}")
    print(f"  Analysis:  {analysis_path}")
    print(f"  Metadata:  {metadata_path}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="phera",
        description="Phera — GenAR V1 Pharmacovigilance Safety Report Pipeline",
    )
    parser.add_argument(
        "--report-type",
        default="pader",
        help="Report type configuration to use (default: pader)",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip human review checkpoints (for automated testing)",
    )
    parser.add_argument(
        "--analysis-only",
        action="store_true",
        help="Run only data ingestion and analysis, then stop",
    )

    args = parser.parse_args()

    try:
        run_pipeline(
            report_type=args.report_type,
            skip_review=args.skip_review,
            analysis_only=args.analysis_only,
        )
    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
