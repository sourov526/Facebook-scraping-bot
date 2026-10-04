import csv
import os
import tempfile
from pathlib import Path

COLUMNS = ["page_name", "page_url", "website_url", "email", "source_url", "status", "error_reason", "collected_at"]


def safe_cell(value):
    value = str(value)
    # Protect every untrusted column, including formulas hidden behind whitespace.
    probe = value.lstrip(" \t\r\n\ufeff\x00\v\f")
    if probe.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def export_csv(storage, keys, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
            writer.writerow(COLUMNS)
            for row in storage.rows(keys):
                writer.writerow([safe_cell(cell) for cell in row])
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
