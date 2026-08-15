"""
Tests for the data ingestion module.
Validates loading, schema validation, date parsing, multi-value splitting,
and case-level deduplication.
"""

import pytest
from pathlib import Path

from src.ingest import (
    ingest,
    load_dataset,
    split_multi_value_field,
    validate_schema,
)

DATASET_PATH = Path(__file__).parent.parent / "docs" / "Bisoprolol_icsr_sample_1068rows.xlsx"


class TestLoadDataset:
    """Test dataset loading."""

    @pytest.fixture
    def dataset(self):
        if not DATASET_PATH.exists():
            pytest.skip("Dataset file not available")
        return load_dataset(DATASET_PATH)

    def test_loads_correct_shape(self, dataset):
        assert dataset.shape == (1068, 67)

    def test_has_required_columns(self, dataset):
        required = ["safetyreportid", "serious", "patient_patientsex"]
        for col in required:
            assert col in dataset.columns

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_dataset("nonexistent.xlsx")

    def test_unsupported_format_raises(self):
        # Create a temp file with wrong extension
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            with pytest.raises(ValueError):
                load_dataset(f.name)


class TestSplitMultiValue:
    """Test comma-packed field splitting."""

    def test_single_value(self):
        assert split_multi_value_field("Coma") == ["Coma"]

    def test_multiple_values(self):
        result = split_multi_value_field("Acute kidney injury,Drug ineffective")
        assert result == ["Acute kidney injury", "Drug ineffective"]

    def test_nan_returns_empty(self):
        import pandas as pd
        assert split_multi_value_field(pd.NA) == []
        assert split_multi_value_field(float("nan")) == []

    def test_empty_string_returns_empty(self):
        assert split_multi_value_field("") == []

    def test_strips_whitespace(self):
        result = split_multi_value_field(" Pain , Nausea ")
        assert result == ["Pain", "Nausea"]


class TestIngestPipeline:
    """Test the full ingestion pipeline."""

    @pytest.fixture
    def ingest_result(self):
        if not DATASET_PATH.exists():
            pytest.skip("Dataset file not available")
        return ingest(DATASET_PATH)

    def test_row_count(self, ingest_result):
        assert ingest_result["row_count"] == 1068

    def test_case_count(self, ingest_result):
        assert ingest_result["case_count"] == 1024

    def test_has_row_df_and_case_df(self, ingest_result):
        assert "row_df" in ingest_result
        assert "case_df" in ingest_result
        assert len(ingest_result["row_df"]) == 1068
        assert len(ingest_result["case_df"]) == 1024

    def test_reactions_list_populated(self, ingest_result):
        case_df = ingest_result["case_df"]
        assert "reactions_list" in case_df.columns
        # At least some cases should have reactions
        non_empty = case_df["reactions_list"].apply(lambda x: len(x) > 0).sum()
        assert non_empty > 0

    def test_reaction_outcome_pairs_populated(self, ingest_result):
        case_df = ingest_result["case_df"]
        assert "reaction_outcome_pairs" in case_df.columns

    def test_primary_country_field(self, ingest_result):
        assert ingest_result["primary_country_field"] == "primarysourcecountry"
