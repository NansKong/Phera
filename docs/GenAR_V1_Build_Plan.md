# GenAR Challenge --- Technical Build Plan

## Version 1 Update: Configurable Instructions + Replicate `openai/gpt-5-nano`

**Updated:** August 2026\
**Baseline:** Version 0 technical build plan\
**Selected Version 1 feature:** Configurable instructions\
**LLM provider:** Replicate\
**Model:** `openai/gpt-5-nano`

------------------------------------------------------------------------

# 1. What We Are Building

A small pipeline that reads the Bisoprolol ICSR dataset, runs
deterministic Python analyses, packages only the relevant precomputed
numbers into a scoped section-specific prompt, asks an LLM to phrase ---
not compute --- each PADER section in regulatory-neutral prose, inserts
human approve/flag checkpoints, and renders approved sections into one
Markdown/HTML/PDF report.

Version 1 makes generation instructions configurable by section and
report type instead of keeping one global prompt.

------------------------------------------------------------------------

# 2. Recommended Tech Stack

  -----------------------------------------------------------------------
  Layer                   Choice                  Why
  ----------------------- ----------------------- -----------------------
  Language                Python 3.11+            Data work and simple
                                                  implementation

  Data handling           pandas                  Deduplication, grouping
                                                  and aggregation

  LLM provider            Replicate               Direct SDK/API
                                                  integration without
                                                  unnecessary frameworks

  LLM model               `openai/gpt-5-nano`     Fast, cost-efficient
                                                  constrained prose
                                                  generation

  LLM SDK                 `replicate`             Official Python client

  Config/specs            YAML + Markdown prompt  Makes section-specific
                          files                   instructions explicit
                                                  and inspectable

  Rendering               Jinja2 → Markdown,      Separates generation
                          optionally HTML/PDF     from presentation

  Human review            CLI/JSON approve-flag   Sufficient for the
                          step                    challenge

  Storage                 Flat files / SQLite if  No infrastructure
                          needed                  required
  -----------------------------------------------------------------------

Avoid LangChain/LangGraph agents, vector DB/RAG and multi-agent
orchestration. The dataset is analyzed deterministically and only
compact evidence is passed to the model.

------------------------------------------------------------------------

# 3. Architecture --- Data Flow

``` text
┌─────────────────────┐
│   Bisoprolol .xlsx  │
└──────────┬──────────┘
           ↓
┌───────────────────────────────┐
│ 1. Ingest & Validate          │
│ - load / parse dates          │
│ - split paired multi-values   │
│ - dedupe case vs row level    │
│ - schema / sanity checks      │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 2. Deterministic Analysis     │
│    Python/pandas — NO LLM     │
│ - totals / seriousness       │
│ - demographics               │
│ - reactions                  │
│ - outcomes                   │
│ - trends                     │
│ → analysis_results.json      │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 3. Human Checkpoint A         │
│ Approve / flag analysis       │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 4. Report Configuration       │
│ - section definitions         │
│ - allowed evidence keys       │
│ - generation instruction      │
│ - generation mode             │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 5. Section Context Builder    │
│ Pull ONLY configured keys     │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 6. LLM Section Generator      │
│ Replicate / GPT-5 Nano        │
│ one small call per section    │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 7. Validation                 │
│ numeric + unsupported claims  │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 8. Human Checkpoint B         │
│ approve / flag each section   │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 9. Report Renderer            │
│ approved prose + Case Index   │
└──────────────┬────────────────┘
               ↓
       report_output.md/.html/.pdf
```

The Case Index bypasses the LLM and is generated directly from
structured data.

------------------------------------------------------------------------

# 4. Repository / File Layout

``` text
genar-challenge/
├── src/
│   ├── ingest.py
│   ├── analyze.py
│   ├── context_builder.py
│   ├── generate.py
│   ├── review.py
│   ├── render.py
│   └── config/
│       ├── report_types/
│       │   └── pader.yaml
│       └── prompts/
│           ├── system_base.md
│           ├── reporting_period.md
│           ├── narrative_summary.md
│           ├── case_summary.md
│           ├── reaction_analysis.md
│           ├── serious_cases.md
│           ├── trends.md
│           └── history_of_actions.md
├── data/
├── output/
│   ├── analysis_results.json
│   └── report_output.md
├── prompts/
├── version1/
├── architecture.md
├── README.md
├── requirements.txt
└── .env.example
```

