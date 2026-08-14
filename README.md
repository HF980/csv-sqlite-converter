# CSV-SQLite Converter

Ein robustes Kommandozeilen-Tool zur bidirektionalen Konvertierung von Daten zwischen CSV-Dateien und SQLite-Datenbanken.

## Funktionen

- **CSV → SQLite** – Importiert CSV-Dateien als SQLite-Tabelle.
- **SQLite → CSV** – Exportiert Tabellen oder das Ergebnis einer `SELECT`-Abfrage.
- **Automatische Typinferenz** – Erkennt `INTEGER`, `REAL` und `TEXT`.
- **Automatische Dialekterkennung** – Erkennt gängige CSV-Trennzeichen.
- **Tabellen anzeigen** – Listet alle Tabellen einer SQLite-Datenbank auf.
- **Schema anzeigen** – Zeigt das Schema einer Tabelle an.
- **Batch-Verarbeitung** – Geeignet für große CSV-Dateien.
- **Sicherer SQL-Export** – Bei `--query` sind ausschließlich `SELECT`-Abfragen erlaubt.

## Installation

### Voraussetzungen

- Python 3.10 oder höher
- pip

Repository klonen:

    git clone https://github.com/USERNAME/csv-sqlite-converter.git
    cd csv-sqlite-converter

Paket installieren:

    pip install

Für die Entwicklung inklusive Testabhängigkeiten:

    pip install -e ".[dev]"

Nach der Installation steht der Befehl 'csvsqlite' zur Verfügung:

    csvsqlite --help

## Verwendung

### CSV in SQLite importieren

    csvsqlite import daten.csv --db daten.db --table personen

Der Parameter '--table' ist optional. Ohne Angabe wird der Dateiname ohne Endung als Tabellenname verwendet.

### Import-Optionen

| Option | Beschreibung |
|---|---|
| '--db DB' | Pfad zur SQLite-Datenbank |
| '--table NAME' | Zieltabelle |
| '--if-exists {fail,replace,append}' | Verhalten bei vorhandener Tabelle |
| '--no-infer-types' | Alle Spalten als `TEXT` anlegen |
| '--chunksize N' | Zeilen pro Batch-Insert, Standard: 5000 |
| '--delimiter ZEICHEN' | CSV-Trennzeichen explizit festlegen |
| '--encoding NAME' | Zeichenkodierung, Standard: UTF-8 |

### Beispiel

CSV-Datei:

    name,alter
    Ali,30
    Maria,25
    Peter,41

Import:

    csvsqlite import personen.csv --db personen.db

Beispielausgabe:

    OK: 3 Zeilen in Tabelle 'personen' importiert
    Spalten:
      - name: TEXT
      - alter: INTEGER

## SQLite nach CSV exportieren

Eine komplette Tabelle exportieren:

    csvsqlite export --db daten.db --table personen --out export.csv

Alternativ kann das Ergebnis einer `SELECT`-Abfrage exportiert werden:

    csvsqlite export --db daten.db --query "SELECT name FROM personen WHERE score > 8" --out top.csv

### Export-Optionen

| Option | Beschreibung |
|---|---|
| '--db DB' | Pfad zur SQLite-Datenbank |
| '--out OUT' | Pfad zur Ziel-CSV-Datei |
| '--table TABLE' | Zu exportierende Tabelle |
| '--query QUERY' | SELECT-Abfrage als Datenquelle |
| '--delimiter ZEICHEN' | Trennzeichen der CSV-Ausgabe |
| '--encoding NAME' | Zeichenkodierung der Ausgabe |

'--table' und '--query' schließen sich gegenseitig aus.

## Tabellen auflisten

    csvsqlite tables --db daten.db

Beispiel:

    personen
    adressen
    bestellungen

## Schema anzeigen

    csvsqlite schema --db daten.db --table personen

Beispiel:

    Schema von 'personen':
      - name: TEXT
      - alter: INTEGER
      - gehalt: REAL

## Weitere Optionen

Allgemeine Hilfe:

    csvsqlite --help

Hilfe zum Import:

    csvsqlite import --help

Hilfe zum Export:

    csvsqlite export --help

Version anzeigen:

    csvsqlite --version

Ausführliche Debug-Logausgaben:

    csvsqlite -v import daten.csv --db daten.db

## Funktionsweise

### Automatische Dialekterkennung

Wenn kein Trennzeichen angegeben wird, versucht das Programm automatisch, den CSV-Dialekt zu erkennen.

Unterstützt werden unter anderem:

- ','
- ';'
- Tabulator
- '|'

Beispiel:

    csvsqlite import daten.csv --db daten.db --delimiter ";"

### Typinferenz

CSV-Spalten werden automatisch auf folgende SQLite-Typen geprüft:

- 'INTEGER'
- 'REAL'
- 'TEXT'

Leere Felder werden als `NULL` gespeichert.

Die Typinferenz kann deaktiviert werden:

    csvsqlite import daten.csv --db daten.db --no-infer-types

### Sichere Identifier

Spalten- und Tabellennamen werden für SQLite korrekt gequotet. Dadurch können auch Sonderzeichen und doppelte Spaltennamen sicher verarbeitet werden.

### Batch-Inserts

Große CSV-Dateien werden in konfigurierbaren Batches verarbeitet.

Standard:

    5000 Zeilen pro Batch

Beispiel:

    csvsqlite import daten.csv --db daten.db --chunksize 10000

### Sicherer Export

Bei Verwendung von '--query' sind ausschließlich 'SELECT'-Abfragen erlaubt.

Beispiel:

    csvsqlite export --db daten.db --query "SELECT * FROM personen" --out personen.csv

Operationen wie 'DROP', 'DELETE', 'UPDATE' oder 'INSERT' werden nicht als Exportabfrage akzeptiert.

### Fehlermanagement

Im normalen Betrieb werden verständliche Fehlermeldungen ausgegeben.

Für die Fehlersuche können ausführliche Debug-Informationen aktiviert werden:

    csvsqlite -v ...

## Tests

Entwicklungsabhängigkeiten installieren:

    pip install -e ".[dev]"

Tests ausführen:

    pytest

## Projektstruktur

    csv-sqlite-converter/
    ├── pyproject.toml
    ├── README.md
    ├── src/
    │   └── csvsqlite/
    │       ├── __init__.py
    │       ├── cli.py
    │       └── core.py
    └── tests/
        ├── test_core.py
        └── test_cli.py

## Lizenz

MIT
EOF
