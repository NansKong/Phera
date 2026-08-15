"""
Phera — Deterministic Analysis Module

ALL computation is done in Python/pandas. No LLM is used here.
Produces a JSON-serializable analysis_results dictionary that becomes
the single source of truth for downstream section generation.

Every number in the final report traces back to this module.
"""

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Product information
PRODUCT_NAME = "Bisoprolol"
REPORT_TYPE = "PADER"

# Top N for reaction/country rankings
TOP_N_REACTIONS = 20
TOP_N_COUNTRIES = 15
TOP_N_ALERT_CASES = 50


def _safe_value_counts(series: pd.Series, dropna: bool = False) -> dict[str, int]:
    """Convert value_counts to a plain dict with string keys."""
    counts = series.value_counts(dropna=dropna)
    return {str(k): int(v) for k, v in counts.items()}


def _compute_reporting_period(case_df: pd.DataFrame) -> dict[str, str]:
    """Extract reporting period dates."""
    report_dates = case_df["report_date"].dropna()

    if report_dates.empty:
        return {
            "reporting_period_start": "Unknown",
            "reporting_period_end": "Unknown",
        }

    return {
        "reporting_period_start": report_dates.min().strftime("%Y-%m-%d"),
        "reporting_period_end": report_dates.max().strftime("%Y-%m-%d"),
    }


def _compute_seriousness(case_df: pd.DataFrame) -> dict[str, Any]:
    """Compute case-level seriousness breakdown."""
    serious_counts = _safe_value_counts(case_df["serious"])

    serious_cases = serious_counts.get("serious", 0)
    non_serious_cases = serious_counts.get("not serious", 0)
    total = len(case_df)

    serious_pct = round(serious_cases / total * 100, 1) if total > 0 else 0.0

    return {
        "serious_cases": serious_cases,
        "non_serious_cases": non_serious_cases,
        "serious_pct": f"{serious_pct}%",
        "seriousness_breakdown": serious_counts,
    }


def _compute_demographics(case_df: pd.DataFrame) -> dict[str, Any]:
    """Compute age and sex distributions at case level."""
    # Sex breakdown
    sex_breakdown = _safe_value_counts(case_df["patient_patientsex"], dropna=True)
    # Count unknowns/blanks
    sex_unknown = int(case_df["patient_patientsex"].isna().sum())
    if sex_unknown > 0:
        sex_breakdown["unknown"] = sex_unknown

    # Age group breakdown
    age_breakdown = {}
    if "patient_patientagegroup" in case_df.columns:
        age_breakdown = _safe_value_counts(case_df["patient_patientagegroup"], dropna=True)
        age_unknown = int(case_df["patient_patientagegroup"].isna().sum())
        if age_unknown > 0:
            age_breakdown["unknown"] = age_unknown

    return {
        "sex_breakdown": sex_breakdown,
        "age_breakdown": age_breakdown,
    }


def _compute_country_breakdown(
    case_df: pd.DataFrame, country_field: str
) -> dict[str, int]:
    """Compute top countries at case level."""
    countries = _safe_value_counts(case_df[country_field], dropna=True)

    # Return top N + aggregate rest
    top_countries = dict(list(countries.items())[:TOP_N_COUNTRIES])
    remaining = sum(list(countries.values())[TOP_N_COUNTRIES:])
    if remaining > 0:
        top_countries["Other"] = remaining

    return top_countries


def _compute_reactions(case_df: pd.DataFrame) -> dict[str, Any]:
    """
    Compute reaction frequencies from the exploded reactions_list.
    Reactions are counted at case level (each reaction counted once per case).
    """
    # Flatten all reactions across cases
    all_reactions: list[str] = []
    for reactions_list in case_df["reactions_list"]:
        if isinstance(reactions_list, list):
            # Deduplicate within a case (count each reaction once per case)
            unique_in_case = set(reactions_list)
            all_reactions.extend(unique_in_case)

    reaction_counts = Counter(all_reactions)
    top_reactions = dict(reaction_counts.most_common(TOP_N_REACTIONS))

    return {
        "top_reactions": top_reactions,
        "reaction_breakdown": dict(reaction_counts.most_common(50)),
    }


