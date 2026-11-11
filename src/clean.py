"""Data-quality checks and cleaning for the raw (synthetic) appointment extract.

Checks: required-field nulls, duplicate rows / IDs, invalid or out-of-window dates,
date logic (scheduled after visit), out-of-range values and invalid category codes.
Rows that fail a critical check are quarantined (not silently dropped); fixable issues
(stray whitespace / casing in codes, lead_days inconsistent with dates) are repaired.
Outputs: data/processed/appointments_clean.csv, data/processed/quarantine.csv,
data/sample/appointments_sample.csv (500-row preview),
reports/data_quality_report.md
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "appointments_raw.csv"
OUT = ROOT / "data" / "processed"
REPORT = ROOT / "reports" / "data_quality_report.md"

REQUIRED = ["appt_id", "patient_id", "clinic_id", "provider_id", "scheduled_date", "appt_date",
            "modality_scheduled", "status"]
VALID = {"modality_scheduled": {"in_person", "video", "audio"},
         "status": {"completed", "no_show", "cancelled"},
         "visit_type": {"chronic_followup", "acute", "preventive", "new_patient"}}
WINDOW = (pd.Timestamp("2023-07-01"), pd.Timestamp("2025-12-31"))  # scheduling can precede Jan 2024
CHARGE_MAX = 2000


def run() -> pd.DataFrame:
    t0 = time.perf_counter()
    df = pd.read_csv(RAW, dtype=str)
    n_raw = len(df)
    checks, reason = [], pd.Series("", index=df.index)

    def flag(mask: pd.Series, label: str, critical: bool = True):
        checks.append((label, int(mask.sum()), "quarantine" if critical else "repaired"))
        if critical:
            reason.loc[mask & (reason == "")] = label

    # 1. exact duplicates, then duplicate IDs
    dup = df.duplicated(keep="first")
    checks.append(("exact duplicate rows", int(dup.sum()), "removed"))
    df, reason = df[~dup], reason[~dup]
    flag(df.appt_id.duplicated(keep="first"), "duplicate appt_id")

    # 2. normalize code fields (repairable)
    for c in VALID:
        clean = df[c].str.strip().str.lower()
        flag((clean != df[c]) & df[c].notna(), f"{c}: whitespace/casing", critical=False)
        df[c] = clean

    # 3. required nulls
    for c in REQUIRED:
        flag(df[c].isna(), f"null {c}")

    # 4. dates
    for c in ["scheduled_date", "appt_date"]:
        parsed = pd.to_datetime(df[c], format="%Y-%m-%d", errors="coerce")
        flag(parsed.isna() & df[c].notna(), f"invalid {c}")
        flag(parsed.notna() & ~parsed.between(*WINDOW), f"{c} outside study window")
        df[c] = parsed
    flag(df.scheduled_date > df.appt_date, "scheduled_date after appt_date")

    # 5. ranges / categories
    for c in ["lead_days", "charge_amount", "video_fallback_to_audio", "inperson_followup_14d", "claim_denied"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    flag(~df.lead_days.between(0, 180), "lead_days out of range [0,180]")
    flag(~df.charge_amount.between(0, CHARGE_MAX), f"charge_amount out of range [0,{CHARGE_MAX}]")
    for c, ok in VALID.items():
        flag(df[c].notna() & ~df[c].isin(ok), f"invalid {c} code")
    for c in ["video_fallback_to_audio", "inperson_followup_14d", "claim_denied"]:
        flag(~df[c].isin([0, 1]), f"{c} not 0/1")

    # 6. consistency repair: lead_days must equal the date difference
    calc = (df.appt_date - df.scheduled_date).dt.days
    mism = calc.notna() & df.lead_days.notna() & (calc != df.lead_days) & (reason == "")
    flag(mism, "lead_days != date difference", critical=False)
    df.loc[mism, "lead_days"] = calc[mism]

    bad = reason != ""
    quarantine = df[bad].assign(dq_reason=reason[bad])
    clean = df[~bad].copy()
    clean["lead_days"] = clean.lead_days.astype(int)
    for c in ["video_fallback_to_audio", "inperson_followup_14d", "claim_denied"]:
        clean[c] = clean[c].astype(int)

    OUT.mkdir(parents=True, exist_ok=True)
    clean.to_csv(OUT / "appointments_clean.csv", index=False, date_format="%Y-%m-%d")
    quarantine.to_csv(OUT / "quarantine.csv", index=False, date_format="%Y-%m-%d")
    sample = ROOT / "data" / "sample"
    sample.mkdir(exist_ok=True)  # small committed preview of the clean table for GitHub viewers
    clean.sample(500, random_state=7).sort_values("appt_id").to_csv(sample / "appointments_sample.csv", index=False, date_format="%Y-%m-%d")
    secs = time.perf_counter() - t0
    write_report(n_raw, len(clean), len(quarantine), checks, secs)
    print(f"[clean] {n_raw:,} raw -> {len(clean):,} clean, {len(quarantine):,} quarantined ({secs:.1f}s)")
    return clean


def write_report(n_raw, n_clean, n_quar, checks, secs):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Data quality report (synthetic appointment extract)", "",
             f"- Raw rows: **{n_raw:,}**", f"- Clean rows: **{n_clean:,}** ({n_clean / n_raw:.2%} of raw)",
             f"- Quarantined rows: **{n_quar:,}** (see `data/processed/quarantine.csv`)",
             "", "| Check | Rows flagged | Action |", "|---|---:|---|"]
    lines += [f"| {c} | {k:,} | {a} |" for c, k, a in checks]
    lines += ["", "_Defects were injected on purpose by `src/generate_synthetic.py` to exercise these checks._", ""]
    REPORT.write_text("\n".join(lines))


if __name__ == "__main__":
    run()
