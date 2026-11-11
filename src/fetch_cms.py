"""Download the public CMS Medicare Telehealth Trends file and keep a tidy national subset.

Source: Centers for Medicare & Medicaid Services, "Medicare Telehealth Trends"
https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-service-type-reports/medicare-telehealth-trends

The full file (~3 MB) is saved to data/raw/ (git-ignored). A small tidy subset used by the
notebook and dashboard is written to data/external/cms_telehealth_national.csv and is
committed, so the project still runs offline if the download fails.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CMS_URL = "https://data.cms.gov/sites/default/files/2026-09/TMEDTREND_PUBLIC_260914.csv"
CMS_PAGE = ("https://data.cms.gov/summary-statistics-on-use-and-payments/"
            "medicare-medicaid-service-type-reports/medicare-telehealth-trends")
RAW_FILE = ROOT / "data" / "raw" / "TMEDTREND_PUBLIC_260914.csv"
TIDY_FILE = ROOT / "data" / "external" / "cms_telehealth_national.csv"


def download() -> bool:
    if RAW_FILE.exists():
        return True
    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(CMS_URL, headers={"User-Agent": "Mozilla/5.0 (portfolio fetch script)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            RAW_FILE.write_bytes(r.read())
        return True
    except Exception as exc:  # network not available, URL moved, etc.
        print(f"[cms] download failed ({exc}); using committed subset {TIDY_FILE.relative_to(ROOT)}.\n"
              f"      If the URL moved, get the current CSV link from {CMS_PAGE}")
        return False


def tidy(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep 'All' demographic slices for National and New York, by rurality and by age."""
    d = raw[raw.Bene_Geo_Desc.isin(["National", "New York"])
            & (raw.Bene_Mdcd_Mdcr_Enrl_Stus == "All") & (raw.Bene_Race_Desc == "All")
            & (raw.Bene_Sex_Desc == "All") & (raw.Bene_Mdcr_Entlmt_Stus == "All")]
    by_ruca = d[(d.Bene_Age_Desc == "All") & (d.Bene_RUCA_Desc.isin(["All", "Rural", "Urban"]))]
    by_ruca = by_ruca.assign(dimension="rurality", segment=by_ruca.Bene_RUCA_Desc)
    by_age = d[(d.Bene_RUCA_Desc == "All") & (d.Bene_Age_Desc != "All")]
    by_age = by_age.assign(dimension="age", segment=by_age.Bene_Age_Desc)
    out = pd.concat([by_ruca, by_age])
    out = out.rename(columns={"Year": "year", "quarter": "quarter", "Bene_Geo_Desc": "geography",
                              "Total_Bene_TH_Elig": "benes_telehealth_eligible",
                              "Total_Bene_Telehealth": "benes_using_telehealth",
                              "Pct_Telehealth": "pct_using_telehealth"})
    cols = ["geography", "year", "quarter", "dimension", "segment", "benes_telehealth_eligible",
            "benes_using_telehealth", "pct_using_telehealth"]
    return out[cols].dropna(subset=["pct_using_telehealth"]).sort_values(cols[:5]).reset_index(drop=True)


def main() -> None:
    if download():
        t = tidy(pd.read_csv(RAW_FILE))
        TIDY_FILE.parent.mkdir(parents=True, exist_ok=True)
        t.to_csv(TIDY_FILE, index=False)
        print(f"[cms] {len(t):,} tidy rows -> {TIDY_FILE.relative_to(ROOT)}")
    elif not TIDY_FILE.exists():
        sys.exit("[cms] no CMS data available (download failed and no committed subset).")


if __name__ == "__main__":
    main()
