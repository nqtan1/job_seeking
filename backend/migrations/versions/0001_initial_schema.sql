-- Initial Schema Migration: 0001_initial_schema.sql

CREATE TABLE IF NOT EXISTS background_jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    result TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    extracted_data TEXT NOT NULL,  -- JSON string of CVInformation
    created_at TEXT NOT NULL,
    file_path TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_title TEXT NOT NULL,
    company TEXT NOT NULL,
    extracted_data TEXT NOT NULL,  -- JSON string of JobPosition
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fit_analyses (
    analysis_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    fit_score INTEGER NOT NULL,
    fit_data TEXT NOT NULL,        -- JSON string of FitCheck or analysis response
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    application_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    company_name TEXT NOT NULL,
    source TEXT NOT NULL,
    applied_date TEXT NOT NULL,
    jd_summary TEXT,
    status TEXT NOT NULL,
    recruiter_response TEXT,
    cv_file TEXT,
    cover_letter_file TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    special_documents TEXT,
    document_prep_completed_at TEXT,
    applied_confirmed_at TEXT
);
