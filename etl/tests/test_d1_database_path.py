"""Tests for resolving the active Wrangler local D1 database."""

import pytest

from psgc_etl.load import d1_loader


def test_database_path_ignores_backup_snapshots(tmp_path, monkeypatch):
    active = tmp_path / "database.sqlite"

    for filename in (
        "database.sqlite",
        "database-pre-0004.sqlite",
        "database-pre-vacuum.sqlite",
        "database-versioning-backup.sqlite",
        "metadata.sqlite",
    ):
        (tmp_path / filename).touch()

    monkeypatch.setattr(d1_loader, "D1_LOCAL_DIR", tmp_path)

    assert d1_loader._database_path() == active


def test_database_path_rejects_multiple_active_databases(
    tmp_path, monkeypatch
):
    (tmp_path / "database-a.sqlite").touch()
    (tmp_path / "database-b.sqlite").touch()

    monkeypatch.setattr(d1_loader, "D1_LOCAL_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="Expected exactly one"):
        d1_loader._database_path()


def test_database_path_rejects_no_active_database(tmp_path, monkeypatch):
    (tmp_path / "database-pre-backup.sqlite").touch()

    monkeypatch.setattr(d1_loader, "D1_LOCAL_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="Expected exactly one"):
        d1_loader._database_path()
