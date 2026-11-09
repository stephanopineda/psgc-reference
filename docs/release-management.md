# Release Management and Publication Contract

## 1. Purpose

This document defines how an imported PSGC source snapshot becomes an
approved release available through the public API.

Importing data, approving data, and publishing data are separate operations.

A successful ETL run does not automatically publish a release.

## 2. Release principles

1. Every release represents a specific PSA source snapshot.
2. The original source artifact remains immutable.
3. Every release is reproducible from its source artifact and recorded
   processing versions and decisions.
4. Only maintainer-approved processing results may be published.
5. Findings and exclusions must remain traceable.
6. A release may contain documented non-blocking limitations.
7. Unresolved identity or hierarchy must never be presented as resolved.
8. Publication must be atomic from the API consumer's perspective.
9. A previous approved release must remain recoverable.
10. Release history must not be silently rewritten.

## 3. Release identity

A release must have an internal immutable `release_id`.

It must also retain source publication metadata, including where available:

- PSA publication period or release label.
- PSA publication date.
- Source workbook filename.
- Source artifact SHA-256 hash.
- Source acquisition timestamp.
- Source worksheet profile.
- Import-run identifier.

The PSA publication date, acquisition timestamp, import timestamp, and
publication timestamp are distinct values.

The project must not infer the latest official release solely from the
largest timestamp or the most recently imported workbook.

The maintainer must explicitly designate which approved release is current.

## 4. Release lifecycle

The initial lifecycle is:

| State | Meaning |
|---|---|
| `DISCOVERED` | Source artifact has been acquired and identified |
| `ANALYZED` | Workbook inspection and initial analysis have completed |
| `IMPORTED` | Extracted source data and findings have been stored |
| `IN_REVIEW` | Findings and proposed decisions are being reviewed |
| `READY_FOR_APPROVAL` | Required checks and review dispositions are complete |
| `APPROVED` | The maintainer has approved the release for publication |
| `PUBLISHED` | The release is available through the public API |
| `REJECTED` | The release was not approved |
| `SUPERSEDED` | A later release has replaced it as the designated current release |
| `WITHDRAWN` | The release has been withdrawn from current API use |

State transitions must be explicit and auditable.

A failed or interrupted import must not be represented as an approved or
published release.

The implementation may use additional internal processing states, but it
must preserve the distinction between imported, approved, and published data.

## 5. Review and approval responsibility

The maintainer is responsible for deciding whether the processed release is
suitable for publication.

The maintainer must review:

- Workbook structure changes.
- Blocking validation findings.
- Unsupported source values.
- Proposed normalization or mapping changes.
- Identity-resolution decisions.
- Unresolved parent relationships.
- Proposed exclusions.
- Historical changes that affect interpretation.
- Data-quality and coverage reports.

AI-generated analysis and recommendations are supporting material only.
They do not constitute approval.

The person approving a release must be recorded in the audit history.

The initial project may use a maintainer-controlled local workflow. A
multi-user review interface is not required for the first implementation.

## 6. Promotion gates

A release may become eligible for approval only when:

1. The original source artifact and its hash are recorded.
2. Workbook extraction completed without silently discarding source content.
3. All blocking validation errors have been resolved or the release has been
   rejected.
4. All review findings have explicit dispositions.
5. Approved transformations and exclusions have documented rules or
   decisions.
6. Identity assignments satisfy the identity-resolution contract.
7. Parent-child relationships exposed by the API are valid within the same
   release.
8. Unresolved records are excluded from API behavior that requires resolved
   identity or hierarchy.
9. Required regression and integrity tests pass.
10. The import report and data-quality report are generated.
11. Processing versions and maintainer decisions are recorded.

A finding may be non-blocking only when its disposition and rationale are
documented. The system must not downgrade a finding's severity merely to
allow promotion.

A genuine source-data defect affecting integrity must block promotion until
an appropriate resolution or formally documented disposition is available.
A documented disposition must not falsely represent defective or uncertain
source data as verified.

## 7. Unresolved records and partial publication

A release may be published with non-blocking unresolved records if:

- Every source record has a documented final assignment state.
- The unresolved records remain stored and traceable.
- The maintainer explicitly accepts the limitation.
- The rationale and affected records are recorded.
- API operations requiring resolved identity or hierarchy do not expose
  those records as resolved entities.
- The release-quality report discloses the limitation.

The project must distinguish:

- Records present in the source workbook.
- Records successfully extracted.
- Records normalized.
- Records assigned to entities.
- Records with unresolved identity or hierarchy.
- Records excluded from a published projection.
- Records available through each API endpoint.

An excluded record is not deleted from the source snapshot.

A release containing unresolved assignments must not be described as fully
identity-resolved.

## 8. Published data and API behavior

The API must read only from the designated published release or from an
explicitly requested historical release.

The API must not expose intermediate import data, unapproved decisions, or
partially loaded records.

For every published release:

- PSGC codes and source attributes must retain release-specific values.
- Parent-child references must resolve within the same release.
- Entity identity must follow approved assignments.
- Unresolved identity must not be guessed at request time.
- Excluded records must not appear in projections from which they were
  excluded.
- The published data must be consistent across requests during a release
  transition.

The API contract must define how clients select a release and how current
release selection works. The API must not silently change historical results
when a new release is published.

Public API consumers should not need to understand ETL internals to use the
API. However, they must have access to release metadata, data-quality
summaries, and change documentation.

## 9. Release reports and public disclosure

Each release must have a human-readable release note and a machine-readable
quality report.

The release note should summarize:

- PSA source publication and source artifact identity.
- Previous release used for comparison.
- Major additions, removals, and changes.
- Important code, name, or geographic-level changes.
- Significant identity or hierarchy decisions.
- Material transformations and exclusions.
- Known limitations and unresolved cases.
- ETL and rule versions.

The quality report should include:

- Source and extracted record counts.
- Counts by geographic level where available.
- Validation findings by severity and category.
- Normalization and transformation counts.
- Identity assignment counts.
- Unresolved identity and hierarchy counts.
- Exclusion counts by reason and projection.
- Test and integrity-check results.

Reports must distinguish source facts from project interpretations.

Do not publish sensitive operational information, credentials, internal
infrastructure details, or unnecessary personal information in public
reports.

## 10. Publication and current-release selection

Publication must be an explicit maintainer action.

The operation must:

1. Verify the release is approved.
2. Verify all promotion gates still pass.
3. Atomically update the designated current-release reference.
4. Preserve the previous current-release reference in the audit history.
5. Record the publication actor and timestamp.
6. Make the new release visible to API consumers only after the publication
   transaction succeeds.

A partially completed publication must not leave the API serving a mixture
of releases.

Historical approved releases must remain addressable unless withdrawn under
a documented policy.

## 11. Rollback and withdrawal

Rollback means changing the designated current release to a previously
approved release. It must not delete the newer release or erase its history.

Withdrawal means preventing a release from being served through the API.
It requires a documented reason and an audit entry.

For rollback or withdrawal, record:

- Affected release.
- Previous and resulting current-release references.
- Reason.
- Decision maker.
- Timestamp.
- API impact.
- Related incident or finding, if applicable.

A withdrawn release must remain available to authorized maintainers for
investigation, subject to the project's retention policy.

## 12. Audit history

The system must retain an auditable history of:

- Source acquisition.
- Import runs.
- Processing versions.
- Validation findings.
- Review decisions.
- Approved transformations and exclusions.
- Identity assignments and relationship decisions.
- Test results.
- Release approval.
- Publication.
- Current-release changes.
- Rollback and withdrawal.

Audit history must be append-only from the application's perspective.
Corrections to prior decisions must create new entries rather than silently
rewriting the historical decision.

## 13. Initial operational workflow

The initial maintainer workflow is:

1. Acquire and preserve the PSA workbook.
2. Inspect workbook structure and source metadata.
3. Run extraction and deterministic validation.
4. Review the generated import and anomaly reports.
5. Investigate unsupported variations and unexpected findings.
6. Use AI assistance if useful to analyze findings or draft proposed changes.
7. Decide which rule changes, transformations, exclusions, or identity
   decisions are appropriate.
8. Implement approved changes and regression tests.
9. Reprocess the unchanged source workbook.
10. Compare the new output with the previous processing result.
11. Review unresolved findings, coverage, and data-quality reports.
12. Approve or reject the release.
13. Publish the approved release explicitly.
14. Publish release notes and the data-quality report.

## 14. Open implementation decisions

The following must be settled during implementation:

- Exact release and import-run database schema.
- Whether approval and publication are separate commands or separate
  operations in one CLI.
- Current-release pointer implementation.
- Historical release retention policy.
- Withdrawal policy and public API behavior.
- Public release-note and quality-report formats.
- Maintainer authorization for local and future hosted workflows.
- Atomic publication strategy for the selected database.
- Whether signed release manifests are warranted.
