-- Track which user uploaded each dataset version (for the "创建者" column).
ALTER TABLE dataset_versions
    ADD COLUMN IF NOT EXISTS created_by integer REFERENCES users(id);
