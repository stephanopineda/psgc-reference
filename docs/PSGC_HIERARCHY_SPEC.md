# PSGC Hierarchy Specification

**Status:** Implemented — candidate hierarchy generated and validated; relationship review and approval pending
**Scope:** Release-specific administrative and geographic parent-child relationships

## 1. Purpose

The PSA PSGC publication is the source of truth for geographic records and
their published attributes.

This project derives a separate hierarchy layer so consuming applications
can navigate PSGC records through cascading location selectors.

The hierarchy:

- is generated independently for each PSGC release;
- does not modify or replace source records;
- preserves source-defined geographic levels and classifications;
- records proposed relationships separately from approved relationships;
- must not assume that PSGC codes or relationships are immutable across
  releases.

## 2. Source record preservation

The following source attributes remain authoritative and must not be
rewritten by hierarchy generation:

- PSGC code;
- geographic name;
- geographic level;
- city classification;
- correspondence code;
- other extracted publication attributes.

Normalization and data-quality review must remain separate from hierarchy
generation.

For example, a malformed source name such as `City of Lucenaa/` must not
be silently corrected by the hierarchy builder.

## 3. Hierarchy model

A hierarchy edge represents one immediate parent-child relationship:

`parent_psgc_code -> child_psgc_code`

Each edge belongs to exactly one release.

The `record_hierarchy` table is the storage layer for these edges. Generated
edges must initially have `review_status = 'PROPOSED'`.

The hierarchy builder must not automatically approve relationships.

## 4. Expected geographic relationships

The following are the expected relationship patterns. They are rules to
validate against each source release, not permission to invent missing
records.

### 4.1 Standard provinces

Expected path:

`Region -> Province -> Component City or Municipality -> Barangay`

A component city (`City`, `city_class = CC`) or municipality (`Mun`) is
normally a child of its province.

### 4.2 Highly Urbanized Cities and Independent Component Cities

Expected path:

`Region -> HUC or ICC -> Barangay`

HUC and ICC records must not be placed under a province merely because their
correspondence codes identify a former or geographically associated
province.

The published PSGC code identifies the release-specific geographic
placement. Correspondence codes are supporting cross-reference data, not
the immediate-parent key.

### 4.3 National Capital Region

NCR has no province layer.

Expected paths:

- `NCR -> HUC -> Barangay`
- `NCR -> Pateros -> Barangay`
- `NCR -> Manila -> SubMunicipality -> Barangay`

Manila's 14 SubMunicipality records are siblings under Manila. They must
never be nested under one another because of coincidental code-prefix
matches.

### 4.4 Special Geographic Area

The Special Geographic Area (SGA) must be represented using the records
published in each release.

The observed source structures differ:

- 2024-Q1: an unclassified SGA grouping record with eight `SGU` records;
- later inspected releases: an unclassified SGA grouping record with eight
  `Mun` records.

The hierarchy must preserve these release-specific classifications. It
must not rewrite the 2024-Q1 `SGU` records as municipalities.

Expected structure:

`BARMM Region -> Special Geographic Area -> source-defined child records
-> Barangays`

The exact parent relationship for the SGA grouping record and its children
must be validated against the source codes and records before approval.

### 4.5 Isabela grouping record

The source contains both:

- `0990100000` — City of Isabela (Not a Province), unclassified;
- `0990101000` — City of Isabela, classified as `City` / `CC`.

These are separate source records and must not be merged.

The unclassified record is a possible grouping parent of the City record.
This relationship must be explicitly validated and documented rather than
inferred from a generic geographic-level rule.

## 5. PSGC code structure and parent derivation

The inspected publications use 10-digit PSGC codes.

The general segment structure is:

| Segment | Positions | Length |
|---|---:|---:|
| Region | 1–2 | 2 |
| Province | 3–5 | 3 |
| City / Municipality | 6–7 | 2 |
| Barangay | 8–10 | 3 |

This structure is useful for generating parent candidates, but a matching
prefix alone does not prove a parent-child relationship.

### 5.1 Prohibited shortcut

Do not use a six-digit prefix as a universal parent lookup.

The source analysis found 209–210 groups of City/Municipality records sharing
the same six-digit prefix. These are not parent-child relationships.

For example, municipalities in Abra share a province prefix. A municipality
must not become the parent of another municipality simply because their
codes share six digits.

### 5.2 Candidate generation

Candidate generation must be constrained by:

