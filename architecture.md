# Phera — Architecture Document

## Overview

Phera implements a pharmacovigilance safety report pipeline modeled on the structure and reporting logic of FDA 21 CFR 314.80 and ICH E2C guidelines, with a strict architectural separation between:

1. **Deterministic computation** (Python/pandas) — produces all numbers and statistical breakdowns
2. **Configuration-driven instructions** (YAML/Markdown) — controls what each section sees and how it is drafted
3. **LLM generation** (Replicate / `openai/gpt-5.6-luna`) — phrases approved evidence as regulatory prose
4. **Automated Validation Suite** — 7 screening checks for numeric grounding, MedDRA integrity, counting accuracy, and inter-section checksums
5. **Human review** — two review checkpoints before any content becomes final

---

## Module Responsibilities

### `ingest.py`
- Loads XLSX/CSV ICSR dataset
- Validates schema (67 columns, required safety report fields)
- Parses integer-format dates (YYYYMMDD)
- Splits comma-packed reaction/outcome fields with positional pairing
- Deduplicates: 1,068 rows -> 1,024 unique cases (by `safetyreportid`)

### `analyze.py`
- Pure Python/pandas — **NO LLM**
- Computes 34 quantitative metric breakdowns across 38 total top-level keys in `analysis_results.json` (34 quantitative metric fields + 4 administrative header fields)
- Produces `analysis_results.json` — the single source of truth for the entire pipeline
- Every number in the final report traces back to this module

### `context_builder.py`
- Loads YAML report configuration (`src/config/report_types/pader.yaml`)
- Loads prompt files (`src/config/prompts/system_base.md` + section instructions)
- `build_section_context()` — the critical V1 boundary:
  - Accepts a section config and analysis results
  - Returns ONLY the evidence keys declared in that section's YAML config
  - Raises `KeyError` if a declared evidence key is missing
  - Never passes raw DataFrames or unneeded section metrics to the LLM

### `generate.py`
- `ReplicateGenerator` — wraps `replicate.run()` with `openai/gpt-5.6-luna`
- Handles `string[]` output normalization (Replicate returns string lists)
- Routes sections to LLM generation or deterministic Python rendering based on `mode`
- Renders deterministic tables (`summary_tabulation` using exact PT serious/non-serious splits, and `case_index`)
- Records generation metadata per section

### `validate.py`
- 7 automated screening validators:
  1. `numeric_consistency`: Extracts numbers from generated text and verifies existence in evidence packet (includes comma normalization `1,024` == `1024` and regulatory citation exemptions like `21 CFR 314.80`).
  2. `unsupported_claims`: Flags conclusion language without evidence (e.g., "no safety concern", "potential signal", "causally related").
  3. `counting_level_mismatch`: Semantic, config-driven validator checking reaction/outcome frequency labels and verifying claims like *"80 cases experienced Acute kidney injury"* against verified evidence counts.
  4. `meddra_term_integrity`: Flags typos or illegal space-splits in MedDRA Preferred Terms (e.g., `Bradi cardia`, `Brdycardia`).
  5. `dangling_content`: Detects unclosed bullet points or incomplete case records.
  6. `completeness`: Global check verifying all required sections are present and non-empty.
  7. `cross_section_consistency`: Global checksum validator ensuring inter-section mathematical invariants (e.g., $\text{Serious PT Count} + \text{Non-Serious PT Count} == \text{Total PT Count}$ for all 50 PTs).

### `review.py`
- CLI-based human review with two checkpoints:
  - Checkpoint A: approve/flag analysis results
  - Checkpoint B: approve/flag/regenerate each section (auto-approved with `--skip-review`)

### `render.py`
- Jinja2 Markdown report rendering (`templates/pader_report.md.j2`)
- Fallback renderer if template missing
- Saves `generation_metadata.json` containing section statuses, review feedback, per-section checks, completeness, and `cross_section_consistency` checksum results.

### `pipeline.py`
- Orchestrator wiring all 8 pipeline steps together
- CLI entry point supporting `--report-type`, `--skip-review`, and `--analysis-only`

---

## V1 Configurable Instructions

The Version 1 feature makes section behavior configuration-driven rather than hard-coded:

```yaml
# pader.yaml snippet
sections:
  - id: narrative_summary
    title: Narrative Summary and Analysis
    mode: llm
    evidence: [total_cases, serious_cases, top_reactions, top_serious_reactions, outcome_breakdown]
    instruction_file: prompts/narrative_summary.md
```

The generation engine reads evidence keys and instructions from config files.
Changing an instruction prompt or evidence list requires zero code modifications.

---

## Data Flow Invariants

1. Raw DataFrames never reach the LLM context.
2. Each section receives only its declared evidence keys.
3. All numbers come from `analyze.py`, never from the LLM.
4. A successful API call does not make a section final (human review sign-off required).
5. The Case Index and Summary Tabulation bypass the LLM entirely (100% deterministic).
6. Cross-section checksums enforce $\text{Serious} + \text{Non-Serious} == \text{Total}$ across all Preferred Terms.
