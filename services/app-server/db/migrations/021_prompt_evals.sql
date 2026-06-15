CREATE TABLE IF NOT EXISTS prompt_eval_runs (
    id                    SERIAL PRIMARY KEY,
    name                  TEXT NOT NULL,
    eval_type             TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'pending',
    progress              DOUBLE PRECISION NOT NULL DEFAULT 0,
    celery_task_id        TEXT,
    error                 TEXT,
    prompt_version_ids    JSON NOT NULL DEFAULT '[]',
    model_ids             JSON NOT NULL DEFAULT '[]',
    dataset_version_ids   JSON NOT NULL DEFAULT '[]',
    compare_to_version_id INTEGER,
    result_summary        JSON NOT NULL DEFAULT '{}',
    created_by            INTEGER REFERENCES users(id),
    created_at            TIMESTAMP DEFAULT now(),
    updated_at            TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_eval_arms (
    id                SERIAL PRIMARY KEY,
    run_id            INTEGER NOT NULL REFERENCES prompt_eval_runs(id) ON DELETE CASCADE,
    arm_index         INTEGER NOT NULL,
    prompt_version_id INTEGER NOT NULL REFERENCES prompt_versions(id),
    model_id          INTEGER NOT NULL REFERENCES llm_models(id),
    label             TEXT NOT NULL DEFAULT '',
    created_at        TIMESTAMP DEFAULT now(),
    updated_at        TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prompt_eval_arms_run ON prompt_eval_arms(run_id);

CREATE TABLE IF NOT EXISTS prompt_eval_items (
    id                 SERIAL PRIMARY KEY,
    run_id             INTEGER NOT NULL REFERENCES prompt_eval_runs(id) ON DELETE CASCADE,
    item_index         INTEGER NOT NULL,
    dataset_version_id INTEGER NOT NULL,
    row_index          INTEGER NOT NULL,
    inputs             JSON NOT NULL DEFAULT '{}',
    created_at         TIMESTAMP DEFAULT now(),
    updated_at         TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prompt_eval_items_run ON prompt_eval_items(run_id);

CREATE TABLE IF NOT EXISTS prompt_eval_outputs (
    id          SERIAL PRIMARY KEY,
    item_id     INTEGER NOT NULL REFERENCES prompt_eval_items(id) ON DELETE CASCADE,
    arm_id      INTEGER NOT NULL REFERENCES prompt_eval_arms(id),
    output_text TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    error       TEXT,
    latency_ms  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prompt_eval_outputs_item ON prompt_eval_outputs(item_id);
