# Tableau companion workbook — Hybrid Clinic KPI Dashboard

This folder is the build spec for the Tableau version of the Hybrid Clinic
KPI Dashboard: a Tableau Desktop workbook that presents the same five
findings as the [live Plotly dashboard](https://wenchensheng.github.io/hybrid-clinic-kpi-dashboard/),
built entirely from this repository's committed outputs. It exists so a
Tableau-first audience (clinic leadership, BI reviewers) can open, filter
and re-cut the numbers without running the Python pipeline. Everything
needed to build the workbook — connections, sheet layouts, calculated
fields — is specified below; the data sources are committed in this repo.

## Data connections (no pipeline run required)

| Tableau connection | Source in this repo | Grain |
|---|---|---|
| `kpi_results` | [`reports/kpi/*.csv`](../reports/kpi) — the saved output of the 9 queries in [`sql/kpi_queries.sql`](../sql/kpi_queries.sql) | One CSV per KPI query (month × clinic × modality and related cuts) |
| `cms_telehealth` | [`data/external/cms_telehealth_national.csv`](../data/external/cms_telehealth_national.csv) | Quarter × geography × rurality × age band (CMS Medicare Telehealth Trends, tidy subset) |
| `appointments_sample` (optional, for row-level exploration) | [`data/sample/appointments_sample.csv`](../data/sample/appointments_sample.csv) | 500-row preview of the clean appointment table |

All clinic data is synthetic (seeded generator, `SEED=42`); the only real
data is the public CMS file. Relationships are defined on `clinic_id`,
`month` and `modality` between the KPI tables, matching the star-like
schema in [`sql/schema.sql`](../sql/schema.sql).

## Workbook structure

| Sheet | Mirrors | Content |
|---|---|---|
| `Overview` (dashboard) | Live dashboard home | KPI tiles: virtual share, no-show rate, days to appointment, provider utilization, denial rate — with clinic / modality / month filters wired to every sheet |
| `Access` | Finding 1 | Days-to-appointment bars by modality (virtual 5.1 days vs in-person 17.0), % booked >14 days out |
| `Attendance` | Finding 2 | No-show rate by modality and lead-time band (in-person 15.9% vs video 8.6% vs audio-only 7.2%) |
| `Clinic focus — Riverbend` | Finding 3 | C05 vs peer average on no-show rate, lead time and utilization, with the peer band highlighted |
| `Equity` | Finding 4 | Audio-only share and video→audio fallback by rurality and age band (rural fallback 14.6% vs urban 7.3%) |
| `Revenue leakage` | Finding 5 | Denial rate by delivered modality (fallback 20.5% vs video 7.3% vs in-person 5.6%) and 14-day in-person follow-up rate |
| `National context` | CMS framing | Medicare telehealth use by quarter from the CMS connection (peak 46.7% in 2020 Q2, ~12.7% in 2026 Q1), rural vs urban split |

## Calculated fields

The workbook uses the repo's canonical definitions (see
[KPI definitions](../README.md#kpi-definitions)) verbatim, e.g.:

- **Virtual share** = (video + audio-only delivered) ÷ completed visits
- **No-show rate** = no-shows ÷ (completed + no-shows) — cancellations excluded
- **Video→audio fallback** = video-scheduled visits delivered as audio-only ÷ completed video-scheduled visits
- **Provider utilization** = completed visits ÷ bookable slots
- **Claim denial rate** = denied claims ÷ completed visits

Because the KPI tables in `reports/kpi/` are already aggregated at these
definitions, most sheets plot stored measures directly; the calculated
fields are only needed when connecting at row level via
`appointments_sample` or a full clean extract.

## Rebuild / refresh

1. Run `python run_all.py` in the repo root (regenerates `reports/kpi/`).
2. In Tableau Desktop, refresh the `kpi_results` extracts — sheet values
   update in place; no field mapping changes are needed because the SQL
   output column names are stable.
3. The CMS connection only changes when `src/fetch_cms.py` pulls a newer
   CMS release file.

## Relationship to the other deliverables

- **Plotly dashboard** (`docs/`): the public, zero-install version.
- **Analysis notebook** (`notebooks/analysis.ipynb`): the auditable
  derivation of every number, with charts rendered on GitHub.
- **This workbook**: the Tableau presentation layer over the same,
  single-source KPI outputs — no number is computed twice.