def _compute_serious_reactions(case_df: pd.DataFrame) -> dict[str, int]:
    """Compute top reactions among serious cases only."""
    serious_df = case_df[case_df["serious"] == "serious"]

    all_reactions: list[str] = []
    for reactions_list in serious_df["reactions_list"]:
        if isinstance(reactions_list, list):
            unique_in_case = set(reactions_list)
            all_reactions.extend(unique_in_case)

    reaction_counts = Counter(all_reactions)
    return dict(reaction_counts.most_common(TOP_N_REACTIONS))


def _compute_serious_reaction_breakdown(case_df: pd.DataFrame) -> dict[str, int]:
    """Compute ALL reactions among serious cases (not top-N truncated).
    Used by the Summary Tabulation for exact per-PT serious counts."""
    serious_df = case_df[case_df["serious"] == "serious"]

    all_reactions: list[str] = []
    for reactions_list in serious_df["reactions_list"]:
        if isinstance(reactions_list, list):
            unique_in_case = set(reactions_list)
            all_reactions.extend(unique_in_case)

    return dict(Counter(all_reactions))


def _compute_non_serious_reaction_breakdown(case_df: pd.DataFrame) -> dict[str, int]:
    """Compute ALL reactions among non-serious cases.
    Used by the Summary Tabulation for exact per-PT non-serious counts."""
    non_serious_df = case_df[case_df["serious"] != "serious"]

    all_reactions: list[str] = []
    for reactions_list in non_serious_df["reactions_list"]:
        if isinstance(reactions_list, list):
            unique_in_case = set(reactions_list)
            all_reactions.extend(unique_in_case)

    return dict(Counter(all_reactions))


def _compute_outcomes(case_df: pd.DataFrame) -> dict[str, int]:
    """
    Compute outcome distribution from exploded reaction-outcome pairs.
    Each outcome is counted per reaction-outcome pair.
    """
    all_outcomes: list[str] = []
    for pairs in case_df["reaction_outcome_pairs"]:
        if isinstance(pairs, list):
            for _, outcome in pairs:
                all_outcomes.append(outcome)

    return dict(Counter(all_outcomes).most_common())


