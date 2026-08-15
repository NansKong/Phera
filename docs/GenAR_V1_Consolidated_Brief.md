# GenAR AI Engineering Challenge --- Consolidated Brief

## Version 1 Update: Configurable Instructions + Replicate `openai/gpt-5-nano`

**Updated:** August 2026\
**Baseline:** GenAR Version 0\
**Selected Version 1 feature:** Configurable instructions\
**LLM provider:** Replicate\
**Model:** `openai/gpt-5-nano`

------------------------------------------------------------------------

## 1. What This Challenge Is

Build a working AI system that turns a raw pile of adverse-event case
data (an ICSR line-listing for **Bisoprolol**) into a short, structured,
evidence-backed safety report --- a simplified PADER (Periodic Adverse
Drug Experience Report).

The challenge is primarily about:

-   understanding what an LLM is and is not good for in this pipeline;
-   ensuring every number in the final report traces to deterministic
    code rather than model arithmetic;
-   providing the right information at the right step;
-   using clear, section-specific prompts;
-   keeping the architecture simple rather than adding agents/frameworks
    unnecessarily;
-   grounding generated claims in the data;
-   explaining how the system would be evaluated at scale;
-   keeping the design extensible beyond PADER.

**Governing rule:** the report can only say what the data supports. It
must never state a conclusion such as "no safety concerns identified"
unless something in the system actually establishes that conclusion.

------------------------------------------------------------------------

## 2. Inputs Supplied

  ----------------------------------------------------------------------------
  Input                                    Purpose
  ---------------------------------------- -----------------------------------
  `Bisoprolol_icsr_sample_1068rows.xlsx` / Safety dataset --- 1,068 rows,
  `.csv`                                   1,024 unique cases, one-year
                                           reporting period

  `PADER_Starter_Guide.pdf`                Domain primer and dataset-specific
                                           requirements

  Sample PADER PDF                         Shape/tone reference only

  `GenAR_-_AI_Engineering_Challenge.pdf`   Challenge brief

  `Submission_Guide.pdf`                   Packaging and README requirements
  ----------------------------------------------------------------------------

------------------------------------------------------------------------

## 3. Dataset --- Verified Structure

Direct inspection of the supplied XLSX established:

-   1,068 total rows;
-   1,024 unique `safetyreportid` values;
-   67 columns;
-   reporting period: **2024-12-27 → 2025-12-26**;
-   row-level seriousness: **1,067 serious / 1 not serious**;
-   case-level seriousness: **1,023 of 1,024 cases serious (99.9%)**;
-   patient sex: **520 female / 518 male / 30 blank**;
-   reactions are MedDRA PT values and no SOC field exists;
-   reaction and outcome fields are comma-packed and positionally
    paired;
-   no product label/CCDS is supplied, so expectedness is out of scope;
-   no history-of-actions data is supplied;
-   `occurcountry` and `primarysource_reportercountry` can differ, so
    one primary country field must be selected and documented.

The implementation must explicitly distinguish row-level and case-level
counts.

------------------------------------------------------------------------

## 4. Required Report Sections

The report covers eight sections:

1.  **Reporting Period** --- product, application ID if supplied,
    reporting period, report type, data cutoff.
2.  **Narrative Summary and Analysis** --- total cases, seriousness,
    alerts if present, major/serious reactions, patient characteristics,
    outcomes, geography and observable patterns.
3.  **Summary Analysis of Cases** --- total/new/serious/non-serious case
    volume and patient/case characteristics.
4.  **Reaction/Adverse Event Analysis** --- most frequent reactions,
    serious reactions, age, sex and time; SOC only if actually
    available.
5.  **Serious Cases / 15-Day Alerts** --- count, seriousness, reaction,
    outcome, dates and case IDs; narrative only where present.
6.  **Trends and Important Observations** --- volume changes, reaction
    changes and country/seriousness/outcome shifts, stated as
    observations rather than unsupported signals.
7.  **History of Actions** --- labeling changes, communications, studies
    and risk-minimization actions. This dataset supplies none, so that
    must be stated.
8.  **Case Index/Listing** --- case ID, reaction, seriousness, reporting
    date, country and outcome, rendered directly from data.

------------------------------------------------------------------------

## 5. Worked Grounding Pattern

The core design remains:

``` text
Raw row
  ↓
Deterministic Python analysis
  ↓
Approved analysis result
  ↓
Section-specific evidence packet
  ↓
LLM phrasing only
  ↓
Human review
  ↓
Report
```

Example deterministic values from the challenge brief:

