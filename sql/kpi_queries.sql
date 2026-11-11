-- KPI queries for the hybrid clinic dashboard (SQLite).
-- Each query starts with "-- name: <id>"; src/build_db.py runs every query and
-- saves the result to reports/kpi/<id>.csv.
-- Denominator conventions:
--   attended appointments = completed + no_show (cancellations excluded)
--   no-show rate          = no_show / attended appointments
--   virtual               = video + audio (by modality scheduled, unless stated)

-- name: monthly_virtual_share
SELECT substr(appt_date, 1, 7)                                              AS month,
       COUNT(*)                                                             AS completed_visits,
       ROUND(AVG(modality_delivered IN ('video', 'audio')), 4)              AS virtual_share,
       ROUND(AVG(modality_delivered = 'video'), 4)                          AS video_share,
       ROUND(AVG(modality_delivered = 'audio'), 4)                          AS audio_share
FROM appointments
WHERE status = 'completed'
GROUP BY month
ORDER BY month;

-- name: attendance_by_modality
SELECT modality_scheduled,
       COUNT(*)                                                             AS scheduled,
       ROUND(AVG(status = 'completed'), 4)                                  AS completion_rate,
       ROUND(AVG(status = 'cancelled'), 4)                                  AS cancel_rate,
       ROUND(1.0 * SUM(status = 'no_show') / SUM(status <> 'cancelled'), 4) AS no_show_rate
FROM appointments
GROUP BY modality_scheduled
ORDER BY no_show_rate DESC;

-- name: days_to_appointment
-- Access: lead time from booking to visit, excluding same-week acute visits.
WITH ranked AS (
    SELECT clinic_id, modality_scheduled, lead_days,
           ROW_NUMBER() OVER (PARTITION BY clinic_id, modality_scheduled ORDER BY lead_days) AS rn,
           COUNT(*)     OVER (PARTITION BY clinic_id, modality_scheduled)                    AS n
    FROM appointments
    WHERE visit_type <> 'acute'
)
SELECT r.clinic_id, c.clinic_name, r.modality_scheduled,
       MAX(r.n)                                                    AS appointments,
       ROUND(AVG(r.lead_days), 1)                                  AS avg_lead_days,
       MIN(CASE WHEN r.rn >= r.n / 2.0 THEN r.lead_days END)       AS median_lead_days,
       ROUND(AVG(r.lead_days > 14), 4)                             AS share_over_14_days
FROM ranked r JOIN clinics c USING (clinic_id)
GROUP BY r.clinic_id, r.modality_scheduled
ORDER BY r.clinic_id, r.modality_scheduled;

-- name: clinic_scorecard
SELECT a.clinic_id, c.clinic_name, c.setting,
       COUNT(*)                                                                     AS scheduled,
       ROUND(1.0 * SUM(a.status = 'no_show') / SUM(a.status <> 'cancelled'), 4)     AS no_show_rate,
       ROUND(AVG(a.lead_days), 1)                                                   AS avg_lead_days,
       ROUND(AVG(CASE WHEN a.status = 'completed'
                      THEN a.modality_delivered IN ('video', 'audio') END), 4)      AS virtual_share,
       ROUND(1.0 * SUM(a.claim_denied) / SUM(a.status = 'completed'), 4)            AS denial_rate,
       ROUND(SUM(a.charge_amount), 0)                                               AS gross_charges
FROM appointments a JOIN clinics c USING (clinic_id)
GROUP BY a.clinic_id
ORDER BY no_show_rate DESC;

-- name: provider_utilization
-- Utilization = completed visits / bookable slots; fill rate = booked / slots.
WITH cap AS (
    SELECT provider_id, SUM(slots) AS slots, COUNT(*) AS sessions
    FROM provider_sessions GROUP BY provider_id
), vol AS (
    SELECT provider_id, COUNT(*) AS booked, SUM(status = 'completed') AS completed
    FROM appointments GROUP BY provider_id
)
SELECT p.provider_id, p.clinic_id, p.role, cap.sessions, cap.slots, vol.booked, vol.completed,
       ROUND(1.0 * vol.booked / cap.slots, 4)    AS fill_rate,
       ROUND(1.0 * vol.completed / cap.slots, 4) AS utilization
FROM providers p JOIN cap USING (provider_id) JOIN vol USING (provider_id)
ORDER BY utilization;

-- name: video_fallback
-- Share of completed video visits that dropped to audio-only, by patient rurality and age.
SELECT p.rurality, p.age_band,
       COUNT(*)                                     AS completed_video_scheduled,
       ROUND(AVG(a.video_fallback_to_audio), 4)     AS fallback_rate
FROM appointments a JOIN patients p USING (patient_id)
WHERE a.status = 'completed' AND a.modality_scheduled = 'video'
GROUP BY p.rurality, p.age_band
ORDER BY p.rurality, p.age_band;

-- name: virtual_to_inperson_conversion
-- Completed virtual visits followed by an in-person visit within 14 days.
SELECT modality_delivered,
       CASE WHEN video_fallback_to_audio = 1 THEN 'video→audio fallback' ELSE 'as scheduled' END AS path,
       visit_type,
       COUNT(*)                                     AS completed_virtual,
       ROUND(AVG(inperson_followup_14d), 4)         AS inperson_within_14d
FROM appointments
WHERE status = 'completed' AND modality_delivered IN ('video', 'audio')
GROUP BY modality_delivered, path, visit_type
ORDER BY modality_delivered, path, visit_type;

-- name: denial_rate
SELECT modality_delivered,
       CASE WHEN video_fallback_to_audio = 1 THEN 'video→audio fallback' ELSE 'as scheduled' END AS path,
       COUNT(*)                                      AS claims,
       ROUND(AVG(claim_denied), 4)                   AS denial_rate,
       ROUND(AVG(charge_amount), 2)                  AS avg_charge,
       ROUND(SUM(charge_amount * claim_denied), 0)   AS denied_charges
FROM appointments
WHERE status = 'completed'
GROUP BY modality_delivered, path
ORDER BY denial_rate DESC;

-- name: equity_gaps
-- Access/attendance gaps by patient rurality and age band.
SELECT p.rurality, p.age_band,
       COUNT(*)                                                                         AS scheduled,
       ROUND(AVG(a.modality_scheduled IN ('video', 'audio')), 4)                        AS virtual_share,
       ROUND(1.0 * SUM(a.modality_scheduled = 'audio')
             / NULLIF(SUM(a.modality_scheduled IN ('video', 'audio')), 0), 4)           AS audio_share_of_virtual,
       ROUND(1.0 * SUM(a.status = 'no_show') / SUM(a.status <> 'cancelled'), 4)         AS no_show_rate,
       ROUND(1.0 * SUM(a.status = 'no_show' AND a.modality_scheduled = 'in_person')
             / SUM(a.status <> 'cancelled' AND a.modality_scheduled = 'in_person'), 4)  AS in_person_no_show_rate
FROM appointments a JOIN patients p USING (patient_id)
GROUP BY p.rurality, p.age_band
ORDER BY p.rurality, p.age_band;
