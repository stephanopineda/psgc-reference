# PSGC Reference

A versioned, machine-readable reference database and read-only API for the
Philippine Standard Geographic Code (PSGC), based on publications from the
Philippine Statistics Authority (PSA).

## Project Goals

- Ingest and validate PSA PSGC publication files.
- Preserve historical PSGC releases.
- Track changes to geographic entities across releases.
- Provide consistent lookup and search capabilities.
- Expose geographic reference data through a read-only REST API.
- Preserve source attribution and publication metadata.

## Project Structure

    .
    ├── api/                  # REST API (Cloudflare Workers / Hono)
    ├── data/
    │   ├── source/
    │   │   ├── psa/          # Original PSA publication files
    │   │   └── third_party/  # Supplementary reference sources
    │   └── processed/        # Generated ETL artifacts
    ├── docs/                 # Technical and project documentation
    ├── etl/                  # Python ETL package
    ├── legacy/               # Previous ETL implementation
    ├── migrations/           # Database schema migrations
    ├── spec/                 # API specifications
    └── .github/workflows/    # CI workflows

## Technology Stack

| Component | Technology |
|---|---|
| ETL | Python 3.12, Pandas, OpenPyXL |
| API | TypeScript, Hono, Cloudflare Workers |
| Database | Cloudflare D1 (SQLite) |
| API specification | OpenAPI 3.1 |
| ETL testing | Pytest |
| API testing | Vitest |

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 22+
- Git

### ETL

From the repository root:

    cd etl

    python3 -m venv .venv
    source .venv/bin/activate

    python -m pip install --upgrade pip
    python -m pip install -e ".[dev]"

Run ETL tests:

    python -m pytest

Run Ruff:

    python -m ruff check .

### API

Install dependencies from the repository root:

    npm install

Apply the D1 migrations to the local database:

    npm run db:migrate:local

Start the local Worker:

    npm run dev

The Worker uses the D1 binding configured in `wrangler.jsonc`. The local
database is stored in Wrangler's local state directory and is separate from
any remote Cloudflare D1 database.

Run API type checking and tests:

    npm run typecheck
    npm run test:api

The API tests use a mocked D1 binding and do not require a remote database.

#### API endpoints

All record queries require an explicit `release_id`. The API does not silently
select a latest release.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/healthz` | API and database health |
| GET | `/v1/releases` | List available releases and their publication metadata |
| GET | `/v1/releases/{releaseId}` | Release metadata and validation finding counts |
| GET | `/v1/geographic-levels?release_id={id}` | Geographic levels and record counts |
| GET | `/v1/records?release_id={id}` | Paginated record search |
| GET | `/v1/records/{psgcCode}?release_id={id}` | Record detail and source provenance |

Record search supports `q`, `geographic_level`, `city_class`,
`income_classification`, `urban_rural`, `page`, and `page_size`.
Page size is limited to 100 and search terms to 200 characters.

The record detail response includes the original source values and
normalization events. These are provenance data, not claims that every
source value has been independently verified.

The geographic-level endpoint groups records by their non-null geographic
levels. Records with a null geographic level are excluded from those groups
and reported separately as `meta.unclassified_record_count`.

The OpenAPI 3.1 document is maintained at `spec/openapi.yaml`.

Deployment requires a configured Cloudflare account and a real D1 database.
Do not deploy using the placeholder database ID in `wrangler.jsonc`.

## Source Data

Original PSA publication files are stored under `data/source/psa/`.

Each imported release must retain its publication metadata and source-file
integrity information. Source data must not be silently modified during
normalization or processing.

PSA source attribution and applicable use constraints must be observed.

## Data and Identity Principles

- PSGC codes and correspondence codes are distinct source identifiers.
- Codes must be preserved as strings.
- Historical releases must remain independently queryable.
- Missing records must not automatically be classified as abolished.
- Ambiguous entity identity changes require review.
- Source-provided values must be distinguished from system-derived values.

## Project Status

The repository includes a Python ETL pipeline, release comparison and
validation, SQLite/D1 migrations and local imports, and an initial read-only
Cloudflare Workers API. Four PSA source releases are currently imported into
the local D1 database. No release is designated as officially current.

Entity identity resolution, reviewed hierarchy data, publication approval
workflow, and production Cloudflare deployment remain future work.
