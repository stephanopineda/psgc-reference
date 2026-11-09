# ETL Architecture and Processing Governance

## 1. Purpose

This document defines the architecture and governance of the PSGC reference
data ingestion pipeline.

The ETL system converts PSA-published PSGC workbooks into validated,
normalized, versioned data suitable for historical analysis and API publication.

The system must detect source variations and data-quality problems without
assuming that every unexpected value is an error in the source.

The original source is immutable. Processing rules, transformations,
interpretations, and exclusions are controlled by the project maintainer and
must be reproducible and documented.

## 2. Governing principles

1. **Source immutability:** Never edit an original PSA workbook to accommodate
   the ETL.
2. **Source fidelity:** Preserve original values and their source locations.
3. **Deterministic processing:** Given the same source, ETL version, rule
   versions, configuration, and approved decisions, processing must produce
   the same result.
4. **Explicit interpretation:** Do not silently infer geographic identity,
   hierarchy, lifecycle status, or missing source values.
5. **Human authority:** Automated algorithms and AI may identify and explain
   findings, but cannot approve changes to published data.
6. **Traceability:** Every transformation, exclusion, and identity decision
   must be traceable to its source and governing rule or approval.
7. **Separation of concerns:** Source acquisition, extraction, validation,
   normalization, hierarchy resolution, identity resolution, comparison,
   loading, and publication must remain distinct processing stages.
8. **Reproducibility:** A previously processed release must be reproducible
   from its source artifacts and recorded processing configuration.

## 3. Processing architecture

The pipeline consists of the following logical stages.

### 3.1 Source acquisition

Responsibilities:

- Obtain the original PSA workbook.
- Preserve the original file without modification.
- Record its filename, source location, acquisition timestamp, and SHA-256
  hash.
- Record available PSA publication metadata.
- Assign an internal source artifact identifier.

The file hash identifies the exact source artifact. A filename or publication
date alone is not sufficient to establish that two files are identical.

### 3.2 Workbook inspection

Inspect the workbook before extracting records.

Detect and report:

- Worksheet names and dimensions.
- Required and unexpected worksheets.
- Header names, positions, and blank headers.
- Missing, renamed, reordered, or additional columns.
- Cell data types and number formats.
- Unexpected formulas, merged cells, or structural changes where relevant.
- Metadata and publication information.

Workbook inspection must distinguish a structural difference from a data
defect. An unexpected column may represent a legitimate PSA publication
change and should initially be reported for review.

### 3.3 Extraction

Extract source records while retaining:

- Source artifact identifier.
- Worksheet name.
- Source row number.
- Original column names and positions.
- Original cell values and, where relevant, cell data types and number formats.
- A stable internal source-record identifier for the import.

Extraction must not silently discard unrecognized columns or source records.

#### Formula and cached-value extraction

Excel formula cells require preservation of both the formula expression and
the cached result, where available.

The extractor must perform complementary workbook reads:

- Load with `data_only=False` to obtain formula expressions and original
  cell values.
- Load with `data_only=True` to obtain cached results for formula cells.

The two reads must be associated using the same source artifact, worksheet,
and cell coordinate.

For a formula cell, retain:

- Original formula expression.
- Cached result, if available.
- Original cell coordinate.
- Original cell data type and relevant number format.
- Extracted source-record and field association.

The ETL must not execute or independently recalculate formulas during
extraction.

If a formula has no usable cached result, create a review finding. Do not
substitute zero, calculate a replacement, or silently use a value from
another release.

The cached result is the value saved by the source workbook. Its presence
does not establish that the ETL independently verified the formula.

### 3.4 Validation

Run deterministic validation rules against the extracted records.

Examples include:

- Required field checks.
- PSGC format checks using the applicable release profile.
- Duplicate PSGC checks within a release.
- Geographic-level checks.
- Numeric representation checks.
- Correspondence-code checks.
- Population representation checks.
- Hierarchy consistency checks.
- Release-to-release anomaly detection.

Every finding must identify the affected source artifact and record or
workbook location whenever possible.

Validation findings must have a stable rule identifier, rule version,
severity, finding code, explanation, and relevant source values.

### 3.5 Normalization

Convert source values into defined internal representations without
overwriting the extracted source values.

Examples:

- Convert a valid numeric correspondence-code cell to a decimal-free string.
- Normalize whitespace according to an explicit field rule.
- Convert valid population values to the chosen integer representation.
- Normalize a literal population placeholder `-` to `NULL` while retaining
  the original source value.
- Map known source geographic-level labels to internal enumerations while
  retaining the original label.

#### Population normalization

Population values must follow the source-data contract.

- Accept valid whole-number values.
- Preserve the original source value and cell representation.
- For formula cells, use the cached result obtained during extraction.
- Convert a valid cached whole-number result to the normalized integer
  representation.
- Normalize a literal `-` to `NULL`, not zero.
- Do not round fractional values.
- Do not independently calculate or recalculate source formulas.
- Do not invent a replacement when a cached result is unavailable.

