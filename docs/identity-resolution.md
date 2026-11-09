# PSGC Entity Identity Resolution

**Contract version:** 0.1.0
**Status:** Initial design
**Applies to:** Historical PSGC release matching

## 1. Purpose

This document defines how the project identifies geographic entities across PSA PSGC releases.

A PSGC code is a source identifier. It is not the permanent identity of a geographic entity.

The project must assign a stable internal `entity_id` so that an entity can be referenced across releases even when its source code, name, geographic level, or parent relationship changes.

Identity resolution must be conservative. When the available evidence does not establish continuity, the system must preserve the uncertainty instead of inventing a match.

This contract supplements `source-data-contract.md`.

## 2. Identity model

The identity model distinguishes three concepts:

| Concept | Meaning |
|---|---|
| Source record | One geographic record as published in a particular PSA release |
| Entity | The project's stable identity for a geographic entity |
| Entity version | The source representation of an entity in one release |

### 2.1 Entity

An entity represents a geographic unit whose identity is maintained across releases.

Each entity must have:

- A stable internal `entity_id`.
- A creation timestamp.
- A record of how and when its identity was established.
- An optional internal note for identity-resolution context.

The `entity_id` must:

- Be generated and managed by the project.
- Remain unchanged when an entity's PSGC code or name changes.
- Have no geographic meaning.
- Not be derived from a PSGC code, correspondence code, name, or hierarchy.
- Never be reused for a different entity.

A UUID is an acceptable implementation identifier. The selected identifier format must not encode source attributes.

### 2.2 Entity version

An entity version records how an entity appears in a particular release.

At minimum, it must reference:

- `entity_id`
- `release_id`
- The corresponding source record
- The source PSGC code
- The source name
- The source geographic level
- The source correspondence code, if supplied
- The resolved parent entity for that release, if established

Source attributes must remain release-specific. A later name or code must not overwrite an earlier version.

### 2.3 Cardinality constraints

The data model must enforce these rules:

1. A source record can be assigned to no more than one entity in the same release.
2. An entity can have no more than one version in the same release.
3. Every entity version must reference an existing release and source record.
4. A parent relationship must reference an entity version in the same release.
5. Entity-to-entity relationships, such as split and merger relationships, must be stored separately from parent-child relationships.
6. An unresolved source record must remain available without an invented entity assignment.

These constraints prevent accidental many-to-many matching and inconsistent historical snapshots.

## 3. Identity-resolution outcomes

Identity resolution must distinguish the result of a candidate comparison from the decision made about it.

### 3.1 Candidate outcomes

| Outcome | Meaning |
|---|---|
| `POTENTIAL_MATCH` | Evidence suggests that two source records may represent the same entity |
| `NO_MATCH` | Available evidence does not support continuity |
| `AMBIGUOUS` | Multiple candidates or conflicting evidence prevent a reliable decision |
| `NOT_EVALUATED` | The records have not yet undergone identity comparison |

These are internal resolution states, not PSA classifications.

### 3.2 Decision dispositions

A candidate-pair decision must support:

| Disposition | Meaning |
|---|---|
| `APPROVED_MATCH` | The records are accepted as versions of the same entity |
| `REJECTED_MATCH` | The proposed identity match is rejected |
| `DEFERRED` | The decision is postponed pending additional evidence |

A deferred decision must not be treated as an approved match or as proof that a new entity exists.

The final assignment state of each source record must be tracked separately:

| Assignment state | Meaning |
|---|---|
| `ASSIGNED_EXISTING_ENTITY` | The source record has been assigned to an established entity |
| `ASSIGNED_NEW_ENTITY` | A new internal entity has been approved for the source record |
| `UNRESOLVED` | No approved entity assignment has been made |

`ASSIGNED_EXISTING_ENTITY` requires an approved identity match or an explicitly approved continuation rule. `ASSIGNED_NEW_ENTITY` requires an explicit decision to establish a new entity; it must not be inferred merely because no candidate was found.

A source record may have rejected or deferred candidate pairs while remaining `UNRESOLVED` or eventually receiving an approved assignment.

The implementation must record candidate-generation results, candidate-pair decisions, and final source-record assignment states separately.

## 4. Evidence model

Identity resolution must retain the evidence used to reach a decision.

Evidence must be attributable to specific source records, releases, or authoritative documents.

### 4.1 Evidence types

| Evidence | Typical significance | Limitations |
|---|---|---|
| Same PSGC code across releases | Strong candidate evidence | Code reuse or conflicting source attributes must be considered |
| Official law, ordinance, or administrative issuance | Potentially authoritative | Must establish the specific geographic identity and effective change |
| Official PSA explanatory note or publication | Strong supporting evidence | Scope and wording must be examined |
| Same correspondence code | Supporting evidence | May be missing, reused, or non-unique |
| Same name | Supporting evidence | Names can be duplicated or reused |
| Same geographic level | Supporting evidence | Does not establish identity |
| Same parent entity | Supporting evidence | Parent relationships can change |
| Similar code structure | Weak supporting evidence | Prefixes and code proximity do not prove identity |
| Worksheet row proximity | No identity evidence | Source ordering must not be used as an identity rule |

