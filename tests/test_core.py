import csv
import sqlite3
from pathlib import Path

import pytest

from csvsqlite.core import (
    ExportResult,
    ImportResult,
    TableExistsError,
    TableNotFoundError,
    export_sqlite_to_csv,
    import_csv_to_sqlite,
    infer_sqlite_type,
    list_tables,
)


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    p = tmp_path / "people.csv"
    p.write_text(
        "id,name,score,joined\n"
        "1,Alice,9.5,2024-01-01\n"
        "2,Bob,7,2024-02-15\n"
        "3,Carol,,2024-03-30\n",
        encoding="utf-8",
    )
    return p


def test_infer_sqlite_type_integer():
    assert infer_sqlite_type(["1", "2", "3"]) == "INTEGER"


def test_infer_sqlite_type_real():
    assert infer_sqlite_type(["1", "2.5", "3"]) == "REAL"


def test_infer_sqlite_type_text():
    assert infer_sqlite_type(["1", "abc", "3"]) == "TEXT"


def test_infer_sqlite_type_all_empty_defaults_text():
    assert infer_sqlite_type(["", "", ""]) == "TEXT"


def test_import_creates_table_with_inferred_types(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    result = import_csv_to_sqlite(sample_csv, db_path, table="people")

    assert isinstance(result, ImportResult)
    assert result.rows_imported == 3
    assert result.column_types["id"] == "INTEGER"
    assert result.column_types["score"] == "REAL"
    assert result.column_types["name"] == "TEXT"

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT id, name, score FROM people ORDER BY id").fetchall()
    conn.close()
    assert rows == [(1, "Alice", 9.5), (2, "Bob", 7.0), (3, "Carol", None)]


def test_import_no_infer_types_uses_text(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    result = import_csv_to_sqlite(sample_csv, db_path, table="people", infer_types=False)
    assert all(t == "TEXT" for t in result.column_types.values())


def test_import_fails_if_table_exists(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    import_csv_to_sqlite(sample_csv, db_path, table="people")
    with pytest.raises(TableExistsError):
        import_csv_to_sqlite(sample_csv, db_path, table="people", if_exists="fail")


def test_import_replace_overwrites_table(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    import_csv_to_sqlite(sample_csv, db_path, table="people")
    result = import_csv_to_sqlite(sample_csv, db_path, table="people", if_exists="replace")
    assert result.rows_imported == 3


def test_import_append_adds_rows(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    import_csv_to_sqlite(sample_csv, db_path, table="people")
    import_csv_to_sqlite(sample_csv, db_path, table="people", if_exists="append")

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    conn.close()
    assert count == 6


def test_import_semicolon_delimiter(tmp_path: Path):
    p = tmp_path / "semi.csv"
    p.write_text("a;b\n1;2\n3;4\n", encoding="utf-8")
    db_path = tmp_path / "semi.db"
    result = import_csv_to_sqlite(p, db_path, table="semi", delimiter=";")
    assert result.rows_imported == 2


def test_list_tables(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    import_csv_to_sqlite(sample_csv, db_path, table="people")
    assert list_tables(db_path) == ["people"]


def test_export_table_roundtrip(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    import_csv_to_sqlite(sample_csv, db_path, table="people")

    out_csv = tmp_path / "out.csv"
    result = export_sqlite_to_csv(db_path, out_csv, table="people")

    assert isinstance(result, ExportResult)
    assert result.rows_exported == 3
    with out_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["id", "name", "score", "joined"]
    assert len(rows) == 4


def test_export_table_not_found_raises(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    import_csv_to_sqlite(sample_csv, db_path, table="people")
    with pytest.raises(TableNotFoundError):
        export_sqlite_to_csv(db_path, tmp_path / "out.csv", table="ghost")


def test_export_with_query(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    import_csv_to_sqlite(sample_csv, db_path, table="people")
    out_csv = tmp_path / "out.csv"
    result = export_sqlite_to_csv(
        db_path, out_csv, query="SELECT name FROM people WHERE score > 8"
    )
    assert result.rows_exported == 1
    assert result.columns == ["name"]


def test_export_rejects_non_select_query(tmp_path: Path, sample_csv: Path):
    db_path = tmp_path / "test.db"
    import_csv_to_sqlite(sample_csv, db_path, table="people")
    from csvsqlite.core import CsvSqliteError

    with pytest.raises(CsvSqliteError):
        export_sqlite_to_csv(db_path, tmp_path / "out.csv", query="DROP TABLE people")
