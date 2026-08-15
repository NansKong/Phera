"""
Phera — Data Ingestion Module

Loads the Bisoprolol ICSR dataset, validates the schema, parses dates,
splits comma-packed multi-value fields (reactions, outcomes), and
provides both row-level and deduplicated case-level DataFrames.

The raw DataFrame is never exposed to downstream LLM steps.
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Required columns that must exist in the dataset
REQUIRED_COLUMNS = [
    "safetyreportid",
    "serious",
    "patient_patientsex",
    "patient_reaction_reactionmeddrapt",
    "patient_reaction_reactionoutcome",
    "report_date",
    "occurcountry",
    "primarysourcecountry",
    "primarysource_reportercountry",
    "fulfillexpeditecriteria",
]

# Date columns stored as integer format (YYYYMMDD)
INTEGER_DATE_COLUMNS = [
    "receivedate",
    "receiptdate",
    "transmissiondate",
]

# Primary country field selection
# The brief notes occurcountry and primarysource_reportercountry can differ.
# We select primarysourcecountry as the primary field because it represents
# the country where the report originated.
PRIMARY_COUNTRY_FIELD = "primarysourcecountry"


def load_dataset(filepath: str | Path) -> pd.DataFrame:
    """
    Load the ICSR dataset from an XLSX or CSV file.

    Args:
        filepath: Path to the dataset file (.xlsx or .csv)

    Returns:
        Raw DataFrame with all columns preserved.

    Raises:
        FileNotFoundError: If the dataset file does not exist.
        ValueError: If the file format is not supported.
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"Dataset file not found: {filepath}")

    logger.info("Loading dataset from %s", filepath)

    if filepath.suffix == ".xlsx":
        df = pd.read_excel(filepath, engine="openpyxl")
    elif filepath.suffix == ".csv":
        df = pd.read_csv(filepath)
    else:
        raise ValueError(f"Unsupported file format: {filepath.suffix}. Use .xlsx or .csv")

    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))
    return df


def validate_schema(df: pd.DataFrame) -> list[str]:
    """
    Validate that required columns exist in the DataFrame.

    Returns:
        List of warning messages (empty if all OK).

    Raises:
        ValueError: If critical columns are missing.
    """
    warnings = []
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Check for unexpected nulls in critical fields
    null_counts = {
        col: int(df[col].isna().sum())
        for col in ["safetyreportid", "serious", "patient_reaction_reactionmeddrapt"]
        if df[col].isna().any()
    }

    if null_counts:
        for col, count in null_counts.items():
            msg = f"Column '{col}' has {count} null values"
            warnings.append(msg)
            logger.warning(msg)

    return warnings


def parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse integer-format date columns (YYYYMMDD) into datetime objects.
    The 'report_date' column is already datetime from the source.
    """
    df = df.copy()

    for col in INTEGER_DATE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(
                df[col].astype(str).str.strip(),
                format="%Y%m%d",
                errors="coerce",
            )

    # Ensure report_date is datetime
    if "report_date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["report_date"]):
        df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")

    return df


def split_multi_value_field(value: Any) -> list[str]:
    """
    Split a comma-packed field into individual values.
    Returns empty list for null/NaN values.

    Example:
        'Acute kidney injury,Drug ineffective' -> ['Acute kidney injury', 'Drug ineffective']
    """
    if pd.isna(value) or str(value).strip() == "":
        return []

    return [v.strip() for v in str(value).split(",") if v.strip()]


def split_and_pair_reactions_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Split comma-packed reaction and outcome fields and create paired
    exploded rows. Reactions and outcomes are positionally paired.

    Returns:
        DataFrame with additional columns:
        - reactions_list: list of individual reactions
        - outcomes_list: list of individual outcomes
        - reaction_outcome_pairs: list of (reaction, outcome) tuples
    """
    df = df.copy()

    df["reactions_list"] = df["patient_reaction_reactionmeddrapt"].apply(split_multi_value_field)
    df["outcomes_list"] = df["patient_reaction_reactionoutcome"].apply(split_multi_value_field)

    # Pair reactions with outcomes positionally
    def pair_reactions_outcomes(row: pd.Series) -> list[tuple[str, str]]:
        reactions = row["reactions_list"]
        outcomes = row["outcomes_list"]
        pairs = []

        for i, reaction in enumerate(reactions):
            outcome = outcomes[i] if i < len(outcomes) else "unknown"
            pairs.append((reaction, outcome))

        return pairs

    df["reaction_outcome_pairs"] = df.apply(pair_reactions_outcomes, axis=1)

    return df


def get_case_level_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate to case level using safetyreportid.
    Keeps the first row per case (highest report version if sorted).

    Returns:
        Case-level DataFrame with one row per unique safetyreportid.
    """
    # Sort by version descending to keep the latest version
    if "safetyreportversion" in df.columns:
        df_sorted = df.sort_values("safetyreportversion", ascending=False)
    else:
        df_sorted = df

    case_df = df_sorted.drop_duplicates(subset="safetyreportid", keep="first")
    logger.info(
        "Deduplicated %d rows -> %d unique cases",
        len(df),
        len(case_df),
    )
    return case_df


def ingest(filepath: str | Path) -> dict:
    """
    Full ingestion pipeline: load, validate, parse, split, deduplicate.

    Args:
        filepath: Path to the ICSR dataset file.

    Returns:
        Dictionary with:
        - 'row_df': Full row-level DataFrame (parsed, multi-values split)
        - 'case_df': Case-level deduplicated DataFrame
        - 'row_count': Total row count
        - 'case_count': Unique case count
        - 'warnings': List of validation warnings
        - 'primary_country_field': Which country field is used
    """
    # Load
    df = load_dataset(filepath)

    # Validate
    warnings = validate_schema(df)

    # Parse dates
    df = parse_dates(df)

    # Split multi-value fields
    df = split_and_pair_reactions_outcomes(df)

    # Deduplicate to case level
    case_df = get_case_level_df(df)

    result = {
        "row_df": df,
        "case_df": case_df,
        "row_count": len(df),
        "case_count": len(case_df),
        "warnings": warnings,
        "primary_country_field": PRIMARY_COUNTRY_FIELD,
    }

    logger.info(
        "Ingestion complete: %d rows, %d cases, %d warnings",
        result["row_count"],
        result["case_count"],
        len(result["warnings"]),
    )

    return result