Evidence strength is contextual. The table is guidance, not a numeric scoring system.

### 4.2 Conflicting evidence

Conflicting evidence must be retained and surfaced.

Examples include:

- The same PSGC code appears with a materially different geographic level.
- A correspondence code points to multiple possible candidates.
- A source record's name and parent both change without an explanatory source.
- Two earlier entities appear to correspond to one later record.
- One earlier entity appears to correspond to multiple later records.

The system must not resolve these conflicts by silently selecting the first candidate or the highest arbitrary score.

## 5. Candidate generation and matching rules

Candidate generation identifies records that deserve comparison. It does not establish identity by itself.

The implementation must be deterministic and explainable: the same inputs and rule version must produce the same candidate set and automated recommendations.

### 5.1 Exact PSGC code

An exact PSGC code match across releases is strong candidate evidence.

Before recommending an automatic match, compare:

- Geographic level
- Name
- Correspondence code
- Resolved parent, where available
- Other source attributes relevant to the geographic unit

An exact code match must be sent for review when material conflicts suggest possible code reuse, reassignment, or a change in the identity represented by the code.

An exact code match must not override authoritative evidence of a split, merger, replacement, or other identity-changing event.

### 5.2 Changed PSGC code

When the PSGC code changes, candidate generation may consider:

- Correspondence code
- Name and old names
- Geographic level
- Parent entity
- Official source notes
- Laws, ordinances, plebiscite results, and other authoritative change documents

A changed code alone is neither proof of continuity nor proof of a new entity.

Do not automatically match records solely because their names are identical.

### 5.3 Changed name

A name change does not automatically establish a new entity.

A candidate may be considered when the PSGC code remains stable or when authoritative evidence establishes continuity.

The original names must remain available in their respective release versions.

### 5.4 Changed geographic level

A change in geographic level requires explicit evaluation.

For example, the SGA records classified as `SGU` in 1Q 2024 and `Mun` in later releases must not be rewritten to use the later classification in the earlier release.

A geographic-level change may represent an administrative reorganization, a change in source classification, or another event. The correct interpretation must be supported by evidence.

### 5.5 Changed parent relationship

A change in parent does not automatically create a new entity.

If authoritative evidence establishes that the same geographic unit was administratively reassigned, retain its `entity_id` and record the new release-specific parent relationship.

Do not infer reassignment from code prefixes or worksheet ordering.

### 5.6 Correspondence code

A correspondence code may help generate candidates, but it must never be treated as a permanent entity identifier.

The implementation must not:

- Assume correspondence codes are unique.
- Assume every source record has one.
- Generate a missing correspondence code.
- Automatically merge all records sharing one correspondence code.

## 6. Automatic decisions and human review

Automatic matching must be conservative and limited to cases covered by explicit, version-controlled rules.

### 6.1 Conditions for automatic matching

An automatic match may be considered when:

- The PSGC code is identical across the compared releases.
- The geographic levels are compatible.
- No material source-attribute conflict is detected.
- No competing candidate exists.
- No known split, merger, code reuse, or identity-changing event conflicts with the match.

The exact definition of compatible levels and material conflicts must be implemented as explicit rules and covered by tests.

Changed-code matches must require an approved rule supported by authoritative evidence. They must not be automatically accepted based only on matching names or correspondence codes.

### 6.2 Mandatory human review

Human review is required when:

- The PSGC code changes and continuity is not established by an approved rule.
- Multiple candidates exist.
- Evidence conflicts.
- A split, merger, or replacement is suspected.
- Geographic-level changes are unexplained.
- Parent changes may represent more than an administrative reassignment.
- The source data does not provide enough information to distinguish continuity from a new entity.

### 6.3 Review decisions

A review decision must record:

- The source record or candidate pair being reviewed.
- The selected disposition.
- The evidence considered.
- The reviewer's rationale.
- The reviewer identity.
- The decision timestamp.
- The identity-resolution rule or contract version, if applicable.

A decision must be reproducible and auditable.

Changing an earlier decision must create an audit record. It must not silently erase the previous decision or its rationale.

## 7. Splits, mergers, and other changes

Not every geographic change can be represented as a one-to-one continuation.

The project must represent relationships between entities separately from entity identity.

### 7.1 Split

A split occurs when one prior entity gives rise to two or more successor entities.

- Do not assign the predecessor's `entity_id` to multiple successor entities.
- Create distinct entity identities for successor entities when the evidence establishes that they are distinct.
- Record the predecessor-to-successor relationships.
- Record the supporting authority and effective date when available.

### 7.2 Merger

A merger occurs when two or more prior entities give rise to one successor entity.

- Do not assign multiple predecessor `entity_id` values to one successor entity.
- Establish a distinct successor identity when the evidence establishes a new combined entity.
- Record each predecessor-to-successor relationship.
- Preserve all predecessor versions.

### 7.3 Administrative reassignment

A geographic unit may be assigned to a different parent without becoming a different entity.

When continuity is supported:

