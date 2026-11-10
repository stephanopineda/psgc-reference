CREATE TABLE source_record_versions (
    version_id TEXT PRIMARY KEY
        CHECK (length(version_id) = 64),

    psgc_code TEXT NOT NULL
        CHECK (length(psgc_code) = 10),

    name TEXT NOT NULL,
    correspondence_code TEXT,
    geographic_level TEXT,
    old_names TEXT,
    city_class TEXT,
    income_classification TEXT,
    urban_rural TEXT,
    population INTEGER
        CHECK (population IS NULL OR population >= 0),
    population_annotation TEXT,
    source_status_value TEXT,

    source_values_json TEXT NOT NULL
        CHECK (json_valid(source_values_json)),

    normalization_events_json TEXT NOT NULL
        CHECK (json_valid(normalization_events_json)),

    UNIQUE (version_id, psgc_code)
);

CREATE INDEX ix_source_record_versions_code
    ON source_record_versions (psgc_code);

CREATE TABLE source_record_version_memberships (
    release_id TEXT NOT NULL,
    psgc_code TEXT NOT NULL,
    version_id TEXT NOT NULL,

    PRIMARY KEY (release_id, psgc_code),

    FOREIGN KEY (release_id, psgc_code)
        REFERENCES source_records (release_id, psgc_code),

    FOREIGN KEY (version_id, psgc_code)
        REFERENCES source_record_versions (version_id, psgc_code)
);

CREATE INDEX ix_source_record_version_memberships_version
    ON source_record_version_memberships (version_id);
