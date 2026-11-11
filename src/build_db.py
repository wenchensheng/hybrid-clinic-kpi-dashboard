"""Load the clean synthetic tables into SQLite and run every KPI query in sql/kpi_queries.sql."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "clinic_kpi.db"
KPI_DIR = ROOT / "reports" / "kpi"


def load_queries(path: Path = ROOT / "sql" / "kpi_queries.sql") -> dict[str, str]:
    parts = re.split(r"^-- name:\s*(\w+)\s*$", path.read_text(), flags=re.M)
    return {name: sql.strip() for name, sql in zip(parts[1::2], parts[2::2])}


def build() -> Path:
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    con.executescript((ROOT / "sql" / "schema.sql").read_text())
    raw, proc = ROOT / "data" / "raw", ROOT / "data" / "processed"
    tables = {"clinics": raw / "clinics.csv", "providers": raw / "providers.csv",
              "patients": raw / "patients.csv", "provider_sessions": raw / "provider_sessions.csv",
              "appointments": proc / "appointments_clean.csv"}
    for name, path in tables.items():
        pd.read_csv(path).to_sql(name, con, if_exists="append", index=False)
    con.commit()
    KPI_DIR.mkdir(parents=True, exist_ok=True)
    queries = load_queries()
    for name, sql in queries.items():
        pd.read_sql_query(sql, con).to_csv(KPI_DIR / f"{name}.csv", index=False)
    con.close()
    print(f"[sql] built {DB.relative_to(ROOT)} and ran {len(queries)} KPI queries -> {KPI_DIR.relative_to(ROOT)}/")
    return DB


if __name__ == "__main__":
    build()