def _compute_reactions_by_age(case_df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Cross-tabulate top reactions by age group."""
    if "patient_patientagegroup" not in case_df.columns:
        return {}

    result: dict[str, dict[str, int]] = {}
    age_groups = case_df["patient_patientagegroup"].dropna().unique()

    for age_group in age_groups:
        age_subset = case_df[case_df["patient_patientagegroup"] == age_group]
        reactions: list[str] = []
        for reactions_list in age_subset["reactions_list"]:
            if isinstance(reactions_list, list):
                reactions.extend(set(reactions_list))

        top = dict(Counter(reactions).most_common(10))
        result[str(age_group)] = top

    return result


def _compute_reactions_by_sex(case_df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Cross-tabulate top reactions by sex."""
    result: dict[str, dict[str, int]] = {}

    for sex in ["female", "male"]:
        sex_subset = case_df[case_df["patient_patientsex"] == sex]
        reactions: list[str] = []
        for reactions_list in sex_subset["reactions_list"]:
            if isinstance(reactions_list, list):
                reactions.extend(set(reactions_list))

        top = dict(Counter(reactions).most_common(10))
        result[sex] = top

    return result


def _compute_monthly_case_counts(case_df: pd.DataFrame) -> dict[str, int]:
    """Compute case counts per month."""
    monthly = case_df.set_index("report_date").resample("ME").size()
    return {dt.strftime("%Y-%m"): int(count) for dt, count in monthly.items() if count > 0}


def _compute_reactions_over_time(case_df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Compute top reaction counts per month."""
    result: dict[str, dict[str, int]] = {}

    case_df = case_df.copy()
    case_df["month"] = case_df["report_date"].dt.to_period("M")

    for month, month_df in case_df.groupby("month"):
        reactions: list[str] = []
        for reactions_list in month_df["reactions_list"]:
            if isinstance(reactions_list, list):
                reactions.extend(set(reactions_list))

        top = dict(Counter(reactions).most_common(5))
        result[str(month)] = top

    return result


def _compute_monthly_top_reactions(case_df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Top reactions per month for trend analysis."""
    return _compute_reactions_over_time(case_df)


def _compute_country_trend(
    case_df: pd.DataFrame, country_field: str
) -> dict[str, dict[str, int]]:
    """Country distribution per month."""
    result: dict[str, dict[str, int]] = {}

    case_df = case_df.copy()
    case_df["month"] = case_df["report_date"].dt.to_period("M")

    for month, month_df in case_df.groupby("month"):
        countries = _safe_value_counts(month_df[country_field], dropna=True)
        result[str(month)] = dict(list(countries.items())[:10])

    return result


def _compute_seriousness_trend(case_df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Seriousness breakdown per month."""
    result: dict[str, dict[str, int]] = {}

    case_df = case_df.copy()
    case_df["month"] = case_df["report_date"].dt.to_period("M")

    for month, month_df in case_df.groupby("month"):
        result[str(month)] = _safe_value_counts(month_df["serious"])

    return result


def _compute_alert_cases(case_df: pd.DataFrame) -> dict[str, Any]:
    """
    Identify 15-day expedited (alert) cases.
    fulfillexpeditecriteria == 'yes' indicates expedited cases.
    """
    alert_df = case_df[case_df["fulfillexpeditecriteria"] == "yes"]
    alert_count = len(alert_df)

    # Build alert cases table (top N for the report)
    alert_table = []
    for _, row in alert_df.head(TOP_N_ALERT_CASES).iterrows():
        entry = {
            "case_id": str(row["safetyreportid"]),
            "reactions": row.get("patient_reaction_reactionmeddrapt", ""),
            "serious": str(row.get("serious", "")),
            "outcome": str(row.get("patient_reaction_reactionoutcome", "")),
            "country": str(row.get("primarysourcecountry", "")),
            "report_date": (
                row["report_date"].strftime("%Y-%m-%d")
                if pd.notna(row.get("report_date"))
                else "Unknown"
            ),
        }

        # Add seriousness criteria
        criteria = []
        for crit_col, crit_name in [
            ("seriousnessdeath", "Death"),
            ("seriousnesslifethreatening", "Life-threatening"),
            ("seriousnesshospitalization", "Hospitalization"),
            ("seriousnessdisabling", "Disabling"),
            ("seriousnesscongenitalanomali", "Congenital anomaly"),
            ("seriousnessother", "Other serious"),
        ]:
            if crit_col in row.index and str(row[crit_col]).strip().lower() in ("1", "yes", "true"):
                criteria.append(crit_name)

        entry["seriousness_criteria"] = criteria
        alert_table.append(entry)

    return {
        "alert_case_count": alert_count,
        "alert_cases_table": alert_table,
    }


def _compute_case_index(case_df: pd.DataFrame) -> list[dict[str, str]]:
    """
    Build the full case index listing for deterministic rendering.
    One entry per case with: case ID, reaction, seriousness, date, country, outcome.
    """
    index_rows = []

    for _, row in case_df.iterrows():
        index_rows.append({
            "case_id": str(row["safetyreportid"]),
            "reaction": str(row.get("patient_reaction_reactionmeddrapt", "")),
            "serious": str(row.get("serious", "")),
            "report_date": (
                row["report_date"].strftime("%Y-%m-%d")
                if pd.notna(row.get("report_date"))
                else "Unknown"
            ),
            "country": str(row.get("primarysourcecountry", "")),
            "outcome": str(row.get("patient_reaction_reactionoutcome", "")),
        })

    return index_rows


def analyze(ingest_result: dict) -> dict[str, Any]:
    """
    Run all deterministic analyses on the ingested data.

    Args:
        ingest_result: Dictionary from ingest() containing row_df, case_df, etc.

    Returns:
        JSON-serializable dictionary with all analysis keys required by
        the PADER report configuration.
    """
    case_df = ingest_result["case_df"]
    country_field = ingest_result["primary_country_field"]

    logger.info("Starting deterministic analysis on %d cases", len(case_df))

    # Reporting period
    period = _compute_reporting_period(case_df)

    # Seriousness
    seriousness = _compute_seriousness(case_df)

    # Demographics
    demographics = _compute_demographics(case_df)

    # Country
    country_breakdown = _compute_country_breakdown(case_df, country_field)

    # Reactions
    reactions = _compute_reactions(case_df)
    serious_reactions = _compute_serious_reactions(case_df)
    serious_reaction_breakdown = _compute_serious_reaction_breakdown(case_df)
    non_serious_reaction_breakdown = _compute_non_serious_reaction_breakdown(case_df)

    # Outcomes
    outcome_breakdown = _compute_outcomes(case_df)

    # Cross-tabulations
    reactions_by_age = _compute_reactions_by_age(case_df)
    reactions_by_sex = _compute_reactions_by_sex(case_df)
    reactions_over_time = _compute_reactions_over_time(case_df)

    # Trends
    monthly_case_counts = _compute_monthly_case_counts(case_df)
    monthly_top_reactions = _compute_monthly_top_reactions(case_df)
    country_trend = _compute_country_trend(case_df, country_field)
    seriousness_trend = _compute_seriousness_trend(case_df)

    # Alert / expedited cases
    alerts = _compute_alert_cases(case_df)

    # Case index (for deterministic section)
    case_index = _compute_case_index(case_df)

    # Assemble the full results
    results: dict[str, Any] = {
        # Reporting period
        "product_name": PRODUCT_NAME,
        "reporting_period_start": period["reporting_period_start"],
        "reporting_period_end": period["reporting_period_end"],
        "report_type": REPORT_TYPE,
        "application_number": "Not supplied",

        # Case counts
        "total_cases": len(case_df),
        "new_cases_in_period": len(case_df),  # All cases are within this reporting period
        "row_count": ingest_result["row_count"],

        # Seriousness
        "serious_cases": seriousness["serious_cases"],
        "non_serious_cases": seriousness["non_serious_cases"],
        "serious_pct": seriousness["serious_pct"],
        "seriousness_breakdown": seriousness["seriousness_breakdown"],

        # Demographics
        "age_breakdown": demographics["age_breakdown"],
        "sex_breakdown": demographics["sex_breakdown"],

        # Geography
        "country_breakdown": country_breakdown,

        # Reactions
        "top_reactions": reactions["top_reactions"],
        "top_serious_reactions": serious_reactions,
        "reaction_breakdown": reactions["reaction_breakdown"],
        "serious_reaction_breakdown": serious_reaction_breakdown,
        "non_serious_reaction_breakdown": non_serious_reaction_breakdown,

        # Outcomes
        "outcome_breakdown": outcome_breakdown,

        # Cross-tabulations
        "reactions_by_age_group": reactions_by_age,
        "reactions_by_sex": reactions_by_sex,
        "reactions_over_time": reactions_over_time,

        # Trends
        "monthly_case_counts": monthly_case_counts,
        "monthly_top_reaction_counts": monthly_top_reactions,
        "country_trend": country_trend,
        "seriousness_trend": seriousness_trend,

        # Alert / 15-day expedited cases
        # Pursuant to 21 CFR 314.80, 15-day Alert reports require cases to be BOTH serious AND unlisted (unexpected).
        # Since no product label / CCDS is supplied (expectedness_available = False), 15-day alert status cannot be determined.
        "alert_case_count": "Not determinable (expectedness/unlisted status unavailable without CCDS)",
        "alert_case_reason": (
            "Pursuant to FDA 21 CFR 314.80, 15-day Alert reports require cases to be both serious and unlisted. "
            "Because no product label or Company Core Data Sheet (CCDS) was supplied with this dataset, "
            f"expectedness (listedness) cannot be determined. A total of {seriousness['serious_cases']:,} cases meet seriousness criteria."
        ),
        "alert_cases_table": alerts["alert_cases_table"],

        # Data availability flags
        "soc_available": False,
        "expectedness_available": False,
        "actions_provided": False,

        # Case index (deterministic)
        "case_index": case_index,

        # Metadata
        "primary_country_field": country_field,
        # Counting methodology
        "reaction_counting_method": "case_level_deduplicated",
        "counting_note": (
            "Counting level is specified for each analysis. Case-level statistics refer to "
            "unique safety reports. Reaction frequencies count each Preferred Term once per "
            "case (deduplicated within each case); outcome frequencies may include multiple "
            "entries from the same case."
        ),
    }

    logger.info(
        "Analysis complete: %d keys produced, %d total cases, %d serious",
        len(results),
        results["total_cases"],
        results["serious_cases"],
    )

    return results


def save_analysis_results(results: dict[str, Any], output_path: str | Path) -> Path:
    """
    Save analysis results to a JSON file.

    Args:
        results: Analysis results dictionary.
        output_path: Path to save the JSON file.

    Returns:
        Path to the saved file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Analysis results saved to %s", output_path)
    return output_path
