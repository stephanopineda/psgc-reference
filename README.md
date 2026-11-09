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

API setup instructions will be added when the API project is initialized.

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

Repository restructuring and source-data analysis are in progress.
The production ETL pipeline, database schema, and API have not yet been
implemented.