------------------------------------------------------------------------

# 5. Section → Required Evidence Mapping

The conceptual content of `config/report_types/pader.yaml` is:

  -----------------------------------------------------------------------
  Section                             Analysis keys it may see
  ----------------------------------- -----------------------------------
  Reporting Period                    `product_name`,
                                      `reporting_period_start`,
                                      `reporting_period_end`,
                                      `report_type`, `application_number`

  Narrative Summary and Analysis      `total_cases`, `serious_cases`,
                                      `non_serious_cases`,
                                      `alert_case_count`,
                                      `top_reactions`,
                                      `top_serious_reactions`,
                                      `age_breakdown`, `sex_breakdown`,
                                      `country_breakdown`,
                                      `outcome_breakdown`

  Summary Analysis of Cases           `total_cases`,
                                      `new_cases_in_period`,
                                      `serious_cases`,
                                      `non_serious_cases`,
                                      `age_breakdown`, `sex_breakdown`,
                                      `country_breakdown`,
                                      `reaction_breakdown`,
                                      `seriousness_breakdown`,
                                      `outcome_breakdown`

  Reaction/Adverse Event Analysis     `top_reactions`,
                                      `top_serious_reactions`,
                                      `reactions_by_age_group`,
                                      `reactions_by_sex`,
                                      `reactions_over_time`,
                                      `soc_available`

  Serious Cases / 15-Day Alerts       `alert_case_count`,
                                      `alert_cases_table`,
                                      `expectedness_available`

  Trends and Important Observations   `monthly_case_counts`,
                                      `monthly_top_reaction_counts`,
                                      `country_trend`,
                                      `seriousness_trend`

  History of Actions                  `actions_provided`

  Case Index/Listing                  Full per-case table; rendered
                                      directly
  -----------------------------------------------------------------------

Each section receives only its own configured evidence. It receives
neither the raw dataframe nor other sections' data.

------------------------------------------------------------------------

# 6. Version 1 --- Configurable Instructions

## 6.1 Configuration Schema

Create:

``` text
src/config/report_types/pader.yaml
```

Example:

``` yaml
report_type: pader
version: "1.0"

generation:
  provider: replicate
  model: openai/gpt-5-nano
  reasoning_effort: minimal
  verbosity: low
  max_completion_tokens: 1200

sections:
  - id: reporting_period
    title: Reporting Period
    mode: llm
    evidence:
      - product_name
      - reporting_period_start
      - reporting_period_end
      - report_type
      - application_number
    instruction_file: prompts/reporting_period.md

  - id: narrative_summary
    title: Narrative Summary and Analysis
    mode: llm
    evidence:
      - total_cases
      - serious_cases
      - non_serious_cases
      - alert_case_count
      - top_reactions
      - top_serious_reactions
      - age_breakdown
      - sex_breakdown
      - country_breakdown
      - outcome_breakdown
    instruction_file: prompts/narrative_summary.md

  - id: case_summary
    title: Summary Analysis of Cases
    mode: llm
    evidence:
      - total_cases
      - new_cases_in_period
      - serious_cases
      - non_serious_cases
      - age_breakdown
      - sex_breakdown
      - country_breakdown
      - reaction_breakdown
      - seriousness_breakdown
      - outcome_breakdown
    instruction_file: prompts/case_summary.md

  - id: reaction_analysis
    title: Reaction/Adverse Event Analysis
    mode: llm
    evidence:
      - top_reactions
      - top_serious_reactions
      - reactions_by_age_group
      - reactions_by_sex
      - reactions_over_time
      - soc_available
    instruction_file: prompts/reaction_analysis.md

  - id: serious_cases
    title: Serious Cases / 15-Day Alerts
    mode: llm
    evidence:
      - alert_case_count
      - alert_cases_table
      - expectedness_available
    instruction_file: prompts/serious_cases.md

  - id: trends
    title: Trends and Important Observations
    mode: llm
    evidence:
      - monthly_case_counts
      - monthly_top_reaction_counts
      - country_trend
      - seriousness_trend
    instruction_file: prompts/trends.md

  - id: history_of_actions
    title: History of Actions
    mode: llm
    evidence:
      - actions_provided
    instruction_file: prompts/history_of_actions.md

  - id: case_index
    title: Case Index/Listing
    mode: deterministic
```

