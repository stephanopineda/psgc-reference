CREATE TABLE hierarchy_publications (
    release_id TEXT PRIMARY KEY,
    publication_status TEXT NOT NULL
        CHECK (publication_status IN ('PUBLISHED', 'WITHDRAWN')),
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    approved_edge_count INTEGER NOT NULL CHECK (approved_edge_count >= 0),
    published_at TEXT NOT NULL,
    publication_reference TEXT NOT NULL
        CHECK (length(trim(publication_reference)) > 0),

    FOREIGN KEY (release_id)
        REFERENCES releases (release_id)
);