Population annotations must remain separate from the normalized population
value. Numbered references may be resolved against release-specific Notes
data, but their original source values must remain preserved.

A normalization rule must define its accepted inputs, output, rejected
inputs, and tests.

Normalization must not invent missing source values or apply arbitrary
padding, truncation, or code derivation.

### 3.6 Hierarchy resolution

Resolve parent-child relationships using explicit, release-aware rules.

The pipeline must:

- Keep source hierarchy evidence separate from resolved relationships.
- Validate that parent references belong to the same release.
- Preserve unresolved parent relationships as findings.
- Avoid deriving hierarchy solely from code prefixes, row order, or proximity.
- Record the rule and evidence used to establish each resolved relationship.

### 3.7 Identity resolution

Generate candidate matches across releases and apply approved identity rules.

Candidate generation and identity decisions are separate operations.

The identity-resolution contract defines candidate outcomes, evidence,
decisions, assignment states, and cardinality constraints.

The ETL must not automatically establish a new identity merely because no
candidate was found.

### 3.8 Release comparison

Compare the current source snapshot with prior releases.

Identify:

- Added and removed source records.
- Changed PSGC codes.
- Changed names and geographic levels.
- Changed correspondence codes.
- Changed population and classification attributes.
- Potential identity continuity.
- Potential splits, mergers, replacements, and parent changes.

A difference is an observation, not automatically an explanation. The system
must not label a record abolished, transferred, or newly established without
sufficient evidence.

### 3.9 Loading

Load approved source snapshots, normalized records, findings, identity
assignments, and resolved relationships into the database.

Loading must be:

- Transactional where supported.
- Idempotent for the same source and processing configuration.
- Traceable to an import run.
- Separate from public API publication.
- Safe to retry after a failed import.

A successful database load does not itself make a release publicly available.

### 3.10 Publication

Only a release that passes the release-management requirements may become
available through the public API.

The API must consume approved release data, not intermediate ETL state.

## 4. Source, normalized, and interpreted data

The data model must distinguish at least these layers:

| Layer | Meaning |
|---|---|
| Source artifact | Original, unmodified workbook |
| Extracted source record | Values and locations as read from the workbook |
| Normalized record | Deterministically converted values |
| Resolved data | Approved identity and hierarchy interpretations |
| Published projection | Data made available through the API |

A normalized or resolved value must never replace the corresponding source
value.

When a source value is excluded from a published projection, its original
value and exclusion decision must remain traceable internally.

## 5. Validation findings and anomaly detection

### 5.1 Deterministic rules

Validation rules must be implemented as explicit, version-controlled code or
configuration.

Each rule must define:

- Stable rule identifier.
- Rule version.
- Purpose and rationale.
- Inputs and applicable release profiles.
- Detection logic.
- Severity.
- Finding output.
- Whether the finding blocks promotion by default.
- Regression tests.

A rule must not silently change behavior between runs.

### 5.2 Finding categories

The initial finding categories are:

- `STRUCTURE`: workbook or worksheet structure differs from expectations.
- `FORMAT`: a source value has an unexpected representation.
- `MISSING_VALUE`: a required or expected value is absent.
- `DUPLICATE`: a value expected to be unique is repeated.
- `REFERENCE`: a parent or other reference cannot be resolved.
- `IDENTITY`: identity continuity is uncertain or conflicting.
- `HISTORICAL_CHANGE`: a difference between releases needs interpretation.
- `UNSUPPORTED_VALUE`: the ETL does not recognize a source value.
- `OTHER`: a finding not covered by the categories above.

These categories are internal classifications, not PSA classifications.

### 5.3 Detection versus disposition

A finding is an observation produced by a rule. It is not itself an approved
correction.

The system must keep separate:

1. Detection result.
2. Finding severity.
3. Maintainer review decision.
4. Approved processing rule or exception.
5. Reprocessing result.
6. Final release disposition.

A finding must not disappear merely because it was reviewed. Its disposition
and review history must remain auditable.

## 6. AI-assisted maintainer workflow

AI is an optional development and review assistant. It is not part of the
deterministic ETL execution path.

AI may assist with:

- Explaining validation findings.
- Comparing unexpected workbook structures.
- Identifying patterns across source records and releases.
- Suggesting possible mapping or normalization rules.
- Suggesting candidate identity matches for human review.
- Drafting code changes and regression tests.
- Explaining the possible impact of a proposed transformation or exclusion.
- Drafting release notes and data-quality summaries.

AI must not:

- Modify original source artifacts.
- Directly modify the production database.
- Approve its own proposed changes.
- Approve identity assignments or exclusions.
- Publish a release.
- Change processing rules without maintainer review.
- Treat an inferred value as an official PSA value.

AI-generated recommendations must be treated as untrusted proposals. The
maintainer must inspect the evidence, proposed implementation, tests, and
expected impact before accepting them.

