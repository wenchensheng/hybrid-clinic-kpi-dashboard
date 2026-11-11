# Data quality report (synthetic appointment extract)

- Raw rows: **100,978**
- Clean rows: **100,155** (99.18% of raw)
- Quarantined rows: **521** (see `data/processed/quarantine.csv`)

| Check | Rows flagged | Action |
|---|---:|---|
| exact duplicate rows | 302 | removed |
| duplicate appt_id | 0 | quarantine |
| modality_scheduled: whitespace/casing | 0 | repaired |
| status: whitespace/casing | 50 | repaired |
| visit_type: whitespace/casing | 0 | repaired |
| null appt_id | 0 | quarantine |
| null patient_id | 201 | quarantine |
| null clinic_id | 0 | quarantine |
| null provider_id | 0 | quarantine |
| null scheduled_date | 0 | quarantine |
| null appt_date | 0 | quarantine |
| null modality_scheduled | 100 | quarantine |
| null status | 0 | quarantine |
| invalid scheduled_date | 0 | quarantine |
| scheduled_date outside study window | 0 | quarantine |
| invalid appt_date | 80 | quarantine |
| appt_date outside study window | 0 | quarantine |
| scheduled_date after appt_date | 0 | quarantine |
| lead_days out of range [0,180] | 80 | quarantine |
| charge_amount out of range [0,2000] | 60 | quarantine |
| invalid modality_scheduled code | 0 | quarantine |
| invalid status code | 0 | quarantine |
| invalid visit_type code | 0 | quarantine |
| video_fallback_to_audio not 0/1 | 0 | quarantine |
| inperson_followup_14d not 0/1 | 0 | quarantine |
| claim_denied not 0/1 | 0 | quarantine |
| lead_days != date difference | 0 | repaired |

_Defects were injected on purpose by `src/generate_synthetic.py` to exercise these checks._