The engine must load this configuration rather than hard-code
section-specific prompt logic.

## 6.2 Anti-Pattern to Remove

Do not build:

``` python
if section == "narrative_summary":
    prompt = "..."
elif section == "reaction_analysis":
    prompt = "..."
```

Instead:

``` python
instruction = load_instruction(section["instruction_file"])
evidence = build_section_context(section, analysis_results)
```

This is the core Version 1 change.

------------------------------------------------------------------------

# 7. Prompt Design --- Concrete Templates

## 7.1 Shared System Prompt

``` text
You are drafting one section of a regulatory PADER safety report.

Rules:
- Use ONLY the figures given in "Approved analysis results."
- Never invent, estimate, or recompute a number.
- Distinguish observed data from derived analysis from interpretation.
- Do not state a safety conclusion unless it is explicitly present in the input.
- If a field is marked unavailable, say so plainly instead of omitting or inferring it.
- Tone: neutral, regulatory, third person.
- No marketing language.
- No unsupported speculation.
- Output plain prose for this section only.
- Do not restate other sections.
```

## 7.2 Narrative Summary Instruction

``` text
Section: Narrative Summary and Analysis

Summarize only the figures provided in the approved evidence packet.
Describe visible patterns in the supplied breakdowns, but do not convert
observations into medical conclusions.
Do not call anything a "signal", "concern", or confirmed causal relationship
unless the supplied evidence explicitly supports that framing.
Target length: 150-250 words.
```

## 7.3 Reporting Period Instruction

``` text
Section: Reporting Period

State the supplied product, application identifier if present, report type,
reporting period and data cutoff.
Do not add regulatory or product information that is not supplied.
Target length: one short paragraph.
```

The other six generated sections should use equivalent section-specific
instruction files.

------------------------------------------------------------------------

# 8. Context Builder

`context_builder.py` should accept a section configuration and analysis
result.

``` python
def build_section_context(section_config, analysis_results):
    packet = {}

    for key in section_config.get("evidence", []):
        if key not in analysis_results:
            raise KeyError(f"Missing analysis key: {key}")

        packet[key] = analysis_results[key]

    return packet
```

The function must not accept or forward the raw dataframe.

------------------------------------------------------------------------

# 9. Prompt Assembly

``` python
import json


def build_prompt(report_type, section_config, evidence, instruction):
    return f"""
Report type: {report_type}

Section: {section_config["title"]}

Approved analysis results:
{json.dumps(evidence, indent=2, ensure_ascii=False)}

Instructions:
{instruction}

Write only the requested section.
Use only the supplied evidence.
"""
```

------------------------------------------------------------------------

# 10. Replicate Migration

## 10.1 Requirements

Remove:

``` text
anthropic
```

Add:

``` text
replicate
```

Keep the existing core dependencies such as:

``` text
pandas
openpyxl
pyyaml
jinja2
python-dotenv
```

plus existing rendering and testing dependencies.

## 10.2 Environment

`.env.example`:

``` text
REPLICATE_API_TOKEN=your_token_here
```

Load it with `python-dotenv` and never commit the real token.

## 10.3 Replicate Generator