``` text
total_cases: 1024
serious_cases: 1023
serious_pct: 99.9%
non_serious_cases: 1

top_reactions:
  Acute kidney injury: 22
  Drug ineffective: 12
  Cerebral haemorrhage: 7
```

The LLM may phrase these supplied values but must not calculate them.

------------------------------------------------------------------------

# 6. Version 0 --- Required Scope

The Version 0 architecture is:

``` text
Safety data
    ↓
Ingest + validate
    ↓
Deterministic analysis
    ↓
Optional human analysis approval
    ↓
Section context assembly
    ↓
LLM generation
    ↓
Human section approval
    ↓
Report rendering
```

Minimum analyses are deterministic/Python:

-   total cases;
-   serious vs. non-serious;
-   age group;
-   sex;
-   country;
-   most common reactions;
-   most common serious reactions;
-   outcomes;
-   trends over time.

The LLM is used only to phrase supplied evidence in regulatory-neutral
prose.

------------------------------------------------------------------------

# 7. Version 1 --- Selected Feature: Configurable Instructions

The selected Version 1 feature is **Configurable instructions**.

The challenge defines this as allowing different report types/sections
to carry their own generation rules instead of one global prompt.

### Version 0

``` text
One global prompt
      ↓
section-specific data
      ↓
LLM
```

### Version 1

``` text
Report configuration
      ↓
Section specification
  ├── section name
  ├── allowed evidence
  ├── generation instruction
  ├── tone/length rules
  └── generation mode
      ↓
Scoped context builder
      ↓
LLM
```

This makes prompt behavior explicit, inspectable and reusable.

## 7.1 Configuration Structure

Recommended layout:

``` text
src/
└── config/
    ├── report_types/
    │   └── pader.yaml
    └── prompts/
        ├── system_base.md
        └── section_*.md
```

Example `pader.yaml`:

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

The exact field names must match the implementation's
`analysis_results.json`.

## 7.2 Why This Is the Selected Feature

This feature directly addresses the challenge's generalization
requirement without adding unnecessary infrastructure.

It proves that:

-   section behavior is not hard-coded into `generate.py`;
-   evidence selection is configuration-driven;
-   prompts vary by section;
-   analyses remain reusable independently of wording;
-   another report type could later be added primarily through
    configuration rather than new generation code paths.

A second report type can be added later as a demonstration, but it is
**not required for this Version 1 selection**.

------------------------------------------------------------------------

# 8. Section → Required Evidence Mapping

Each section sees only the evidence it declares.

  -----------------------------------------------------------------------
  Section                             Allowed evidence
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

No raw dataframe or unrelated section data is passed to the model.

------------------------------------------------------------------------

# 9. Prompt Design

## Shared system instruction

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

## Example section instruction --- Narrative Summary

``` text
Section: Narrative Summary and Analysis

Summarize only the figures provided in the approved evidence packet.
Describe visible patterns in the supplied breakdowns, but do not
convert observations into medical conclusions.
Do not call anything a "signal", "concern", or confirmed causal
relationship unless the supplied evidence explicitly supports that framing.
Target length: 150-250 words.
```

The remaining sections receive their own instruction files. The
important Version 1 rule is that those instructions live outside the
generation engine.

------------------------------------------------------------------------

# 10. Replicate Migration

Version 0 used the Anthropic API. Version 1 replaces it with Replicate
and the model:

``` text
openai/gpt-5-nano
```

Authentication:

``` text
REPLICATE_API_TOKEN
```

Dependency:

``` text
replicate
```

Remove the Anthropic SDK and Anthropic-specific response parsing.

## 10.1 Model Configuration

The selected Replicate model supports:

-   `prompt`;
-   `messages`;
-   `system_prompt`;
-   `reasoning_effort`;
-   `verbosity`;
-   `max_completion_tokens`.

The documented output type is `string[]`.

Recommended defaults:

``` yaml
generation:
  provider: replicate
  model: openai/gpt-5-nano
  reasoning_effort: minimal
  verbosity: low
  max_completion_tokens: 1200
```

For this simple single-turn section-generation task, use `prompt` +
`system_prompt` rather than `messages`.

## 10.2 Replicate Generator

``` python
import replicate

MODEL = "openai/gpt-5-nano"


def generate_section(
    system_prompt: str,
    prompt: str,
    max_completion_tokens: int = 1200,
) -> str:
    output = replicate.run(
        MODEL,
        input={
            "prompt": prompt,
            "system_prompt": system_prompt,
            "reasoning_effort": "minimal",
            "verbosity": "low",
            "max_completion_tokens": max_completion_tokens,
        },
    )

    if isinstance(output, list):
        return "".join(str(chunk) for chunk in output).strip()

    return str(output).strip()
```