AI use must not be required to rerun a previously approved import.

## 7. Maintainer decisions and approved rules

A maintainer may decide to:

- Update an extraction profile for a legitimate workbook structure change.
- Add or revise a normalization rule.
- Add a geographic-level or hierarchy mapping supported by evidence.
- Approve or reject an identity candidate.
- Exclude a record or field from a specific published projection.
- Retain a questionable value with a documented limitation.
- Defer a decision pending additional evidence.
- Reject a proposed solution.

Every decision affecting processed or published data must record:

- Decision identifier.
- Affected source artifact, release, record, and field where applicable.
- Finding or candidate that prompted the decision.
- Decision type and disposition.
- Original value and resulting treatment.
- Rationale and supporting evidence.
- Reviewer identity.
- Decision timestamp.
- Applicable ETL and rule versions.
- Tests or verification results.

A decision must have a defined scope. An exception for one record must not
silently become a global rule.

Approved reusable behavior belongs in version-controlled rules and tests.
Record-specific exceptions must remain explicitly scoped and auditable.

## 8. Transformations and exclusions

### 8.1 Transformations

A transformation creates a derived representation. It does not modify the
source artifact or erase the extracted source value.

Each transformation must identify:

- Input field and source value.
- Output field and derived value.
- Rule identifier and version.
- Reason for the transformation.
- Whether the transformation is lossless.
- Validation and test coverage.

### 8.2 Exclusions

Exclusion means withholding a source record or field from a defined
published projection. It does not mean deleting the original source data.

An exclusion must record:

- What is excluded.
- Its source location.
- The affected release and API projection.
- The reason and evidence.
- The maintainer approval.
- Whether the exclusion is temporary or intended to persist.
- Conditions for reconsideration.

Exclusions must be visible in internal import reports and summarized in the
public release-quality documentation where they affect published coverage.

The system must not describe an excluded record as nonexistent in the PSA
source.

### 8.3 No silent repairs

The ETL must not silently:

- Invent missing PSGC or correspondence codes.
- Change a source name to a preferred spelling.
- Assign a geographic level unsupported by the source or approved evidence.
- Guess parent relationships.
- Merge records based only on similar names.
- Convert an uncertain identity into an approved match.
- Remove a record solely to make validation pass.

## 9. Reproducibility and idempotency

An import run must identify:

- Source artifact hash.
- Source-data contract version.
- Identity-resolution contract version.
- ETL software version or commit.
- Extraction profile version.
- Validation rule-set version.
- Normalization rule-set version.
- Identity rule-set version.
- Approved decision-set version.
- Import configuration.

The same inputs and versions must produce the same deterministic outputs.

A changed rule or approved decision must create a distinguishable processing
run. It must not silently rewrite the audit history of an earlier run.

Repeated execution with the same inputs must not create duplicate release
records, entity versions, or relationships.

## 10. Testing strategy

The ETL must include:

- Unit tests for individual rules.
- Workbook fixture tests for extraction profiles.
- Regression tests for previously encountered source variations.
- Historical comparison tests.
- Identity-resolution tests.
- Hierarchy integrity tests.
- Idempotency tests.
- Integration tests for database loading.
- Tests proving that original source values remain unchanged.
- Tests proving that exclusions do not delete source records.
- Tests proving that AI is not required for deterministic processing.

Synthetic fixtures may be used in CI. Production release data must be
processed and reviewed through the maintainer-controlled workflow.

## 11. Reports and outputs

Each import run must produce a machine-readable report and a human-readable
summary.

At minimum, report:

- Source artifact and hash.
- Release metadata.
- Workbook structure detected.
- Source record counts.
- Validation findings by rule and severity.
- Unsupported or unexpected values.
- Normalization actions.
- Identity candidate and assignment counts.
- Unresolved identity and hierarchy counts.
- Approved exclusions.
- Processing rule versions.
- Review decisions and outstanding issues.
- Promotion eligibility and reasons for blocking.

A report must distinguish source record counts from normalized, resolved,
excluded, and published record counts.

## 12. Implementation boundaries

The initial implementation should use:

- Python 3.12 within the supported project environment.
- Pandas and OpenPyXL for workbook processing where appropriate.
- Pytest for tests.
- Ruff for linting.
- SQLite-compatible schema and migrations for local development and D1
  compatibility.

The ETL must remain independent of the API runtime and must not require an
AI provider, network access, or cloud service to process approved source
artifacts.

The API and database implementation details are governed by their respective
architecture and schema documents.

## 13. Open implementation decisions

The following must be settled during implementation:

- Exact import-run and source-artifact schema.
- Finding and review-decision schema.
- Rule registry format and versioning strategy.
- Workbook profile discovery and selection.
- Exclusion granularity and published projection behavior.
- Report formats and retention.
- Maintainer authentication and authorization for any future review UI.
- Database transaction and retry strategy.
- Public data-quality report format.
