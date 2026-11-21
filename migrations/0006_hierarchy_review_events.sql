CREATE TABLE hierarchy_review_events (
    event_id TEXT PRIMARY KEY,
    hierarchy_id TEXT NOT NULL,
    previous_status TEXT NOT NULL
        CHECK (previous_status = 'PROPOSED'),
    new_status TEXT NOT NULL
        CHECK (new_status IN ('APPROVED', 'REJECTED')),
    reviewed_by TEXT NOT NULL
        CHECK (length(trim(reviewed_by)) > 0),
    reviewed_at TEXT NOT NULL,
    decision_note TEXT NOT NULL
        CHECK (length(trim(decision_note)) > 0),

    FOREIGN KEY (hierarchy_id)
        REFERENCES record_hierarchy (hierarchy_id)
);

CREATE INDEX idx_hierarchy_review_events_hierarchy
    ON hierarchy_review_events (hierarchy_id, reviewed_at);

CREATE TRIGGER hierarchy_review_events_no_update
BEFORE UPDATE ON hierarchy_review_events
BEGIN
    SELECT RAISE(ABORT, 'hierarchy review events are immutable');
END;

CREATE TRIGGER hierarchy_review_events_no_delete
BEFORE DELETE ON hierarchy_review_events
BEGIN
    SELECT RAISE(ABORT, 'hierarchy review events are immutable');
END;
