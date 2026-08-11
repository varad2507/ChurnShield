CREATE TABLE IF NOT EXISTS companies (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sector      TEXT NOT NULL DEFAULT 'ecommerce'
);

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL REFERENCES companies(id),
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'admin'
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id               TEXT PRIMARY KEY,
    company_id       TEXT NOT NULL,
    actor_id         TEXT,
    action_type      TEXT,
    entity_affected  TEXT,
    previous_state   TEXT,
    new_state        TEXT,
    ip_address       TEXT,
    timestamp        TEXT
);

CREATE TABLE IF NOT EXISTS notification_logs (
    id               TEXT PRIMARY KEY,
    company_id       TEXT NOT NULL,
    customer_id      TEXT,
    customer_name    TEXT,
    channel          TEXT,
    recipient        TEXT,
    subject          TEXT,
    body             TEXT,
    status           TEXT,
    triggered_score  REAL,
    sent_at          TEXT
);

CREATE TABLE IF NOT EXISTS notification_settings (
    company_id           TEXT PRIMARY KEY REFERENCES companies(id),
    high_risk_threshold  REAL    DEFAULT 75.0,
    email_enabled        INTEGER DEFAULT 1,
    sms_enabled          INTEGER DEFAULT 1,
    cooling_off_hours    INTEGER DEFAULT 24,
    email_recipient      TEXT,
    sms_recipient        TEXT
);

CREATE TABLE IF NOT EXISTS file_uploads (
    id           TEXT PRIMARY KEY,
    company_id   TEXT NOT NULL,
    name         TEXT,
    uploader     TEXT,
    timestamp    TEXT,
    size         TEXT,
    status       TEXT DEFAULT 'Processed',
    record_count INTEGER DEFAULT 0
);
