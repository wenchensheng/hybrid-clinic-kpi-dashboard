-- SQLite schema for the SYNTHETIC hybrid primary-care dataset.
DROP TABLE IF EXISTS appointments;
DROP TABLE IF EXISTS provider_sessions;
DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS providers;
DROP TABLE IF EXISTS clinics;

CREATE TABLE clinics (
    clinic_id    TEXT PRIMARY KEY,
    clinic_name  TEXT NOT NULL,
    setting      TEXT NOT NULL CHECK (setting IN ('Urban', 'Suburban', 'Rural'))
);

CREATE TABLE providers (
    provider_id        TEXT PRIMARY KEY,
    clinic_id          TEXT NOT NULL REFERENCES clinics (clinic_id),
    role               TEXT NOT NULL CHECK (role IN ('MD', 'NP')),
    slots_per_session  INTEGER NOT NULL
);

CREATE TABLE patients (
    patient_id      TEXT PRIMARY KEY,
    home_clinic_id  TEXT NOT NULL REFERENCES clinics (clinic_id),
    age_band        TEXT NOT NULL,
    rurality        TEXT NOT NULL CHECK (rurality IN ('Rural', 'Urban')),
    payer           TEXT NOT NULL
);

-- One row per provider clinic day; slots = bookable capacity.
CREATE TABLE provider_sessions (
    provider_id   TEXT NOT NULL REFERENCES providers (provider_id),
    session_date  TEXT NOT NULL,
    slots         INTEGER NOT NULL,
    PRIMARY KEY (provider_id, session_date)
);

CREATE TABLE appointments (
    appt_id                  TEXT PRIMARY KEY,
    patient_id               TEXT NOT NULL REFERENCES patients (patient_id),
    clinic_id                TEXT NOT NULL REFERENCES clinics (clinic_id),
    provider_id              TEXT NOT NULL REFERENCES providers (provider_id),
    scheduled_date           TEXT NOT NULL,
    appt_date                TEXT NOT NULL,
    lead_days                INTEGER NOT NULL CHECK (lead_days >= 0),
    visit_type               TEXT NOT NULL,
    modality_scheduled       TEXT NOT NULL CHECK (modality_scheduled IN ('in_person', 'video', 'audio')),
    modality_delivered       TEXT,            -- NULL unless completed; video can fall back to audio
    status                   TEXT NOT NULL CHECK (status IN ('completed', 'no_show', 'cancelled')),
    video_fallback_to_audio  INTEGER NOT NULL CHECK (video_fallback_to_audio IN (0, 1)),
    inperson_followup_14d    INTEGER NOT NULL CHECK (inperson_followup_14d IN (0, 1)),
    charge_amount            REAL NOT NULL,
    claim_denied             INTEGER NOT NULL CHECK (claim_denied IN (0, 1))
);

CREATE INDEX ix_appt_month ON appointments (substr(appt_date, 1, 7));
CREATE INDEX ix_appt_clinic ON appointments (clinic_id);
