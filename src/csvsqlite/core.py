"""Kernlogik für die Konvertierung zwischen CSV-Dateien und SQLite-Datenbanken."""

from __future__ import annotations

import csv
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

logger = logging.getLogger("csvsqlite")

# ---------------------------------------------------------------------------
# Fehlerklassen
# ---------------------------------------------------------------------------


class CsvSqliteError(Exception):
    """Basisklasse für alle erwarteten Fehler dieses Tools."""


class TableExistsError(CsvSqliteError):
    """Wird geworfen, wenn eine Zieltabelle bereits existiert und if_exists='fail' gilt."""


class TableNotFoundError(CsvSqliteError):
    """Wird geworfen, wenn eine angeforderte Tabelle nicht existiert."""


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

_IDENTIFIER_RE = re.compile(r"[^0-9A-Za-z_äöüÄÖÜß]+")


def sanitize_identifier(name: str, fallback: str = "column") -> str:
    """Wandelt einen beliebigen String in einen sicheren SQLite-Identifier um.

    SQLite-Identifier werden ohnehin über doppelte Anführungszeichen quotiert,
    trotzdem entfernen wir problematische Zeichen (Anführungszeichen, Leerraum
    am Rand) und stellen sicher, dass der Name nicht leer ist.
    """
    name = name.strip().replace('"', "'")
    if not name:
        return fallback
    return name


def quote_identifier(name: str) -> str:
    """Quotiert einen Identifier für SQLite (Tabellen-/Spaltennamen)."""
    return '"' + name.replace('"', '""') + '"'


def detect_dialect(sample: str, default_delimiter: str | None = None) -> csv.Dialect:
    """Ermittelt das CSV-Dialekt (Trennzeichen etc.) anhand einer Textprobe."""
    if default_delimiter:
        class _Fixed(csv.Dialect):
            delimiter = default_delimiter
            quotechar = '"'
            doublequote = True
            skipinitialspace = False
            lineterminator = "\r\n"
            quoting = csv.QUOTE_MINIMAL

        return _Fixed
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        logger.debug("CSV-Dialekt konnte nicht erkannt werden, verwende Komma als Trennzeichen.")
        return csv.excel


def infer_sqlite_type(values: Iterable[str]) -> str:
    """Leitet aus einer Menge von String-Werten den passenden SQLite-Spaltentyp ab.

    Reihenfolge der Prüfung: INTEGER -> REAL -> TEXT.
    Leere Werte (None/"") werden bei der Typprüfung ignoriert.
    """
    saw_value = False
    could_be_int = True
    could_be_real = True

    for raw in values:
        if raw is None or raw == "":
            continue
        saw_value = True
        if could_be_int:
            try:
                int(raw)
            except ValueError:
                could_be_int = False
        if could_be_real:
            try:
                float(raw)
            except ValueError:
                could_be_real = False
        if not could_be_int and not could_be_real:
            return "TEXT"

    if not saw_value:
        return "TEXT"
    if could_be_int:
        return "INTEGER"
    if could_be_real:
        return "REAL"
    return "TEXT"


def _convert_value(raw: str, sql_type: str) -> object:
    if raw == "" or raw is None:
        return None
    if sql_type == "INTEGER":
        try:
            return int(raw)
        except ValueError:
            return raw
    if sql_type == "REAL":
        try:
            return float(raw)
        except ValueError:
            return raw
    return raw


# ---------------------------------------------------------------------------
# CSV -> SQLite
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    table: str
    rows_imported: int
    columns: list[str]
    column_types: dict[str, str]


