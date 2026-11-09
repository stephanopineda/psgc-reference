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

The currently inspected PSA workbooks contain 11 columns, including one blank-header column.

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
| 9 | 2020 Population | `population_2020` | Nullable |
| 10 | Blank header | Unmapped | Inspect before discarding |
| 11 | Status | `source_status_value` | Nullable |

Header comparison may normalize line breaks and surrounding whitespace, but must not silently accept missing, reordered, or unexpected columns.

If the worksheet structure changes, extraction must stop or require an explicitly reviewed mapping update.

The blank-header column must be inspected. If it contains non-empty values, those values must be reported and retained for investigation rather than silently discarded.

## 3. Release identification and metadata

A release represents one specific PSA publication, not merely a calendar year.

Multiple publications may exist within the same year. Therefore, the release identifier must distinguish individual publications.

Each imported release must record:

| Field | Description |
|---|---|
| `release_id` | Stable internal identifier |
| `release_name` | Human-readable PSA publication name |
| `publication_date` | Publication date stated by PSA |
| `effective_date` | Nullable; populated only when explicitly supported by the source |
| `source_file_name` | Original workbook filename |
| `source_file_sha256` | SHA-256 hash of the exact imported workbook |
| `source_url` | Official source URL, if available |
| `imported_at` | Timestamp of the import operation |
| `is_complete` | Whether the release passed completeness checks |
| `is_current` | Explicit designation as the current published release |

Known source publications:

| Publication | Publication date |
|---|---|
| PSGC 1Q 2024 | 2024-03-31 |
| PSGC 4Q 2024 | 2024-12-31 |
| PSGC 1Q 2025 | 2025-03-31 |

The publication date must come from the source metadata, not from the filename or file modification timestamp when the metadata is available.

`imported_at` must never be used as a substitute for publication chronology.

The current release must be explicitly designated. Importing a newer file must not automatically make it current.

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

### 5.8 Urban / Rural

Internal field: `urban_rural`

- Nullable.
- Preserve the original source value.
- Retain the source's association with the 2020 Census of Population and Housing (2020 CPH).
- Do not infer values for missing records.

### 5.9 Population

Internal field: `population_2020`

- Nullable integer.
- Accept valid whole-number values.
- Reject invalid numeric representations.
- Reject negative values unless an authoritative source definition explicitly permits them.
- Do not round fractional values.
- Do not substitute population values from another release.

The field represents the population reference supplied by the source, not a live or current population estimate.

### 5.10 Status

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
| Non-empty unmapped source column | REVIEW |
| Missing correspondence code | WARNING |
| Duplicate correspondence code | REVIEW |
| Unknown geographic level | REVIEW |
| Unknown city class | REVIEW |
| Unknown income classification | REVIEW |
| Unresolved parent relationship | REVIEW |
| Unexpected change in release record counts | REVIEW |

Validation must not silently repair source data.

Where a transformation is deterministic and permitted by this contract, the ETL may normalize the value while retaining its original representation.

A release containing errors must not be promoted as current.

Warnings and review findings must be included in the import report. Any review conditions that affect identity resolution or hierarchy must be resolved before the release is published.

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
14. Unexpected non-empty values in the blank-header column.
15. The three SGA barangay PSGC code changes between 1Q 2024 and 4Q 2024.

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