``` python
import replicate

MODEL = "openai/gpt-5-nano"


class ReplicateGenerator:
    def __init__(self, model: str = MODEL):
        self.model = model

    def generate(
        self,
        system_prompt: str,
        prompt: str,
        *,
        max_completion_tokens: int = 1200,
    ) -> str:
        output = replicate.run(
            self.model,
            input={
                "prompt": prompt,
                "system_prompt": system_prompt,
                "reasoning_effort": "minimal",
                "verbosity": "low",
                "max_completion_tokens": max_completion_tokens,
            },
        )

        if isinstance(output, list):
            return "".join(str(item) for item in output).strip()

        return str(output).strip()
```

Replicate's current model schema documents `prompt`, `system_prompt`,
`reasoning_effort`, `verbosity`, and `max_completion_tokens`, with a
`string[]` output type.

If `messages` is supplied, it takes precedence over `prompt` and
`system_prompt`, so the first implementation should use the simpler
`prompt` + `system_prompt` pattern.

------------------------------------------------------------------------

# 11. Generate Flow

``` python
def generate_report_sections(config, analysis_results):
    generator = ReplicateGenerator(
        model=config["generation"]["model"]
    )

    generated = []

    for section in config["sections"]:
        if section["mode"] == "deterministic":
            content = render_deterministic_section(
                section,
                analysis_results,
            )
        else:
            evidence = build_section_context(
                section,
                analysis_results,
            )

            instruction = load_instruction(
                section["instruction_file"]
            )

            prompt = build_prompt(
                config["report_type"],
                section,
                evidence,
                instruction,
            )

            content = generator.generate(
                system_prompt=load_system_prompt(),
                prompt=prompt,
                max_completion_tokens=config["generation"][
                    "max_completion_tokens"
                ],
            )

        generated.append({
            "section_id": section["id"],
            "title": section["title"],
            "content": content,
        })

    return generated
```

------------------------------------------------------------------------

# 12. Validation Layer

Add:

``` text
src/validate.py
```

## 12.1 Numeric Consistency

``` text
generated numbers
       ↓
compare with allowed evidence
       ↓
flag unsupported values
```

This is a screening mechanism, not a mathematical proof of factual
correctness.

## 12.2 Unsupported Claim Check

Flag language such as:

``` text
no safety concern
signal
confirmed
causal
caused by
```

when the evidence does not establish that conclusion.

## 12.3 Completeness

Check that:

-   every required section was generated;
-   no section is empty;
-   review status exists for every generated section.

------------------------------------------------------------------------

# 13. Human Review

Retain two review points.

### Checkpoint A

Reviewer approves or flags `analysis_results.json` before it becomes
approved evidence.

### Checkpoint B

Reviewer approves or flags each generated section before it becomes
final report content.

A minimal CLI can expose:

``` text
[1] Approve
[2] Flag
[3] Regenerate
```

------------------------------------------------------------------------

# 14. Case Index

The Case Index remains deterministic.

``` python
if section["mode"] == "deterministic":
    render_case_index(analysis_results)
```

No LLM call is made for this section.

------------------------------------------------------------------------

# 15. Evaluation Approach

For approximately 1,000 generated reports:

## Metric 1 --- Numeric consistency

Percentage of generated numerical claims supported by the section's
approved evidence packet.

## Metric 2 --- Unsupported-claim rate

Percentage of generated sections containing flagged conclusion language
without corresponding evidence.

## Metric 3 --- Completeness rate

Percentage of reports where every required section was generated and
approved.

## Metric 4 --- Human rejection rate

Percentage of generated sections rejected during sampled review.

## Metric 5 --- Generation failure rate

Percentage of model calls that fail or return empty output.

Automated checks should prioritize human review rather than attempting
to eliminate human review entirely.

------------------------------------------------------------------------

# 16. Testing

Minimum tests:

``` text
test_config_loads
test_section_ids_unique
test_all_evidence_keys_exist
test_analysis_outputs_are_json_serializable
test_context_contains_only_declared_keys
test_missing_evidence_key_fails
test_replicate_output_list_is_joined
test_empty_generation_is_rejected
test_case_index_does_not_call_llm
test_numeric_consistency_flags_unknown_number
```

The most important context-engineering test is:

``` text
test_context_contains_only_declared_keys
```

