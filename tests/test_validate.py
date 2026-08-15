from src.validate import (
    extract_numbers_from_text,
    validate_completeness,
    validate_cross_section_consistency,
    validate_numeric_consistency,
    validate_unsupported_claims,
)


class TestNumericConsistency:
    """Test that invented numbers are flagged."""

    def test_supported_numbers_pass(self):
        text = "A total of 1024 cases were reported, of which 1023 were serious."
        evidence = {"total_cases": 1024, "serious_cases": 1023}
        result = validate_numeric_consistency(text, evidence)
        assert result["status"] == "pass"

    def test_unsupported_number_warns(self):
        text = "A total of 9999 cases were reported."
        evidence = {"total_cases": 1024}
        result = validate_numeric_consistency(text, evidence)
        assert result["status"] == "warn"
        assert "9999" in result["unsupported_numbers"]

    def test_percentage_matching(self):
        text = "Of these, 99.9% were serious."
        evidence = {"serious_pct": "99.9%"}
        result = validate_numeric_consistency(text, evidence)
        assert result["status"] == "pass"

    def test_trivial_numbers_ignored(self):
        """Small common numbers (0-10) should not trigger warnings."""
        text = "Section 1 of 8 sections."
        evidence = {"sections": 8}
        result = validate_numeric_consistency(text, evidence)
        # 1 is trivial, 8 is in evidence
        assert result["status"] == "pass"


class TestExtractNumbers:
    """Test number extraction from text."""

    def test_integer(self):
        assert "1024" in extract_numbers_from_text("Total: 1024 cases")

    def test_decimal(self):
        assert "99.9" in extract_numbers_from_text("99.9 percent")

    def test_percentage(self):
        assert "99.9%" in extract_numbers_from_text("99.9% were serious")


class TestUnsupportedClaims:
    """Test that conclusion language is flagged."""

    def test_no_safety_concern_flagged(self):
        text = "No safety concern was identified during the period."
        result = validate_unsupported_claims(text)
        assert result["status"] == "warn"
        assert len(result["flagged_phrases"]) > 0

    def test_signal_flagged(self):
        text = "A potential signal was observed."
        result = validate_unsupported_claims(text)
        assert result["status"] == "warn"

    def test_causal_flagged(self):
        text = "The reaction was causally related to the drug."
        result = validate_unsupported_claims(text)
        assert result["status"] == "warn"

    def test_clean_text_passes(self):
        text = (
            "During the reporting period, 1024 cases were received. "
            "Of these, 1023 were classified as serious."
        )
        result = validate_unsupported_claims(text)
        assert result["status"] == "pass"

class TestCountingLevelMismatch:
    """Test that mislabeled or contradictory reaction/outcome counting levels are flagged."""

    def test_unsupported_case_claim_flagged(self):
        from src.validate import validate_counting_level_mismatch
        # Claiming 99 cases experienced Acute kidney injury when actual case count is 80
        text = "99 cases experienced Acute kidney injury."
        evidence = {"top_reactions": {"Acute kidney injury": 80}, "reaction_counting_method": "case_level_deduplicated"}
        result = validate_counting_level_mismatch(text, evidence)
        assert result["status"] == "warn"
        assert len(result["flagged_phrases"]) > 0

    def test_verified_case_claim_passes(self):
        from src.validate import validate_counting_level_mismatch
        # 80 is the verified case-level count for Acute kidney injury
        text = "80 cases experienced Acute kidney injury."
        evidence = {"top_reactions": {"Acute kidney injury": 80}, "reaction_counting_method": "case_level_deduplicated"}
        result = validate_counting_level_mismatch(text, evidence)
        assert result["status"] == "pass"

    def test_valid_counting_terms_pass(self):
        from src.validate import validate_counting_level_mismatch
        text = (
            "Top reported reactions by case-level reaction frequency include Acute kidney injury (80). "
            "Reactions are counted once per case and deduplicated within each case. "
            "Outcome frequencies across reported outcome entries are reported."
        )
        result = validate_counting_level_mismatch(text)
        assert result["status"] == "pass"

    def test_outcome_case_level_mislabel_flagged(self):
        from src.validate import validate_counting_level_mismatch
        text = "Outcome distribution (case level): recovered 1280."
        result = validate_counting_level_mismatch(text)
        assert result["status"] == "warn"
        assert len(result["flagged_phrases"]) > 0