- the child's geographic level;
- the candidate parent's geographic level;
- city classification where applicable;
- the expected code segment;
- release-specific exceptions;
- the existence of the exact candidate parent record in the same release.

Candidate selection must reject:

- self-parent relationships;
- same-level relationships unless an explicitly documented exception
  permits them;
- barangay-to-barangay relationships;
- relationships based only on a six-digit prefix;
- relationships whose parent record does not exist in that release.

For Barangay records, candidate matching may use the applicable seven- or
eight-digit administrative prefix. When more than one candidate exists,
the builder must select only a uniquely justified immediate parent.
It must not silently resolve a genuine ambiguity.

### 5.3 Correspondence codes

Correspondence codes must be retained as source cross-reference attributes.

They can help identify continuity or changes across releases, but they must
not be treated as direct parent codes.

For example, HUC/ICC correspondence codes may refer to the geographic
location or former administrative code of the independent city.

## 6. Release-specific behavior

Hierarchy generation must use records from one release at a time.

It must not:

- use a parent record from another release;
- assume that a code in one release has the same classification in another;
- carry forward a relationship without validating it against the target
  release;
- overwrite historical hierarchy edges when a new release is imported.

Known differences requiring release-specific handling include:

- SGA child classification (`SGU` in 2024-Q1 versus `Mun` in later
  inspected releases);
- Bacolod's PSGC code changing from `0630200000` in 2024-Q1 to
  `1830200000` in later inspected releases, while its correspondence code
  remains `064501000`;
- source-name differences and data-quality findings.

## 7. Validation requirements

Every generated release hierarchy must be checked for:

1. Parent and child records exist in the same release.
2. No self-parent relationships.
3. No duplicate parent-child edges.
4. No child with multiple immediate parents unless explicitly allowed and
   documented.
5. No cycles.
6. No invalid geographic-level transitions.
7. No barangay used as a parent.
8. No municipality used as the parent of another municipality through a
   coincidental prefix.
9. Every classified non-root record has an expected parent or an explicit
   documented exception.
10. Unclassified records are reported for explicit handling.
11. Manila's SubMunicipalities resolve to Manila.
12. SGA relationships preserve the source release's classifications.
13. HUC/ICC relationships are not assigned to provinces merely because of
    correspondence codes.
14. No relationship references a record from a different release.

Validation output must distinguish:

- resolved relationships;
- unresolved records;
- ambiguous candidates;
- rejected candidates;
- explicitly exempted records.

An unresolved or ambiguous record must not be assigned an arbitrary parent.

## 8. Review and approval

All generated relationships begin as `PROPOSED`.

A relationship may become `APPROVED` only after:

- its parent and child records are verified;
- the relationship satisfies the documented rules;
- release-specific exceptions have been considered;
- the validation report has no unexplained errors affecting that edge.

Rejected candidates must remain distinguishable from approved relationships.

## 9. API implications

The eventual location API should expose the approved hierarchy, not raw
prefix-derived candidates.

The API should support:

- listing top-level regions for a selected release;
- listing immediate children of a location;
- retrieving one location;
- retrieving its ancestor path;
- searching locations within a release.

A location's `has_children` value describes its structural position.
It must not imply that the location is or is not selectable by every
consuming application.

Consumers may choose their own permitted selection levels.

The `latest` API must resolve only to a release explicitly designated as
the official current release. It must not automatically select the newest
imported release.

## 10. Implementation sequence

1. Implement a pure Python hierarchy candidate builder.
2. Generate proposed edges independently for all four imported releases.
3. Produce concise validation summaries.
4. Investigate unresolved and ambiguous records.
5. Add regression tests for Manila, NCR, HUC/ICC, Isabela, and SGA.
6. Review the generated hierarchy before approving any edges.
7. Implement API endpoints over approved hierarchy records.
8. Expose a `latest` alias only after an official release is explicitly
   activated.

## 11. Evidence and limitations

This draft is based on analysis of these PSA source workbooks:

- PSGC-1Q-2024-Publication-Datafile.xlsx
- PSGC-4Q-2024-Publication-Datafile.xlsx
- PSGC-1Q-2025-Publication-Datafile.xlsx
- PSGC-3Q-2026-Publication-Datafile.xlsx

The code structure and candidate relationships are derived from inspected
source records. They must not be interpreted as a complete official
statement of every PSA administrative relationship.

Any relationship not established by the source data and documented rules
must remain unresolved pending review.
