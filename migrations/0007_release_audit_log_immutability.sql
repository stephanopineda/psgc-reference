CREATE TRIGGER release_audit_log_no_update
BEFORE UPDATE ON release_audit_log
BEGIN
    SELECT RAISE(ABORT, 'release audit log entries are immutable');
END;

CREATE TRIGGER release_audit_log_no_delete
BEFORE DELETE ON release_audit_log
BEGIN
    SELECT RAISE(ABORT, 'release audit log entries are immutable');
END;
