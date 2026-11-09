# PSGC Source Data Contract

**Contract version:** 0.1.0
**Status:** Initial design
**Source authority:** Philippine Statistics Authority (PSA)
**Primary source:** PSA Philippine Standard Geographic Code (PSGC) publication workbooks

## 1. Purpose

This document defines how the PSGC ETL project reads, preserves, validates, and normalizes data published by the Philippine Statistics Authority.

The contract applies to every PSA PSGC release imported into this project.

Its primary principle is:

> Preserve the source as published. Keep normalized values, derived relationships, and system interpretations distinguishable from source data.

The ETL must not silently invent, discard, or reinterpret source information to make records conform to an assumed administrative hierarchy.

## 2. Source workbook

### 2.1 Expected worksheet

The primary data worksheet is named `PSGC`.

Other worksheets may include:

- `Metadata`
- `National Summary`
- `Provincial Summary` or `Prov Sum`
- `Notes`
- `Coding Structure`

The ETL must not assume that all releases use identical names for supplementary worksheets.

The `PSGC` worksheet is the authoritative source for the individual geographic records being imported.

### 2.2 Expected columns

The currently inspected PSA workbooks contain 11 columns, including one
blank-header column.

| Position | Source header | Internal field | Requirement |
|---:|---|---|---|
| 1 | 10-digit PSGC | `psgc_code` | Required |
| 2 | Name | `name` | Required |
| 3 | Correspondence Code | `correspondence_code` | Nullable |
| 4 | Geographic Level | `geographic_level` | Nullable |
| 5 | Old names | `old_names` | Nullable |
| 6 | City Class | `city_class` | Nullable |
| 7 | Income Classification | `income_classification` | Nullable |
| 8 | Urban / Rural (based on 2020 CPH) | `urban_rural` | Nullable |
| 9 | 2020 Population | `population` | Nullable |
| 10 | Blank header | `population_annotation` | Nullable |
| 11 | Status | `source_status_value` | Nullable |

Header comparison may normalize line breaks and surrounding whitespace, but
must not silently accept missing, reordered, or unexpected columns.

If the worksheet structure changes, extraction must stop or require an
explicitly reviewed mapping update.

Although column 10 has no source header, it contains values associated with
the population figures in column 9. These include numbered footnote references
and explanatory text describing population inclusions, exclusions, transfers,
and recomputations.

Map this column to `population_annotation` for the inspected source profile.
Preserve its original blank header, column position, cell values, and source
locations in the extracted source representation.

Do not silently discard its values or merge them into `population`, `name`,
or `source_status_value`.

A future source release may change the meaning or position of this column.
Such a change requires inspection and an explicitly reviewed mapping update.

## 3. Release identification and metadata

A release represents one specific PSA publication, not merely a calendar
year.

Multiple publications may exist within the same year. Therefore, the release
identifier must distinguish individual publications.

Each imported release must record:

| Field | Description |
|---|---|
| `release_id` | Stable internal identifier |
| `release_name` | Human-readable PSA publication name |
| `publication_date` | Publication date stated by PSA |
| `effective_date` | Nullable; populated only when explicitly supported by the source |
| `population_reference_year` | Reference year of the population figures |
| `urban_rural_reference_year` | Reference year associated with the urban/rural classification |
| `source_file_name` | Original workbook filename |
| `source_file_sha256` | SHA-256 hash of the exact imported workbook |
| `source_url` | Official source URL, if available |
| `imported_at` | Timestamp of the import operation |
| `is_complete` | Whether the release passed completeness checks |
| `is_current` | Explicit designation as the current published release |

The population and urban/rural reference years describe the underlying
statistical data. They are distinct from the PSA publication date.

For the inspected 1Q 2024, 4Q 2024, and 1Q 2025 workbooks, both fields
refer to 2020.

The applicable source notes and methodology references must also be retained.
A reference year alone does not fully describe the methodology used to
produce a classification.

Known source publications:

| Publication | Publication date | Population reference year | Urban/rural reference year |
|---|---|---:|---:|
| PSGC 1Q 2024 | 2024-03-31 | 2020 | 2020 |
| PSGC 4Q 2024 | 2024-12-31 | 2020 | 2020 |
| PSGC 1Q 2025 | 2025-03-31 | 2020 | 2020 |

The publication date must come from the source metadata, not from the
filename or file modification timestamp when the metadata is available.

`imported_at` must never be used as a substitute for publication chronology.

The current release must be explicitly designated. Importing a newer file
must not automatically make it current.