def import_csv_to_sqlite(
    csv_path: Path,
    db_path: Path,
    table: str,
    *,
    delimiter: str | None = None,
    encoding: str = "utf-8",
    if_exists: str = "fail",
    infer_types: bool = True,
    chunksize: int = 5000,
    sniff_sample_bytes: int = 65536,
) -> ImportResult:
    """Importiert eine CSV-Datei in eine SQLite-Tabelle.

    Args:
        csv_path: Pfad zur Quell-CSV-Datei.
        db_path: Pfad zur (ggf. neu anzulegenden) SQLite-Datenbank.
        table: Name der Zieltabelle.
        delimiter: Explizites Trennzeichen; bei None wird automatisch erkannt.
        encoding: Zeichenkodierung der CSV-Datei.
        if_exists: Verhalten bei bereits existierender Tabelle:
            "fail" (Fehler), "replace" (Tabelle löschen & neu anlegen),
            "append" (Zeilen anhängen, Schema muss passen).
        infer_types: Wenn True, werden Spaltentypen (INTEGER/REAL/TEXT) aus den
            Daten abgeleitet. Wenn False, wird alles als TEXT gespeichert.
        chunksize: Anzahl der Zeilen pro Batch-Insert.
        sniff_sample_bytes: Anzahl Bytes, die zur Dialekterkennung gelesen werden.

    Returns:
        ImportResult mit Statistiken zum Import.
    """
    if if_exists not in {"fail", "replace", "append"}:
        raise ValueError("if_exists muss 'fail', 'replace' oder 'append' sein")

    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV-Datei nicht gefunden: {csv_path}")

    with csv_path.open("r", newline="", encoding=encoding) as fh:
        sample = fh.read(sniff_sample_bytes)
        fh.seek(0)
        dialect = detect_dialect(sample, delimiter)
        reader = csv.reader(fh, dialect=dialect)

        try:
            header = next(reader)
        except StopIteration:
            raise CsvSqliteError(f"CSV-Datei ist leer: {csv_path}") from None

        seen: dict[str, int] = {}
        columns: list[str] = []
        for raw_name in header:
            name = sanitize_identifier(raw_name, fallback="column")
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 0
            columns.append(name)

        rows = list(reader)

    column_types: dict[str, str] = {}
    if infer_types:
        for idx, col in enumerate(columns):
            column_values = (row[idx] if idx < len(row) else "" for row in rows)
            column_types[col] = infer_sqlite_type(column_values)
    else:
        column_types = {col: "TEXT" for col in columns}

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,))
        exists = cur.fetchone() is not None

        if exists and if_exists == "fail":
            raise TableExistsError(
                f"Tabelle '{table}' existiert bereits in {db_path}. "
                "Nutze --if-exists replace oder --if-exists append."
            )
        if exists and if_exists == "replace":
            cur.execute(f"DROP TABLE {quote_identifier(table)}")
            exists = False

        if not exists:
            col_defs = ", ".join(
                f"{quote_identifier(c)} {column_types[c]}" for c in columns
            )
            cur.execute(f"CREATE TABLE {quote_identifier(table)} ({col_defs})")

        placeholders = ", ".join(["?"] * len(columns))
        col_list = ", ".join(quote_identifier(c) for c in columns)
        insert_sql = (
            f"INSERT INTO {quote_identifier(table)} ({col_list}) VALUES ({placeholders})"
        )

        total = 0
        batch: list[tuple] = []
        for row in rows:
            padded = list(row) + [""] * (len(columns) - len(row))
            converted = tuple(
                _convert_value(padded[i], column_types.get(columns[i], "TEXT"))
                for i in range(len(columns))
            )
            batch.append(converted)
            if len(batch) >= chunksize:
                cur.executemany(insert_sql, batch)
                total += len(batch)
                batch.clear()
        if batch:
            cur.executemany(insert_sql, batch)
            total += len(batch)

        conn.commit()
    finally:
        conn.close()

    return ImportResult(
        table=table, rows_imported=total, columns=columns, column_types=column_types
    )


# ---------------------------------------------------------------------------
# SQLite -> CSV
# ---------------------------------------------------------------------------


@dataclass
class ExportResult:
    csv_path: Path
    rows_exported: int
    columns: list[str]


def list_tables(db_path: Path) -> list[str]:
    """Listet alle Benutzertabellen einer SQLite-Datenbank."""
    if not db_path.is_file():
        raise FileNotFoundError(f"SQLite-Datenbank nicht gefunden: {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_table_schema(db_path: Path, table: str) -> list[tuple]:
    """Gibt die Spalteninfo (PRAGMA table_info) einer Tabelle zurück."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(f"PRAGMA table_info({quote_identifier(table)})")
        info = cur.fetchall()
        if not info:
            raise TableNotFoundError(f"Tabelle '{table}' nicht gefunden in {db_path}")
        return info
    finally:
        conn.close()


def export_sqlite_to_csv(
    db_path: Path,
    csv_path: Path,
    *,
    table: str | None = None,
    query: str | None = None,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> ExportResult:
    """Exportiert eine SQLite-Tabelle oder eine beliebige SELECT-Query als CSV.

    Es muss entweder `table` oder `query` angegeben werden.
    """
    if not table and not query:
        raise ValueError("Entweder 'table' oder 'query' muss angegeben werden")
    if table and query:
        raise ValueError("'table' und 'query' schließen sich gegenseitig aus")
    if not db_path.is_file():
        raise FileNotFoundError(f"SQLite-Datenbank nicht gefunden: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if table:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,))
            if cur.fetchone() is None:
                raise TableNotFoundError(f"Tabelle '{table}' nicht gefunden in {db_path}")
            sql = f"SELECT * FROM {quote_identifier(table)}"
        else:
            sql = query
            if re.match(r"^\s*(insert|update|delete|drop|alter|create)\b", sql, re.IGNORECASE):
                raise CsvSqliteError("Nur SELECT-Abfragen sind für den Export erlaubt")

        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description]

        csv_path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with csv_path.open("w", newline="", encoding=encoding) as fh:
            writer = csv.writer(fh, delimiter=delimiter)
            writer.writerow(columns)
            while True:
                chunk = cur.fetchmany(5000)
                if not chunk:
                    break
                writer.writerows(tuple(r) for r in chunk)
                total += len(chunk)
    finally:
        conn.close()

    return ExportResult(csv_path=csv_path, rows_exported=total, columns=columns)