The output normalization step is required because the model returns a
string array rather than a single text field.

------------------------------------------------------------------------

# 11. Why GPT-5 Nano Fits This Pipeline

The model is not being asked to perform the pharmacovigilance analysis.

The intended task is:

``` text
precomputed evidence → controlled regulatory prose
```

That makes a fast, cost-efficient model a defensible choice for this
constrained generation role.

The correct response to a smaller model is not to provide more raw
context. The system should instead use:

``` text
small evidence packet
        +
clear instructions
        +
deterministic validation
        +
human review
```

------------------------------------------------------------------------

# 12. Human Review

Retain both review points:

``` text
Analysis results
      ↓
Human Checkpoint A
      ↓
Scoped context
      ↓
LLM generation
      ↓
Validation
      ↓
Human Checkpoint B
      ↓
Final report
```

A successful API call does not make a section final.

------------------------------------------------------------------------

# 13. Grounding / Traceability

At minimum, every generated section should retain:

-   report type;
-   section ID;
-   model;
-   generation settings;
-   allowed evidence keys;
-   exact evidence packet;
-   generated text;
-   validation status.

Example:

``` json
{
  "report_type": "pader",
  "section_id": "narrative_summary",
  "model": "openai/gpt-5-nano",
  "evidence_keys": [
    "total_cases",
    "serious_cases",
    "top_reactions"
  ],
  "status": "generated"
}
```

Sentence-level evidence tracing remains a possible future extension, but
it is not the selected Version 1 feature.

------------------------------------------------------------------------

# 14. Evaluation at Scale

For approximately 1,000 generated reports, use:

1.  **Numeric consistency** --- parse generated numbers and compare them
    with the section's approved evidence packet.
2.  **Unsupported-claim check** --- flag conclusion language such as "no
    safety concern", "signal", "confirmed", or "causal" when the
    evidence does not establish it.
3.  **Completeness check** --- verify every required section was
    generated and approved.
4.  **Spot-check sampling** --- human reviewers inspect a random
    percentage of sections, concentrating on automated flags.

------------------------------------------------------------------------

# 15. Known Constraints

-   No SOC field → never invent SOC groupings.
-   No product label/CCDS → expectedness is out of scope.
-   No history-of-actions data → explicitly state that none was
    supplied.
-   Row-level and case-level counts differ → state the counting level.
-   Reaction/outcome fields are positionally paired comma-packed values
    → split and re-pair them.
-   Dataset must not be included in the submission zip.
-   Raw dataset must never be sent to the LLM.

------------------------------------------------------------------------

# 16. Updated Repository Structure

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

# 17. Requirements Changes

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

`.env.example`:

``` text
REPLICATE_API_TOKEN=your_token_here
```

Never commit the real token.

------------------------------------------------------------------------

# 18. Version 1 Definition of Done

-   [ ] Anthropic dependency removed.
-   [ ] Replicate dependency added.
-   [ ] `REPLICATE_API_TOKEN` used for authentication.
-   [ ] `openai/gpt-5-nano` configured.
-   [ ] Replicate output normalized correctly.
-   [ ] Section instructions moved out of `generate.py`.
-   [ ] Each section declares its own evidence keys.
-   [ ] `context_builder.py` reads evidence requirements from
    configuration.
-   [ ] Shared grounding rules remain centralized.
-   [ ] Case Index remains deterministic.
-   [ ] Python remains responsible for all calculations.
-   [ ] Human review remains in the workflow.
-   [ ] Generation metadata retains evidence scope.
-   [ ] Numeric consistency validation is implemented.
-   [ ] README documents the configurable-instruction architecture.
-   [ ] The system remains capable of adding another report type
    primarily through configuration.

------------------------------------------------------------------------

# 19. Final Version 0 → Version 1 Architecture

### Version 0

``` text
XLSX
 ↓
Ingest
 ↓
Deterministic Analysis
 ↓
Scoped Context
 ↓
Anthropic
 ↓
Human Review
 ↓
Renderer
```

### Version 1

``` text
XLSX
 ↓
Ingest
 ↓
Deterministic Analysis
 ↓
Report Configuration
 ├── section definitions
 ├── evidence keys
 └── generation instructions
 ↓
Scoped Context
 ↓
Replicate / openai/gpt-5-nano
 ↓
Validation
 ↓
Human Review
 ↓
Renderer
```

The important architectural change is not merely the model-provider
swap. It is:

``` text
Hard-coded generation behavior
            ↓
Configuration-driven instructions
```

while keeping deterministic analysis and grounding boundaries intact.
