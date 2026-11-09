ALTER TABLE releases
ADD COLUMN population_reference_year INTEGER;

ALTER TABLE releases
ADD COLUMN urban_rural_reference_year INTEGER;

ALTER TABLE releases
ADD COLUMN income_classification_basis TEXT;

ALTER TABLE releases
ADD COLUMN source_profile_id TEXT;

ALTER TABLE releases
ADD COLUMN extraction_profile_version TEXT;

UPDATE releases
SET
    population_reference_year = 2020,
    urban_rural_reference_year = 2020,
    source_profile_id = 'psa-legacy-2024-2025',
    extraction_profile_version = '1.0'
WHERE release_id IN ('2024-Q1', '2024-Q4', '2025-Q1');
