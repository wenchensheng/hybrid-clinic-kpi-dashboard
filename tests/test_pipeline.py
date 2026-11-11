"""Smoke tests: data quality guarantees, every KPI query runs, and dashboard JSON is consistent."""
import json
import sqlite3
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from build_db import DB, load_queries  # noqa: E402


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = sqlite3.connect(DB)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_clean_data_has_no_defects(self):
        a = pd.read_csv(ROOT / "data" / "processed" / "appointments_clean.csv")
        self.assertFalse(a.appt_id.duplicated().any())
        self.assertFalse(a[["patient_id", "modality_scheduled", "status"]].isna().any().any())
        self.assertTrue(a.lead_days.between(0, 180).all())
        self.assertTrue(set(a.status) <= {"completed", "no_show", "cancelled"})

    def test_every_kpi_query_runs_and_returns_rows(self):
        for name, sql in load_queries().items():
            with self.subTest(query=name):
                self.assertGreater(len(pd.read_sql_query(sql, self.con)), 0)

    def test_dashboard_totals_match_database(self):
        d = json.loads((ROOT / "docs" / "data" / "dashboard.json").read_text())
        n_db = self.con.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
        self.assertEqual(sum(d["cube"]["scheduled"]), n_db)
        self.assertEqual(len(d["findings"]["headlines"]), 5)


if __name__ == "__main__":
    unittest.main()