- Retain the existing `entity_id`.
- Record the changed parent relationship in the applicable release.
- Preserve the prior parent relationship in earlier releases.
- Record supporting evidence when the change requires review.

### 7.4 Code or name replacement

A code or name replacement does not automatically imply a split, merger, or new entity.

Use the evidence and matching rules to determine whether the entity continues, changes, or requires review.

### 7.5 Entity relationship records

Relationships between distinct entities must be stored separately from entity versions.

The relationship model must support, at minimum:

- Relationship type
- Source entity
- Target entity
- Applicable release or effective period, when known
- Supporting evidence
- Review disposition
- Decision rationale

Initial relationship types may include:

- `SPLIT_INTO`
- `MERGED_INTO`
- `REPLACED_BY`
- `RELATED_TO`

These are project-defined relationship types, not PSA source classifications.

Do not use a relationship type to imply an official lifecycle status that the source does not establish.

## 8. Absence and lifecycle limitations

A source record missing from a later release must not automatically be classified as abolished, inactive, or dissolved.

The project must distinguish:

- Not present in a particular release.
- Identity unresolved.
- Officially abolished or dissolved, when supported by authoritative evidence.
- Superseded or replaced, when supported by authoritative evidence.

Absence is an observation about a release, not a lifecycle decision.

Do not create synthetic entity versions to fill gaps between releases.

Do not invent effective dates or lifecycle events.

## 9. Initial SGA identity-resolution cases

The inspected releases contain three SGA barangay code changes:

| Barangay | 1Q 2024 PSGC | 4Q 2024 PSGC |
|---|---|---|
| Dunguan | `1999908003` | `1999904007` |
| Macabual | `1999907007` | `1999908009` |
| Panicupan | `1999906008` | `1999908010` |

Their names and correspondence codes remained unchanged in the inspected releases.

These records must be generated as identity-resolution candidates.

The unchanged names and correspondence codes are supporting evidence only. They do not independently authorize automatic matching.

The final identity decision must be supported by reviewed evidence. Until then, the records must remain unresolved rather than being silently merged or assigned unrelated new identities.

The eight SGA records changing from `SGU` to `Mun` must retain their source geographic levels in each release. A classification change alone does not establish a new entity.

## 10. Release publication requirements

Before a release is promoted for public API use:

1. Every source record must have a documented final assignment state.
2. Every source record assigned to an entity must have an approved assignment decision and satisfy the cardinality constraints in Section 2.3.
3. Records with assignment state `UNRESOLVED` must remain traceable to their source records and must not be exposed through API behavior that requires a resolved entity identity or hierarchy.
4. Split, merger, and replacement relationships must have reviewed evidence or an explicit documented disposition explaining why they do not prevent promotion.
5. The original source values and release-specific entity versions must be retained without modification.
6. All candidate decisions, assignment states, review dispositions, and rule versions must be auditable.
7. The person responsible for the import must review and disposition all findings that could affect identity or hierarchy before promotion.

A release may be promoted with non-blocking unresolved records only when the reviewer documents the rationale and confirms that those records are excluded from API behavior requiring resolved identity or hierarchy.

A release must not be represented as fully identity-resolved when unresolved records remain.

The release-management contract must define the promotion workflow, reviewer authorization, audit records, and how unresolved records are represented or excluded in API responses.

## 11. Auditability and reproducibility

Identity resolution must be reproducible from:

- The original source workbooks.
- The source-data contract version.
- The identity-resolution contract version.
- The matching rule version.
- Candidate-generation results.
- Human review decisions and evidence.

A re-run using the same inputs and rule versions must not silently produce different identity assignments.

Rule changes must not silently rewrite previously approved identity decisions.

Any re-evaluation of historical decisions must produce an auditable change with its reason and supporting evidence.

## 12. Initial regression cases

Automated tests must cover at least:

1. Same PSGC code and compatible source attributes across releases.
2. Same PSGC code with conflicting geographic levels.
3. Same PSGC code with materially conflicting attributes.
4. Changed PSGC code with matching correspondence code.
5. Changed PSGC code with matching name only.
6. Changed name with stable PSGC code.
7. Changed geographic level.
8. Changed parent relationship.
9. Duplicate correspondence codes.
10. Multiple candidate matches.
11. One predecessor with multiple successors.
12. Multiple predecessors with one successor.
13. A source record absent from a later release.
14. Deferred and rejected review decisions.
15. Reviewer decision changes and audit history.
16. The three SGA barangay code changes listed in Section 9.

Tests must verify that unresolved cases are not silently converted into approved matches or invented lifecycle events.

## 13. Open implementation decisions

The following details must be finalized during schema and implementation design:

- Internal identifier format (`UUID` or another opaque identifier).
- Exact database representation of source records, entity versions, candidates, decisions, evidence, and entity relationships.
- Exact compatibility rules for geographic-level changes.
- Approved authoritative evidence sources and document-reference format.
- Whether identity review is performed entirely before loading or can be completed through a separate administrative workflow.
- Release publication behavior for records with non-blocking unresolved identity cases.

These implementation decisions must preserve the identity and auditability principles defined in this contract.
