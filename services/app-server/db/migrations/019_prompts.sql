CREATE TABLE IF NOT EXISTS prompts (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id            SERIAL PRIMARY KEY,
    prompt_id     INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_no    INTEGER NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    user_prompt   TEXT NOT NULL DEFAULT '',
    params        JSON NOT NULL DEFAULT '[]',
    note          TEXT NOT NULL DEFAULT '',
    created_by    INTEGER REFERENCES users(id),
    created_at    TIMESTAMP DEFAULT now(),
    updated_at    TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_prompt_versions_prompt_no UNIQUE (prompt_id, version_no)
);
CREATE INDEX IF NOT EXISTS ix_prompt_versions_prompt ON prompt_versions(prompt_id);
