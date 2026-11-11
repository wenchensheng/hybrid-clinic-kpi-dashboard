"""Generate a SYNTHETIC hybrid primary-care visit dataset (Jan 2024 - Dec 2025).

Everything here is fictional: clinics, providers, patients and visits are
simulated with a fixed random seed. No real patient or organization data is used.

Patterns are baked in on purpose so the analysis has explainable signal:
  * virtual visits (video / audio-only) have shorter lead times and fewer no-shows
  * rural patients rely more on audio-only and see more video-call failures
  * video visits that fail and fall back to audio carry a higher claim-denial rate
  * one clinic (C05 Riverbend) underperforms on access and attendance
A small share of data-quality defects is injected into the raw file so the
cleaning pipeline has something real to catch.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SEED = 42
START, END = "2024-01-01", "2025-12-31"

CLINICS = pd.DataFrame(
    [
        ("C01", "Harborside Family Medicine", "Urban"),
        ("C02", "Maple Grove Primary Care", "Suburban"),
        ("C03", "Eastbrook Internal Medicine", "Urban"),
        ("C04", "Pine Hollow Community Health", "Rural"),
        ("C05", "Riverbend Primary Care", "Suburban"),
        ("C06", "Cedar Ridge Family Health", "Rural"),
    ],
    columns=["clinic_id", "clinic_name", "setting"],
)
AGE_BANDS = ["0-17", "18-44", "45-64", "65-74", "75+"]
VISIT_TYPES = ["chronic_followup", "acute", "preventive", "new_patient"]


def make_providers(rng):
    rows, n = [], 1
    for cid in CLINICS.clinic_id:
        for role in ["MD", "MD", "NP"]:
            rows.append((f"P{n:02d}", cid, role, 16 if role == "MD" else 14))
            n += 1
    return pd.DataFrame(rows, columns=["provider_id", "clinic_id", "role", "slots_per_session"])


def make_patients(rng, per_clinic=2500):
    frames = []
    rural_p = {"Urban": 0.05, "Suburban": 0.20, "Rural": 0.75}
    for _, c in CLINICS.iterrows():
        n = per_clinic
        age = rng.choice(AGE_BANDS, n, p=[0.14, 0.30, 0.28, 0.16, 0.12])
        rural = np.where(rng.random(n) < rural_p[c.setting], "Rural", "Urban")
        payer = np.empty(n, dtype=object)
        senior = np.isin(age, ["65-74", "75+"])
        payer[senior] = rng.choice(["Medicare", "Commercial", "Medicaid"], senior.sum(), p=[0.82, 0.10, 0.08])
        payer[~senior] = rng.choice(["Commercial", "Medicaid", "Self-pay"], (~senior).sum(), p=[0.62, 0.30, 0.08])
        frames.append(pd.DataFrame({"clinic_id": c.clinic_id, "age_band": age, "rurality": rural, "payer": payer}))
    p = pd.concat(frames, ignore_index=True)
    p.insert(0, "patient_id", [f"PT{i:05d}" for i in range(1, len(p) + 1)])
    return p.rename(columns={"clinic_id": "home_clinic_id"})


def make_sessions(rng, providers):
    days = pd.bdate_range(START, END)
    rows = []
    for _, pr in providers.iterrows():
        day_off = rng.integers(0, 5)  # each provider works 4 weekdays
        for d in days:
            if d.weekday() == day_off or rng.random() < 0.05:  # PTO / admin days
                continue
            rows.append((pr.provider_id, d, pr.slots_per_session))
    return pd.DataFrame(rows, columns=["provider_id", "session_date", "slots"])


def make_appointments(rng, providers, patients, sessions):
    prov = providers.set_index("provider_id")
    sess = sessions.join(prov[["clinic_id"]], on="provider_id")
    fill = np.where(sess.clinic_id == "C05", 0.86, 0.93)
    booked = rng.binomial(sess.slots.to_numpy(), fill)
    a = sess.loc[sess.index.repeat(booked)].reset_index(drop=True)
    n = len(a)
    a = a.rename(columns={"session_date": "appt_date"}).drop(columns="slots")

    # patient from the clinic panel (older patients visit more often)
    w_age = {"0-17": 0.7, "18-44": 0.8, "45-64": 1.1, "65-74": 1.4, "75+": 1.6}
    pid = np.empty(n, dtype=object)
    for cid, idx in a.groupby("clinic_id").groups.items():
        panel = patients[patients.home_clinic_id == cid]
        w = panel.age_band.map(w_age).to_numpy()
        pid[idx] = rng.choice(panel.patient_id.to_numpy(), len(idx), p=w / w.sum())
    a["patient_id"] = pid
    a = a.merge(patients[["patient_id", "age_band", "rurality", "payer"]], on="patient_id", how="left")
    setting = a.clinic_id.map(CLINICS.set_index("clinic_id").setting)

    a["visit_type"] = rng.choice(VISIT_TYPES, n, p=[0.45, 0.25, 0.20, 0.10])

    # --- modality -------------------------------------------------------------
    t = ((a.appt_date.dt.year - 2024) * 12 + a.appt_date.dt.month - 1).to_numpy() / 23.0
    winter = a.appt_date.dt.month.isin([12, 1, 2]).to_numpy() * 0.03
    clinic_eff = a.clinic_id.map({"C01": 0.03, "C02": 0.0, "C03": 0.05, "C04": 0.02, "C05": -0.04, "C06": 0.01}).to_numpy()
    type_mult = a.visit_type.map({"chronic_followup": 1.45, "acute": 1.15, "preventive": 0.12, "new_patient": 0.45}).to_numpy()
    p_virtual = np.clip((0.21 + 0.06 * t + winter + clinic_eff) * type_mult, 0, 0.85)
    is_virtual = rng.random(n) < p_virtual
    audio_share = setting.map({"Urban": 0.18, "Suburban": 0.25, "Rural": 0.30}).to_numpy()
    audio_share = audio_share + (a.rurality == "Rural").to_numpy() * 0.18 + (a.age_band == "75+").to_numpy() * 0.15
    is_audio = is_virtual & (rng.random(n) < audio_share)
    a["modality_scheduled"] = np.where(~is_virtual, "in_person", np.where(is_audio, "audio", "video"))
    mod = a.modality_scheduled.to_numpy()

    # --- access: lead days ----------------------------------------------------
    mean_lead = np.select([mod == "in_person", mod == "video"], [11.0, 4.5], 3.5)
    mean_lead = mean_lead * np.where(a.clinic_id == "C05", np.where(mod == "in_person", 1.75, 1.3), 1.0)
    mean_lead = mean_lead * np.where(setting == "Rural", 1.15, 1.0)
    mean_lead = mean_lead * a.visit_type.map({"chronic_followup": 1.1, "acute": 0.35, "preventive": 1.6, "new_patient": 1.4}).to_numpy()
    lead = np.clip(np.round(rng.gamma(2.0, mean_lead / 2.0)), 0, 120).astype(int)
    a["lead_days"] = lead
    a["scheduled_date"] = a.appt_date - pd.to_timedelta(lead, unit="D")

    # --- attendance -----------------------------------------------------------
    p_cancel = 0.06 + (lead > 14) * 0.04
    p_ns = np.select([mod == "in_person", mod == "video"], [0.095, 0.055], 0.045)
    p_ns = p_ns + a.payer.map({"Medicaid": 0.04, "Self-pay": 0.03}).fillna(0).to_numpy()
    p_ns = p_ns + 0.0015 * lead + (a.clinic_id == "C05").to_numpy() * 0.06
    p_ns = p_ns + (a.age_band == "18-44").to_numpy() * 0.02 - (a.age_band == "75+").to_numpy() * 0.01
    p_ns = p_ns + ((mod == "in_person") & (a.rurality == "Rural")).to_numpy() * 0.025
    u = rng.random(n)
    a["status"] = np.where(u < p_cancel, "cancelled", np.where(u < p_cancel + p_ns, "no_show", "completed"))
    done = (a.status == "completed").to_numpy()

    # --- video -> audio fallback ----------------------------------------------
    p_fail = setting.map({"Urban": 0.05, "Suburban": 0.08, "Rural": 0.10}).to_numpy()
    p_fail = p_fail + (a.rurality == "Rural").to_numpy() * 0.06 + (a.age_band == "75+").to_numpy() * 0.06
    p_fail = p_fail + (a.clinic_id == "C05").to_numpy() * 0.05 - 0.02 * t
    fallback = done & (mod == "video") & (rng.random(n) < p_fail)
    a["video_fallback_to_audio"] = fallback.astype(int)
    a["modality_delivered"] = np.where(fallback, "audio", mod)
    a.loc[~done, "modality_delivered"] = None

    # --- virtual -> in-person follow-up within 14 days ------------------------
    p_fu = np.select([a.modality_delivered == "video", a.modality_delivered == "audio"], [0.09, 0.16], 0.0)
    p_fu = p_fu + (a.visit_type == "acute").to_numpy() * 0.08 + fallback * 0.05
    a["inperson_followup_14d"] = np.where(done & (mod != "in_person"), (rng.random(n) < p_fu).astype(int), 0)

    # --- revenue ----------------------------------------------------------------
    base = a.visit_type.map({"chronic_followup": 140, "acute": 120, "preventive": 190, "new_patient": 210}).to_numpy()
    mfac = np.select([a.modality_delivered == "in_person", a.modality_delivered == "video"], [1.0, 0.95], 0.62)
    charge = np.round(base * mfac * rng.normal(1.0, 0.08, n), 2)
    a["charge_amount"] = np.where(done, charge, 0.0)
    p_den = np.select([a.modality_delivered == "in_person", a.modality_delivered == "video"], [0.045, 0.06], 0.10)
    p_den = p_den + fallback * 0.09 + (a.payer == "Medicaid").to_numpy() * 0.03 + (a.clinic_id == "C05").to_numpy() * 0.03
    a["claim_denied"] = np.where(done, (rng.random(n) < p_den).astype(int), 0)

    a = a.sort_values(["appt_date", "provider_id"]).reset_index(drop=True)
    a.insert(0, "appt_id", [f"A{i:06d}" for i in range(1, len(a) + 1)])
    cols = ["appt_id", "patient_id", "clinic_id", "provider_id", "scheduled_date", "appt_date", "lead_days",
            "visit_type", "modality_scheduled", "modality_delivered", "status", "video_fallback_to_audio",
            "inperson_followup_14d", "charge_amount", "claim_denied"]
    a = a[cols]
    for c in ["scheduled_date", "appt_date"]:
        a[c] = a[c].dt.strftime("%Y-%m-%d")
    return a


def inject_defects(rng, a):
    """Add a small, known share of realistic data-entry defects to the raw extract."""
    a = a.copy().astype({"lead_days": "object", "charge_amount": "object"})
    n = len(a)
    pick = lambda k: rng.choice(n, k, replace=False)
    a.loc[pick(int(n * 0.002)), "patient_id"] = None
    a.loc[pick(int(n * 0.001)), "modality_scheduled"] = None
    a.loc[pick(int(n * 0.0008)), "appt_date"] = "2025-02-30"
    a.loc[pick(int(n * 0.0008)), "lead_days"] = -3
    a.loc[pick(int(n * 0.0006)), "charge_amount"] = 99999.0
    done_idx = np.flatnonzero(a.status.to_numpy() == "completed")
    a.loc[rng.choice(done_idx, int(n * 0.0005), replace=False), "status"] = "Completed "  # stray case/whitespace
    dups = a.loc[pick(int(n * 0.003))]
    return pd.concat([a, dups]).sample(frac=1.0, random_state=SEED).reset_index(drop=True)


def main(out_dir: Path = RAW):
    rng = np.random.default_rng(SEED)
    out_dir.mkdir(parents=True, exist_ok=True)
    providers = make_providers(rng)
    patients = make_patients(rng)
    sessions = make_sessions(rng, providers)
    appts = make_appointments(rng, providers, patients, sessions)
    raw = inject_defects(rng, appts)
    CLINICS.to_csv(out_dir / "clinics.csv", index=False)
    providers.to_csv(out_dir / "providers.csv", index=False)
    patients.to_csv(out_dir / "patients.csv", index=False)
    sessions.assign(session_date=sessions.session_date.dt.strftime("%Y-%m-%d")).to_csv(out_dir / "provider_sessions.csv", index=False)
    raw.to_csv(out_dir / "appointments_raw.csv", index=False)
    print(f"[generate] SYNTHETIC data written to {out_dir.relative_to(ROOT)}: "
          f"{len(patients):,} patients, {len(providers)} providers, {len(sessions):,} sessions, {len(raw):,} raw appointment rows")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