## 4. Source values and normalized values

The ETL must distinguish the original source representation from the normalized representation.

At minimum, extraction must retain:

- Release identifier
- Source worksheet name
- Source row number
- Original source values
- Source column mapping

Normalization must not overwrite the original source values.

Where normalization changes a value, the ETL must make the normalized result traceable to its original source value.

Missing values, literal placeholders, and actual values must remain distinguishable.

Examples:

| Source value | Interpretation |
|---|---|
| Empty cell | Missing value |
| `-` | Literal source placeholder |
| `CC` | Actual classification value |
| `Capital` | Actual source annotation |
| `Pob.` | Actual source annotation |

Do not automatically convert every placeholder to SQL `NULL`.

## 5. Field-level contract

### 5.1 PSGC code

Internal field: `psgc_code`

- Store as text.
- Preserve leading zeros.
- Do not convert to an integer.
- Do not remove meaningful characters.
- Do not derive another identifier from it.
- Validate against the expected format for the applicable release.
- Require uniqueness within a release.

A PSGC code is a source identifier that may change between releases.

It is not the project's permanent internal entity identifier.

#### Release-specific code formats

Code validation must use an explicit format profile for the applicable source release.

- The inspected 1Q 2024, 4Q 2024, and 1Q 2025 workbooks use 10-digit PSGC codes.
- Historical source data may use legacy 9-digit PSGC formats.
- Do not enforce a universal 10-digit length across all supported releases.
- Do not pad, truncate, or otherwise convert a code to make it conform to another release's format.
- The format profile must be selected and documented for each supported source type or release family.
- A code that does not match its selected profile must be reported as invalid; do not silently repair it.

### 5.2 Correspondence code

Internal field: `correspondence_code`

- Store as nullable text.
- Preserve the source value.
- Do not derive it from the PSGC code.
- Do not assume it always has a fixed length.
- Do not assume it is unique.
- Do not arbitrarily pad numeric values with zeros.

Some inspected workbooks store correspondence codes in numeric Excel cells despite displaying them with text number formatting.

When converting numeric Excel values:

- Accept only valid whole-number representations.
- Convert them to decimal-free strings.
- Avoid scientific notation.
- Do not add leading zeros that are not represented by the source value.
- Reject invalid numeric representations rather than silently truncating them.

Missing correspondence codes are valid source conditions.

Duplicate correspondence codes must be reported for review, not automatically rejected.

A missing correspondence code is an expected condition and is not, by
itself, a validation error or warning. The correspondence code represents
the previous PSGC coding system and is not a required predecessor identifier
for every record in a later release. Entities introduced after the transition
to the 10-digit PSGC format may have no correspondence code.

The ETL must preserve a missing correspondence code as `null` in the
normalized representation. It must not derive a correspondence code from
the current PSGC code, pad or truncate either identifier, or assume that
every current entity has a predecessor in the previous coding system.

### 5.3 Name

Internal field: `name`

- Required.
- Preserve the original source value.
- A normalized comparison value may trim surrounding whitespace.
- Do not automatically change spelling, capitalization, punctuation, or abbreviations.
- Do not assume a name uniquely identifies an entity.

Name changes between releases must be recorded as source changes.

### 5.4 Geographic level

Internal field: `geographic_level`

Recognized source values currently observed:

| Value | Description |
|---|---|
| `Reg` | Region |
| `Prov` | Province |
| `City` | City |
| `Mun` | Municipality |
| `Bgy` | Barangay |
| `SubMun` | Sub-municipality |
| `SGU` | Special Geographic Unit |
| NULL | No geographic level supplied |

Preserve the original source value.

Do not silently map one geographic level to another.

Unknown non-null values must be retained in the extracted source data and reported for review. They must not be silently converted to `NULL`.

Null geographic levels are valid source conditions.

### 5.5 Old names

Internal field: `old_names`

- Nullable.
- Preserve the original source value.
- Do not automatically split the value into multiple names.
- Do not treat old names as proof of historical entity identity.
- Do not automatically use old names to merge records.

Any future parsing of this field must have a separately documented rule.

### 5.6 City class

Internal field: `city_class`

Observed values include:

- `CC`
- `HUC`
- `ICC`

Preserve the original value.

Do not infer city class from the name or geographic level.

Unknown values must be reported for review without discarding the source record.

### 5.7 Income classification

Internal field: `income_classification`

- Nullable.
- Preserve the original source value.
- Do not automatically convert `-` into `NULL`.
- Do not infer a classification from another release.
- Do not assume the classification is permanent across releases.

