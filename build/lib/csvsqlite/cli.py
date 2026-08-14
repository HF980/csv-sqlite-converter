"""Kommandozeilen-Interface für csv-sqlite-converter."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .core import (
    CsvSqliteError,
    export_sqlite_to_csv,
    get_table_schema,
    import_csv_to_sqlite,
    list_tables,
)

logger = logging.getLogger("csvsqlite")


def _add_common_io_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--delimiter",
        default=None,
        help="CSV-Trennzeichen (Standard: automatische Erkennung bzw. ',')",
    )
    parser.add_argument(
        "--encoding", default="utf-8", help="Zeichenkodierung der CSV-Datei (Standard: utf-8)"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csvsqlite",
        description="Konvertiert Daten bidirektional zwischen CSV-Dateien und SQLite-Datenbanken.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Ausführliche (DEBUG-)Logausgaben aktivieren"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- import ---------------------------------------------------------
    p_import = subparsers.add_parser(
        "import", help="CSV-Datei in eine SQLite-Tabelle importieren"
    )
    p_import.add_argument("csv_file", type=Path, help="Pfad zur CSV-Quelldatei")
    p_import.add_argument("--db", required=True, type=Path, help="Pfad zur SQLite-Datenbank")
    p_import.add_argument(
        "--table",
        default=None,
        help="Zieltabelle (Standard: Dateiname ohne Endung)",
    )
    p_import.add_argument(
        "--if-exists",
        choices=["fail", "replace", "append"],
        default="fail",
        help="Verhalten, wenn die Tabelle bereits existiert (Standard: fail)",
    )
    p_import.add_argument(
        "--no-infer-types",
        action="store_true",
        help="Typinferenz deaktivieren, alle Spalten als TEXT anlegen",
    )
    p_import.add_argument(
        "--chunksize", type=int, default=5000, help="Zeilen pro Batch-Insert (Standard: 5000)"
    )
    _add_common_io_args(p_import)

    # --- export ---------------------------------------------------------
    p_export = subparsers.add_parser(
        "export", help="SQLite-Tabelle (oder SELECT-Query) als CSV exportieren"
    )
    p_export.add_argument("--db", required=True, type=Path, help="Pfad zur SQLite-Datenbank")
    p_export.add_argument("--out", required=True, type=Path, help="Pfad zur Ziel-CSV-Datei")
    group = p_export.add_mutually_exclusive_group(required=True)
    group.add_argument("--table", help="Name der zu exportierenden Tabelle")
    group.add_argument("--query", help="Beliebige SELECT-Abfrage als Datenquelle")
    p_export.add_argument(
        "--delimiter", default=",", help="CSV-Trennzeichen für die Ausgabe (Standard: ',')"
    )
    p_export.add_argument(
        "--encoding", default="utf-8", help="Zeichenkodierung der Ausgabedatei (Standard: utf-8)"
    )

    # --- tables -----------------------------------------------------------
    p_tables = subparsers.add_parser("tables", help="Alle Tabellen einer SQLite-Datenbank auflisten")
    p_tables.add_argument("--db", required=True, type=Path, help="Pfad zur SQLite-Datenbank")

    # --- schema -----------------------------------------------------------
    p_schema = subparsers.add_parser("schema", help="Spaltenschema einer Tabelle anzeigen")
    p_schema.add_argument("--db", required=True, type=Path, help="Pfad zur SQLite-Datenbank")
    p_schema.add_argument("--table", required=True, help="Name der Tabelle")

    return parser


def _cmd_import(args: argparse.Namespace) -> int:
    table = args.table or args.csv_file.stem
    result = import_csv_to_sqlite(
        csv_path=args.csv_file,
        db_path=args.db,
        table=table,
        delimiter=args.delimiter,
        encoding=args.encoding,
        if_exists=args.if_exists,
        infer_types=not args.no_infer_types,
        chunksize=args.chunksize,
    )
    print(f"OK: {result.rows_imported} Zeilen in Tabelle '{result.table}' importiert ({args.db}).")
    print("Spalten:")
    for col in result.columns:
        print(f"  - {col}: {result.column_types.get(col, 'TEXT')}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    result = export_sqlite_to_csv(
        db_path=args.db,
        csv_path=args.out,
        table=args.table,
        query=args.query,
        delimiter=args.delimiter,
        encoding=args.encoding,
    )
    print(f"OK: {result.rows_exported} Zeilen nach '{result.csv_path}' exportiert.")
    print(f"Spalten: {', '.join(result.columns)}")
    return 0


def _cmd_tables(args: argparse.Namespace) -> int:
    tables = list_tables(args.db)
    if not tables:
        print("Keine Tabellen gefunden.")
        return 0
    for name in tables:
        print(name)
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    info = get_table_schema(args.db, args.table)
    print(f"Schema von '{args.table}':")
    for _cid, name, col_type, notnull, default, pk in info:
        flags = []
        if pk:
            flags.append("PRIMARY KEY")
        if notnull:
            flags.append("NOT NULL")
        if default is not None:
            flags.append(f"DEFAULT {default}")
        flag_str = f" ({', '.join(flags)})" if flags else ""
        print(f"  - {name}: {col_type}{flag_str}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    handlers = {
        "import": _cmd_import,
        "export": _cmd_export,
        "tables": _cmd_tables,
        "schema": _cmd_schema,
    }

    try:
        return handlers[args.command](args)
    except CsvSqliteError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - saubere Fehlermeldung für Nutzer
        if args.verbose:
            raise
        print(f"Unerwarteter Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
