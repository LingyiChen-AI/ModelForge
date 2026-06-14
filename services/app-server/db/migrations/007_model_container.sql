-- Named model container; training binds to it and each run adds a version.
CREATE TABLE IF NOT EXISTS models (
    id serial PRIMARY KEY,
    name varchar NOT NULL UNIQUE,
    task_type varchar NOT NULL,
    description varchar NOT NULL DEFAULT '',
    created_by integer REFERENCES users(id),
    created_at timestamp NOT NULL DEFAULT now(),
    updated_at timestamp NOT NULL DEFAULT now()
);

ALTER TABLE training_jobs   ADD COLUMN IF NOT EXISTS model_id integer REFERENCES models(id);
ALTER TABLE model_versions  ADD COLUMN IF NOT EXISTS model_id integer REFERENCES models(id);