The inspected PSA Notes worksheet provides additional definitions for
income-classification values.

In particular:

- `*` indicates that an entity was not reclassified under the referenced
  Department of Finance order due to incomplete income data.
- `-` indicates newly created municipalities that were not reclassified.

The Notes worksheet also identifies different update dates for province,
city, and municipality income classifications.

These source definitions must be retained as release-specific documentation.
Do not treat these symbols as generic missing-value indicators or infer
income classifications from the documented income brackets.

### 5.8 Urban / Rural

Internal field: `urban_rural`

- Nullable.
- Preserve the original source value.
- Retain its association with the applicable urban/rural reference year.
- Do not infer values for missing records.

For the inspected workbooks, the classification is based on the 2020 Census
of Population and Housing and the PSA resolutions identified in the Notes
worksheet.

The release metadata must retain `urban_rural_reference_year` separately
from the publication date and population reference year.

The applicable source methodology and resolution references must also be
preserved. Do not assume that the reference year alone fully describes the
classification methodology.

The source values `U`, `R`, and `-` must be preserved as published.
Do not automatically convert `-` to `NULL` without a documented,
release-specific interpretation.

### 5.9 Population

Internal field: `population`

- Nullable integer.
- Accept valid whole-number values.
- Reject invalid numeric representations.
- Reject negative values unless an authoritative source definition explicitly
  permits them.
- Do not round fractional values.
- Do not substitute population values from another release.

The field represents the population reference supplied by the source, not a
live or current population estimate.

For the inspected workbooks, the population reference year is 2020.

#### Literal source values

A literal `-` in the population column must be preserved in the extracted
source representation and normalized to `NULL`, not zero.

An empty source cell must remain distinguishable from a literal `-`.

#### Formula cells

Some population cells contain Excel formulas rather than literal numeric
values.

For formula cells:

- Preserve the original formula expression.
- Obtain the cached result from the workbook using a `data_only=True` read.
- Associate the formula and cached result with the same source cell.
- Use a valid cached whole-number result as the extracted population value.
- Do not execute or independently recalculate the source formula during
  extraction.
- Do not substitute zero or a value from another release when a cached
  result is missing.
- Generate a review finding when a formula has no usable cached result.

The formula expression and cached result are source evidence. The normalized
`population` value must remain traceable to both.

A cached formula result represents the value saved by the workbook. The ETL
must not claim that it independently verified the spreadsheet calculation.

### 5.10 Population annotation

Internal field: `population_annotation`

This field originates from column 10 of the inspected `PSGC` worksheet,
which has a blank source header.

- Nullable.
- Preserve the original source value and source location.
- Do not merge it into the population value or geographic name.
- Do not interpret it as an entity lifecycle status.

Observed values include numbered references such as `17/`, `45/`, and
explanatory text such as `(excluding BAGUIO CITY)`.

Numbered references correspond to definitions in the `Notes` worksheet
of the same PSA release.

The ETL must:

- Retain the original annotation exactly as published.
- Retain the release-specific footnote definitions.
- Resolve numbered references only against the corresponding release.
- Never assume that the same footnote number has the same meaning across
  different releases.
- Preserve explanatory text that is not a numbered reference.
- Avoid inferring or changing population values from annotation text.

Population annotations provide context for interpreting published population
figures. They do not independently establish geographic identity, hierarchy,
or lifecycle status.

### 5.11 Status

Internal field: `source_status_value`

Observed values include:

- `Capital`
- `Pob.`
- Empty values

This field must be treated as a source annotation.

It must not be interpreted as the entity's lifecycle status.

In particular:

- `Capital` does not mean active.
- `Pob.` does not mean inactive or abolished.
- An empty value does not mean the entity has no lifecycle status.

Any future lifecycle classification must be supported by authoritative documentation and stored separately from this source field.

## 6. Geographic hierarchy

The inspected PSA worksheet does not provide an explicit parent identifier in the listed columns.

Parent-child relationships are therefore derived information and must be distinguishable from source fields.

Rules:

1. Do not determine parent relationships solely by taking a prefix of a PSGC code.
2. Do not assume adjacent worksheet rows establish parent-child relationships.
3. Use geographic level, official coding conventions, authoritative documentation, and reviewed exceptions.
4. Every resolved parent must have a corresponding version in the same release.
5. Unresolved or ambiguous parent relationships must be reported.
6. Do not assign a parent merely to make the hierarchy complete.
7. Preserve special geographic arrangements even when they do not fit a conventional administrative hierarchy.