class TestMeddraTermIntegrity:
    """Test that MedDRA Preferred Term typos or split words are flagged."""

    def test_meddra_typo_flagged(self):
        from src.validate import validate_meddra_term_integrity
        text = "Episodes of Bradi cardia (37) were reported."
        result = validate_meddra_term_integrity(text)
        assert result["status"] == "warn"
        assert len(result["flagged_phrases"]) > 0

    def test_correct_meddra_term_passes(self):
        from src.validate import validate_meddra_term_integrity
        text = "Episodes of Bradycardia (37) were reported."
        result = validate_meddra_term_integrity(text)
        assert result["status"] == "pass"


class TestDanglingContent:
    """Test that dangling or incomplete case bullet points are flagged."""

    def test_dangling_case_flagged(self):
        from src.validate import validate_dangling_content
        text = "- Case 25063910: details...\n- Case 25066459:"
        result = validate_dangling_content(text)
        assert result["status"] == "warn"
        assert len(result["flagged_phrases"]) > 0

    def test_complete_case_passes(self):
        from src.validate import validate_dangling_content
        text = "- Case 25063910: details...\n- Case 25066459: complete details."
        result = validate_dangling_content(text)
        assert result["status"] == "pass"

class TestCompleteness:
    """Test that completeness checks work."""

    def test_all_sections_present_passes(self):
        generated = [
            {"section_id": "s1", "content": "text", "status": "generated"},
            {"section_id": "s2", "content": "text", "status": "generated"},
        ]
        config_sections = [{"id": "s1"}, {"id": "s2"}]
        result = validate_completeness(generated, config_sections)
        assert result["status"] == "pass"

    def test_missing_section_fails(self):
        generated = [
            {"section_id": "s1", "content": "text", "status": "generated"},
        ]
        config_sections = [{"id": "s1"}, {"id": "s2"}]
        result = validate_completeness(generated, config_sections)
        assert result["status"] == "fail"
        assert "s2" in result["missing_sections"]

    def test_empty_section_fails(self):
        generated = [
            {"section_id": "s1", "content": "", "status": "generated"},
        ]
        config_sections = [{"id": "s1"}]
        result = validate_completeness(generated, config_sections)
        assert result["status"] == "fail"
        assert "s1" in result["empty_sections"]


class TestCrossSectionConsistency:
    """Test that cross-section consistency catches data contradictions."""

    def test_consistent_data_passes(self):
        """When serious + non_serious == total for all PTs, should pass."""
        analysis = {
            "reaction_breakdown": {"Drug ineffective": 54, "Bradycardia": 37},
            "serious_reaction_breakdown": {"Drug ineffective": 53, "Bradycardia": 37},
            "non_serious_reaction_breakdown": {"Drug ineffective": 1},
        }
        result = validate_cross_section_consistency(analysis)
        assert result["status"] == "pass"
        assert len(result["mismatches"]) == 0
        assert result["pts_checked"] == 2

    def test_inconsistent_data_fails(self):
        """The Drug ineffective scenario: 54 != 54 + 0 when serious is actually 53."""
        analysis = {
            "reaction_breakdown": {"Drug ineffective": 54},
            "serious_reaction_breakdown": {"Drug ineffective": 54},
            "non_serious_reaction_breakdown": {},
        }
        # This would pass (54 == 54+0), but if we change serious to 53:
        analysis["serious_reaction_breakdown"]["Drug ineffective"] = 53
        result = validate_cross_section_consistency(analysis)
        assert result["status"] == "fail"
        assert len(result["mismatches"]) == 1
        assert "Drug ineffective" in result["mismatches"][0]

    def test_missing_breakdown_keys_handled(self):
        """If breakdown keys are absent, should use empty dicts and flag mismatches."""
        analysis = {
            "reaction_breakdown": {"Coma": 15},
        }
        result = validate_cross_section_consistency(analysis)
        assert result["status"] == "fail"
        assert len(result["mismatches"]) == 1

    def test_all_zeros_passes(self):
        """Edge case: empty breakdowns with empty reaction_breakdown."""
        analysis = {
            "reaction_breakdown": {},
            "serious_reaction_breakdown": {},
            "non_serious_reaction_breakdown": {},
        }
        result = validate_cross_section_consistency(analysis)
        assert result["status"] == "pass"
        assert result["pts_checked"] == 0
