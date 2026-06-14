CREATE TABLE IF NOT EXISTS badcases (
    id                  SERIAL PRIMARY KEY,
    model_version_id    INTEGER NOT NULL REFERENCES model_versions(id),
    task_type           TEXT NOT NULL,
    input               JSON NOT NULL DEFAULT '{}',
    inference           JSON NOT NULL DEFAULT '{}',
    category            TEXT,
    source              TEXT,
    source_ref          TEXT,
    status              TEXT NOT NULL DEFAULT 'reported',
    annotation          JSON,
    annotated_by        INTEGER REFERENCES users(id),
    annotated_at        TIMESTAMP,
    dataset_version_id  INTEGER REFERENCES dataset_versions(id),
    created_at          TIMESTAMP DEFAULT now(),
    updated_at          TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_badcases_model_version ON badcases(model_version_id);
CREATE INDEX IF NOT EXISTS ix_badcases_status ON badcases(status);