### 6.1 Special Geographic Area

The SGA records demonstrate that geographic levels and codes can change between publications.

In 1Q 2024:

- The SGA parent record has PSGC `1999900000` and a null geographic level.
- Eight child records use geographic level `SGU`.
- Sixty-three barangay records are associated with the SGA structure.
- The parent record's source name is an interim province-code description.

In 4Q 2024 and 1Q 2025:

- The parent remains `1999900000` with a null geographic level.
- The eight records are classified as municipalities (`Mun`).
- The same 63 barangays remain represented.
- Three barangays have different PSGC codes.
- The parent record's source name is `Special Geographic Area`.

The three observed barangay code changes are:

| Barangay | 1Q 2024 PSGC | 4Q 2024 PSGC |
|---|---|---|
| Dunguan | `1999908003` | `1999904007` |
| Macabual | `1999907007` | `1999908009` |
| Panicupan | `1999906008` | `1999908010` |

Their names and correspondence codes remained unchanged in the inspected releases. This is supporting evidence for possible identity continuity, not conclusive proof. Identity resolution must follow the separate review rules.

The ETL must preserve each release's actual source representation.

It must not rewrite the 1Q 2024 records as municipalities merely because later releases classify them that way.

### 6.2 City of Isabela

The PSA notes describe the special geographic and administrative treatment of the City of Isabela.

The parent record `0990100000` has a null geographic level and is associated with the City of Isabela hierarchy.

The ETL must preserve the source record and use an explicitly reviewed hierarchy rule.

It must not invent a province-level classification for the null-level parent.

## 7. Validation contract

Validation findings must be structured and attributable to a release and, where applicable, a source row.

Use these severity levels:

| Severity | Meaning |
|---|---|
| `ERROR` | The affected record or release cannot safely proceed |
| `WARNING` | The source condition is valid but deserves attention |
| `REVIEW` | A human decision or authoritative evidence is needed |

Initial validation rules:

| Condition | Severity |
|---|---|
| Missing PSGC code | ERROR |
| Invalid PSGC code format | ERROR |
| Duplicate PSGC code within a release | ERROR |
| Missing name | ERROR |
| Invalid population representation | ERROR |
| Unexpected worksheet structure | ERROR |
| Non-empty source column without an approved mapping | REVIEW |
| Duplicate correspondence code | REVIEW |
| Unknown geographic level | REVIEW |
| Unknown city class | REVIEW |
| Unknown income classification | REVIEW |
| Unresolved parent relationship | REVIEW |
| Unexpected change in release record counts | REVIEW |
| Numeric PSGC stored in an Excel numeric cell | WARNING |
| Numeric correspondence code stored in an Excel numeric cell | WARNING |
| Population formula without a usable cached result | REVIEW |
| Invalid cached population formula result | ERROR |
| Unresolved numbered population annotation reference | REVIEW |

Validation must not silently repair source data.

Where a transformation is deterministic and permitted by this contract, the ETL may normalize the value while retaining its original representation.

A release with unresolved `ERROR` findings must not be promoted as current.
An affected record may be excluded from the published projection only through
an explicitly approved, tested, and documented process that preserves the
original source data and prevents the affected record from compromising
published data integrity. Such an exclusion must have a recorded disposition;
it must not silently downgrade the original finding.

Warnings and review findings must be included in the import report and reviewed by the person responsible for the import.

A validation finding must not automatically be treated as a defect in the PSA source. The reviewer must determine whether it represents:

- A legitimate source-data or workbook-structure variation that the ETL must support.
- A genuine source-data defect that prevents safe promotion.
- A non-blocking anomaly that can be retained and reported without compromising data integrity.

When a legitimate source variation is not supported by the current ETL, the ETL logic or its documented mapping rules must be updated and tested against the original, unchanged workbook. The source workbook must never be edited to accommodate the implementation.

A genuine source-data defect that affects data integrity must block promotion until it has been appropriately resolved. A documented disposition alone must not permit a release with an unresolved blocking defect to be promoted.

If the affected source data cannot be safely resolved, the release must be rejected or the affected records must be excluded from the published projection through an explicitly approved, tested, and documented process. The original source values must remain preserved. The ETL must not silently repair or discard them.

Review conditions affecting identity resolution or hierarchy must receive an explicit disposition. Unresolved conditions may be accepted as non-blocking only when the reviewer documents the rationale and the affected records are excluded from API behavior that requires the unresolved identity or hierarchy.

