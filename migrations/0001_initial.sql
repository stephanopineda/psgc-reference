PRAGMA foreign_keys = ON;

CREATE TABLE releases (
    release_id TEXT PRIMARY KEY,
    publication_date TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    source_size_bytes INTEGER NOT NULL CHECK (source_size_bytes > 0),
    worksheet_name TEXT NOT NULL,
    normalization_profile_version TEXT NOT NULL,
    record_count INTEGER NOT NULL CHECK (record_count >= 0),

    status TEXT NOT NULL DEFAULT 'IMPORTED'
        CHECK (status IN (
            'DISCOVERED',
            'ANALYZED',
            'IMPORTED',
            'IN_REVIEW',
            'READY_FOR_APPROVAL',
            'APPROVED',
            'PUBLISHED',
            'REJECTED',
            'SUPERSEDED',
            'WITHDRAWN'
        )),

    is_official_current INTEGER NOT NULL DEFAULT 0
        CHECK (is_official_current IN (0, 1)),

    imported_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (source_sha256)
);

CREATE UNIQUE INDEX ux_releases_official_current
    ON releases (is_official_current)
    WHERE is_official_current = 1;

CREATE INDEX ix_releases_publication_date
    ON releases (publication_date DESC);


CREATE TABLE source_records (
    release_id TEXT NOT NULL,
    psgc_code TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 0),

    name TEXT NOT NULL,
    correspondence_code TEXT,
    geographic_level TEXT,
    old_names TEXT,
    city_class TEXT,
    income_classification TEXT,
    urban_rural TEXT,
    population INTEGER CHECK (population IS NULL OR population >= 0),
    population_annotation TEXT,
    source_status_value TEXT,

    source_values_json TEXT NOT NULL
        CHECK (json_valid(source_values_json)),
    normalization_events_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(normalization_events_json)),

    PRIMARY KEY (release_id, psgc_code),
    UNIQUE (release_id, source_record_id),
    UNIQUE (release_id, source_row_number),

    FOREIGN KEY (release_id)
        REFERENCES releases (release_id)
);

CREATE INDEX ix_source_records_name
    ON source_records (release_id, name);

CREATE INDEX ix_source_records_correspondence
    ON source_records (release_id, correspondence_code);

CREATE INDEX ix_source_records_level
    ON source_records (release_id, geographic_level);

CREATE INDEX ix_source_records_population
    ON source_records (release_id, population);


CREATE TABLE entity_assignments (
    assignment_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    psgc_code TEXT NOT NULL,
    entity_id TEXT,
    assignment_status TEXT NOT NULL
        CHECK (assignment_status IN (
            'ASSIGNED_EXISTING_ENTITY',
            'ASSIGNED_NEW_ENTITY',
            'UNRESOLVED'
        )),
    decision_reference TEXT,
    rationale TEXT,
    assigned_by TEXT,
    assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (release_id, psgc_code),

    CHECK (
        (assignment_status = 'UNRESOLVED' AND entity_id IS NULL)
        OR
        (assignment_status IN (
            'ASSIGNED_EXISTING_ENTITY',
            'ASSIGNED_NEW_ENTITY'
        ) AND entity_id IS NOT NULL)
    ),

    FOREIGN KEY (release_id, psgc_code)
        REFERENCES source_records (release_id, psgc_code)
);

CREATE INDEX ix_entity_assignments_entity
    ON entity_assignments (entity_id);


CREATE TABLE record_hierarchy (
    hierarchy_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    parent_psgc_code TEXT NOT NULL,
    child_psgc_code TEXT NOT NULL,
    relationship_type TEXT NOT NULL DEFAULT 'PARENT_OF',
    evidence_reference TEXT,
    rationale TEXT,
    review_status TEXT NOT NULL DEFAULT 'PROPOSED'
        CHECK (review_status IN (
            'PROPOSED',
            'APPROVED',
            'REJECTED'
        )),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        release_id,
        parent_psgc_code,
        child_psgc_code,
        relationship_type
    ),

    CHECK (parent_psgc_code <> child_psgc_code),

    FOREIGN KEY (release_id, parent_psgc_code)
        REFERENCES source_records (release_id, psgc_code),

    FOREIGN KEY (release_id, child_psgc_code)
        REFERENCES source_records (release_id, psgc_code)
);

CREATE INDEX ix_record_hierarchy_child
    ON record_hierarchy (release_id, child_psgc_code);

CREATE INDEX ix_record_hierarchy_parent
    ON record_hierarchy (release_id, parent_psgc_code);


CREATE TABLE validation_findings (
    finding_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    psgc_code TEXT,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL
        CHECK (severity IN ('ERROR', 'WARNING', 'REVIEW')),
    message TEXT NOT NULL,
    disposition TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (disposition IN (
            'OPEN',
            'ACCEPTED',
            'RESOLVED',
            'EXCLUDED'
        )),
    disposition_rationale TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(evidence_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT,

    FOREIGN KEY (release_id)
        REFERENCES releases (release_id),

    FOREIGN KEY (release_id, psgc_code)
        REFERENCES source_records (release_id, psgc_code)
);

CREATE INDEX ix_validation_findings_release
    ON validation_findings (release_id, severity, disposition);


CREATE TABLE release_audit_log (
    audit_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT,
    actor TEXT NOT NULL,
    rationale TEXT,
    details_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(details_json)),
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (release_id)
        REFERENCES releases (release_id)
);

CREATE INDEX ix_release_audit_log_release
    ON release_audit_log (release_id, occurred_at);
