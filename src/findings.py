"""Compute the headline findings from the SQLite database (used by the notebook, dashboard and README)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "clinic_kpi.db"
CMS = ROOT / "data" / "external" / "cms_telehealth_national.csv"


def q(con, sql):
    return pd.read_sql_query(sql, con)


def compute(db: Path = DB) -> dict:
    con = sqlite3.connect(db)
    att = q(con, """SELECT modality_scheduled m,
                    1.0*SUM(status='no_show')/SUM(status<>'cancelled') ns FROM appointments GROUP BY m""").set_index("m").ns
    lead = q(con, """SELECT CASE WHEN modality_scheduled='in_person' THEN 'in_person' ELSE 'virtual' END m,
                     AVG(lead_days) avg_lead, AVG(lead_days>14) over14
                     FROM appointments WHERE visit_type<>'acute' GROUP BY m""").set_index("m")
    clinic = q(con, """SELECT a.clinic_id, c.clinic_name,
                       1.0*SUM(status='no_show')/SUM(status<>'cancelled') ns,
                       AVG(CASE WHEN modality_scheduled='in_person' AND visit_type<>'acute' THEN lead_days END) ip_lead
                       FROM appointments a JOIN clinics c USING(clinic_id) GROUP BY a.clinic_id""").set_index("clinic_id")
    util = q(con, """SELECT p.clinic_id, 1.0*SUM(v.completed)/SUM(v.slots) util, SUM(v.slots) slots FROM providers p JOIN
                     (SELECT s.provider_id, SUM(s.slots) slots,
                             (SELECT COUNT(*) FROM appointments a WHERE a.provider_id=s.provider_id AND a.status='completed') completed
                      FROM provider_sessions s GROUP BY s.provider_id) v USING(provider_id) GROUP BY p.clinic_id""").set_index("clinic_id")
    eq = q(con, """SELECT p.rurality r,
                   1.0*SUM(a.modality_scheduled='audio')/SUM(a.modality_scheduled IN ('video','audio')) audio_share,
                   AVG(CASE WHEN a.modality_scheduled='video' AND a.status='completed' THEN a.video_fallback_to_audio END) fallback
                   FROM appointments a JOIN patients p USING(patient_id) GROUP BY r""").set_index("r")
    den = q(con, """SELECT CASE WHEN video_fallback_to_audio=1 THEN 'fallback' ELSE modality_delivered END k,
                    AVG(claim_denied) rate, SUM(charge_amount*claim_denied) denied FROM appointments
                    WHERE status='completed' GROUP BY k""").set_index("k")
    fu = q(con, """SELECT CASE WHEN video_fallback_to_audio=1 THEN 'fallback' ELSE modality_delivered END k,
                   AVG(inperson_followup_14d) rate FROM appointments
                   WHERE status='completed' AND modality_delivered IN ('video','audio') GROUP BY k""").set_index("k").rate
    vshare = q(con, """SELECT substr(appt_date,1,4) y, AVG(modality_delivered IN ('video','audio')) s
                       FROM appointments WHERE status='completed' GROUP BY y""").set_index("y").s
    con.close()

    others = clinic.drop(index="C05")
    peer_util = util.drop(index="C05").util.mean()
    lost_visits = (peer_util - util.loc["C05", "util"]) * util.loc["C05", "slots"] / 2  # per year
    cms = pd.read_csv(CMS)
    nat = cms[(cms.geography == "National") & (cms.dimension == "rurality") & (cms.quarter != "Overall")]
    latest = nat[nat.year == nat.year.max()].quarter.max()
    peak = nat[(nat.segment == "All")].sort_values("pct_using_telehealth").iloc[-1]
    last = nat[(nat.year == nat.year.max()) & (nat.quarter == latest)].set_index("segment").pct_using_telehealth

    f = {
        "network_virtual_share_2024": vshare["2024"], "network_virtual_share_2025": vshare["2025"],
        "no_show_in_person": att["in_person"], "no_show_video": att["video"], "no_show_audio": att["audio"],
        "lead_in_person": lead.loc["in_person", "avg_lead"], "lead_virtual": lead.loc["virtual", "avg_lead"],
        "over14_in_person": lead.loc["in_person", "over14"], "over14_virtual": lead.loc["virtual", "over14"],
        "c05_no_show": clinic.loc["C05", "ns"], "peer_no_show": others.ns.mean(),
        "c05_ip_lead": clinic.loc["C05", "ip_lead"], "peer_ip_lead": others.ip_lead.mean(),
        "c05_util": util.loc["C05", "util"], "peer_util": peer_util, "c05_lost_visits_per_year": lost_visits,
        "rural_audio_share": eq.loc["Rural", "audio_share"], "urban_audio_share": eq.loc["Urban", "audio_share"],
        "rural_fallback": eq.loc["Rural", "fallback"], "urban_fallback": eq.loc["Urban", "fallback"],
        "denial_in_person": den.loc["in_person", "rate"], "denial_video": den.loc["video", "rate"],
        "denial_audio": den.loc["audio", "rate"], "denial_fallback": den.loc["fallback", "rate"],
        "denied_charges_fallback": den.loc["fallback", "denied"],
        "followup_video": fu["video"], "followup_audio": fu["audio"], "followup_fallback": fu["fallback"],
        "cms_peak_pct": peak.pct_using_telehealth, "cms_peak_label": f"{peak.year} Q{peak.quarter}",
        "cms_latest_label": f"{nat.year.max()} Q{latest}", "cms_latest_all": last["All"],
        "cms_latest_rural": last["Rural"], "cms_latest_urban": last["Urban"],
    }
    f = {k: (round(float(v), 4) if not isinstance(v, str) else v) for k, v in f.items()}
    f["headlines"] = headlines(f)
    return f


def pct(x): return f"{x * 100:.1f}%"


def headlines(f: dict) -> list[dict]:
    return [
        {"title": "Virtual visits open access faster",
         "text": f"Non-acute virtual visits are booked {f['lead_virtual']:.1f} days out on average vs "
                 f"{f['lead_in_person']:.1f} days in person; {pct(f['over14_in_person'])} of in-person bookings wait more than 14 days "
                 f"vs {pct(f['over14_virtual'])} of virtual.",
         "action": "Offer a virtual slot first for chronic follow-ups when the next in-person slot is >14 days out."},
        {"title": "Virtual visits cut no-shows roughly in half",
         "text": f"No-show rate is {pct(f['no_show_in_person'])} in person vs {pct(f['no_show_video'])} video and "
                 f"{pct(f['no_show_audio'])} audio-only.",
         "action": "Target in-person reminder outreach at long-lead bookings, where no-shows concentrate."},
        {"title": "Riverbend (C05) is the clinic to fix first",
         "text": f"No-show {pct(f['c05_no_show'])} vs {pct(f['peer_no_show'])} peer average; in-person non-acute lead time "
                 f"{f['c05_ip_lead']:.1f} vs {f['peer_ip_lead']:.1f} days; provider utilization {pct(f['c05_util'])} vs "
                 f"{pct(f['peer_util'])} — about {f['c05_lost_visits_per_year']:,.0f} completed visits a year below peers.",
         "action": "Open template slots and add virtual capacity at C05; review its scheduling workflow."},
        {"title": "Rural patients hit a digital gap",
         "text": f"Audio-only is {pct(f['rural_audio_share'])} of rural virtual visits vs {pct(f['urban_audio_share'])} urban, "
                 f"and {pct(f['rural_fallback'])} of rural video visits fail over to audio vs {pct(f['urban_fallback'])} urban.",
         "action": "Run pre-visit tech checks / device support for rural and 75+ patients before video visits."},
        {"title": "Video→audio fallbacks leak revenue",
         "text": f"Fallback visits are denied {pct(f['denial_fallback'])} of the time vs {pct(f['denial_video'])} for video and "
                 f"{pct(f['denial_in_person'])} in person (${f['denied_charges_fallback']:,.0f} denied), and "
                 f"{pct(f['followup_fallback'])} need an in-person visit within 14 days.",
         "action": "Add a coding check that updates modality/modifier when a video visit drops to audio."},
    ]


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