The import report and release audit trail must record the reviewer's identity, decision, rationale, timestamp, and applicable ETL and rule versions.

## 8. Historical release comparison

Every release is an independent source snapshot.

The ETL must preserve release-specific values and must not overwrite historical records with current values.

Rules:

- Absence from a later release does not automatically mean abolished.
- A changed PSGC code does not automatically mean a new entity.
- A changed name does not automatically mean a new entity.
- A matching correspondence code is supporting evidence, not conclusive identity proof.
- Splits, mergers, reorganizations, and geographic reassignment require explicit change classification.
- Uncertain identity matches must be sent for review.
- Do not manufacture source versions or official lifecycle statuses.

Historical identity resolution is defined separately in `identity-resolution.md`.

## 9. ETL processing boundaries

The pipeline should distinguish the following logical stages:

1. **Source acquisition**
   - Obtain the original PSA workbook.
   - Preserve the original file.
   - Calculate its SHA-256 hash.

2. **Extraction**
   - Read the `PSGC` worksheet.
   - Verify its structure.
   - Retain original source values and row numbers.

3. **Validation**
   - Validate worksheet structure and record-level constraints.
   - Produce structured validation findings.

4. **Normalization**
   - Convert values to their defined internal data types.
   - Retain traceability to original source values.
   - Avoid unsupported semantic transformations.

5. **Hierarchy resolution**
   - Resolve parent-child relationships using documented rules.
   - Report unresolved relationships.

6. **Identity resolution**
   - Match records to stable internal entities using the separately defined identity-resolution rules.
   - Record uncertain matches for review.

7. **Comparison**
   - Compare the release with prior releases.
   - Produce additions, removals, modifications, and review-required changes.

8. **Loading**
   - Load only validated and approved release data.
   - Preserve historical versions.
   - Do not promote an incomplete or invalid release as current.

The original source workbook must remain unchanged.

## 10. Expected ETL outputs

An import operation should produce, at minimum:

- Release metadata
- Extracted source records
- Validation report
- Normalized records
- Hierarchy resolution findings
- Identity resolution findings
- Release comparison report
- Load summary

The exact output file formats and database staging structures will be defined during implementation design.

The ETL must provide enough information to trace a published record back to its source release, worksheet, and row.

## 11. Initial regression fixtures

The following source conditions must be represented in automated tests:

1. PSGC codes with leading zeros.
2. Missing correspondence codes.
3. Numeric Excel correspondence codes.
4. Duplicate PSGC codes within a release.
5. Duplicate correspondence codes.
6. Null geographic levels.
7. `SGU` records in 1Q 2024.
8. Municipality (`Mun`) records in 4Q 2024 and 1Q 2025.
9. The SGA parent record `1999900000`.
10. The special City of Isabela parent record `0990100000`.
11. `Capital` and `Pob.` source annotations.
12. Literal placeholders such as `-`.
13. Missing population values.
14. Non-empty values in the blank-header column are preserved as population annotations.
15. The three SGA barangay PSGC code changes between 1Q 2024 and 4Q 2024.
16. Numeric PSGC cells that require decimal-free string normalization.
17. Population cells containing literal `-` placeholders.
18. Population cells containing formulas with cached numeric results.
19. Population formulas with missing cached results.
20. Population annotations containing numbered footnote references.
21. Population annotations containing explanatory text.
22. Release-specific population footnote definitions in the `Notes` worksheet.
23. Income-classification annotations such as `*` and `-`.
24. Urban/rural classification methodology references.
25. Population and urban/rural reference years distinct from publication dates.

These fixtures must verify that source preservation, validation, and normalization behave as specified.

## 12. Known limitations and future review

This contract is based on the inspected 1Q 2024, 4Q 2024, and 1Q 2025 PSA workbooks.

It does not claim that every future or historical PSA publication has an identical structure.

Before importing a new release:

- Inspect its metadata and notes.
- Verify its worksheet structure.
- Review changes to source columns and geographic levels.
- Review newly introduced classifications and special geographic arrangements.
- Update this contract when a source change requires a new rule.

Any change to this contract must be reviewed and version-controlled.

## 13. Source attribution

The inspected PSA workbook metadata specifies acknowledgement of the Philippine Statistics Authority as the source.

Public-facing documentation and API responses must acknowledge PSA as the source of the underlying PSGC data.

The exact attribution wording and any additional publication or redistribution conditions must be verified against the applicable PSA publication before public deployment.
