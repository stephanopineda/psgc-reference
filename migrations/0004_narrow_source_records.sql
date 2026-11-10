-- Payload attributes now live in source_record_versions.
-- source_records retains release membership and source-row provenance.

DROP INDEX IF EXISTS ix_source_records_name;
DROP INDEX IF EXISTS ix_source_records_correspondence;
DROP INDEX IF EXISTS ix_source_records_level;
DROP INDEX IF EXISTS ix_source_records_population;

ALTER TABLE source_records DROP COLUMN name;
ALTER TABLE source_records DROP COLUMN correspondence_code;
ALTER TABLE source_records DROP COLUMN geographic_level;
ALTER TABLE source_records DROP COLUMN old_names;
ALTER TABLE source_records DROP COLUMN city_class;
ALTER TABLE source_records DROP COLUMN income_classification;
ALTER TABLE source_records DROP COLUMN urban_rural;
ALTER TABLE source_records DROP COLUMN population;
ALTER TABLE source_records DROP COLUMN population_annotation;
ALTER TABLE source_records DROP COLUMN source_status_value;
ALTER TABLE source_records DROP COLUMN source_values_json;
ALTER TABLE source_records DROP COLUMN normalization_events_json;
