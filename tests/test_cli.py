import sqlite3
from pathlib import Path

from csvsqlite.cli import main


def test_cli_import_export_roundtrip(tmp_path: Path, capsys):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
    db_path = tmp_path / "data.db"

    rc = main(["import", str(csv_path), "--db", str(db_path), "--table", "people"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 Zeilen" in out

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    conn.close()
    assert count == 2

    out_csv = tmp_path / "out.csv"
    rc = main(["export", "--db", str(db_path), "--table", "people", "--out", str(out_csv)])
    assert rc == 0
    assert out_csv.read_text(encoding="utf-8").splitlines()[0] == "id,name"


def test_cli_import_default_table_name(tmp_path: Path):
    csv_path = tmp_path / "widgets.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    db_path = tmp_path / "widgets.db"

    rc = main(["import", str(csv_path), "--db", str(db_path)])
    assert rc == 0

    conn = sqlite3.connect(str(db_path))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    conn.close()
    assert tables == ["widgets"]


def test_cli_tables_command(tmp_path: Path, capsys):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id\n1\n", encoding="utf-8")
    db_path = tmp_path / "data.db"
    main(["import", str(csv_path), "--db", str(db_path), "--table", "t1"])

    capsys.readouterr()
    rc = main(["tables", "--db", str(db_path)])
    assert rc == 0
    assert "t1" in capsys.readouterr().out


def test_cli_import_existing_table_fails_cleanly(tmp_path: Path, capsys):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id\n1\n", encoding="utf-8")
    db_path = tmp_path / "data.db"
    main(["import", str(csv_path), "--db", str(db_path), "--table", "t1"])

    capsys.readouterr()
    rc = main(["import", str(csv_path), "--db", str(db_path), "--table", "t1"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "existiert bereits" in err


def test_cli_schema_command(tmp_path: Path, capsys):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")
    db_path = tmp_path / "data.db"
    main(["import", str(csv_path), "--db", str(db_path), "--table", "t1"])

    capsys.readouterr()
    rc = main(["schema", "--db", str(db_path), "--table", "t1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "id" in out and "name" in out