because it directly verifies that the model receives only the
information assigned to its section.

------------------------------------------------------------------------

# 17. Task Breakdown / Build Order

1.  **Freeze Version 0 behavior** --- do not change deterministic
    analysis while migrating the model.
2.  **Extract generation boundary** --- keep provider-specific logic
    inside `generate.py`.
3.  **Replace Anthropic** --- remove the Anthropic SDK and response
    parsing; add Replicate.
4.  **Add configuration** --- create `pader.yaml` and move section
    instructions out of Python.
5.  **Add prompt files** --- create the shared system prompt and seven
    section-specific instruction files.
6.  **Make context assembly configuration-driven** --- read the
    `evidence` list from the section spec.
7.  **Add validation** --- numeric consistency and unsupported-claim
    checks.
8.  **Keep human review** --- analysis and generated sections must
    remain approvable/flagable.
9.  **Run tests** --- `pytest -q`.
10. **Run end-to-end** --- `python -m src.pipeline --report-type pader`.

------------------------------------------------------------------------

# 18. Version 1 Acceptance Test

The decisive test is to change a section's instruction in YAML/Markdown
without changing `generate.py`.

For example, change:

``` text
Target length: 150-250 words.
```

to:

``` text
Target length: 100-150 words.
```

Then regenerate the same report.

If the generation engine requires a code change to honor the new
instruction, the configurable-instructions implementation is incomplete.

A second test is to change the allowed evidence keys for a section and
verify that the model receives only the new keys.

------------------------------------------------------------------------

# 19. Known Constraints

-   No SOC field → never infer SOC.
-   No product label/CCDS → expectedness is out of scope.
-   No history-of-actions data → explicitly report that none was
    supplied.
-   Row-level and case-level counts differ → be explicit about the
    counting level.
-   Reaction/outcome fields are positionally paired comma-packed values
    → split and re-pair.
-   Dataset must not be included in the final submission zip.
-   Raw dataset must never be sent to the LLM.

------------------------------------------------------------------------

# 20. Final Architecture

``` text
                    ┌───────────────────┐
                    │     Bisoprolol    │
                    │       XLSX        │
                    └─────────┬─────────┘
                              ↓
                    ┌───────────────────┐
                    │    ingest.py      │
                    └─────────┬─────────┘
                              ↓
                    ┌───────────────────┐
                    │    analyze.py     │
                    │  Python = truth   │
                    └─────────┬─────────┘
                              ↓
              ┌───────────────────────────────┐
              │          pader.yaml           │
              │                               │
              │ section definitions           │
              │ evidence keys                 │
              │ instruction files             │
              │ model configuration           │
              └──────────────┬────────────────┘
                             ↓
                    ┌───────────────────┐
                    │ context_builder   │
                    │ scoped evidence   │
                    └─────────┬─────────┘
                              ↓
                    ┌───────────────────┐
                    │ Replicate         │
                    │ GPT-5 Nano        │
                    └─────────┬─────────┘
                              ↓
                    ┌───────────────────┐
                    │   validate.py     │
                    └─────────┬─────────┘
                              ↓
                    ┌───────────────────┐
                    │   human review    │
                    └─────────┬─────────┘
                              ↓
                    ┌───────────────────┐
                    │    render.py      │
                    └─────────┬─────────┘
                              ↓
                    ┌───────────────────┐
                    │   PADER report    │
                    └───────────────────┘

Case Index bypasses the LLM.
```

------------------------------------------------------------------------

# 21. Version 1 Summary

``` text
VERSION 0
---------
Hard-coded section behavior
Anthropic API
Scoped evidence
Deterministic analysis
Human review

VERSION 1
---------
Configurable section instructions
Configurable evidence declarations
Replicate provider
openai/gpt-5-nano
Validation layer
Same deterministic analysis boundary
Same human review boundary
```

The core principle remains:

> Python computes. Configuration decides what each section is allowed to
> see and how it should be written. The LLM phrases the supplied
> evidence. Validation and human review decide whether generated text
> can become final.
