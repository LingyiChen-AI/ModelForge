CREATE TABLE IF NOT EXISTS llm_providers (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    base_url    TEXT NOT NULL,
    api_key     TEXT NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS llm_models (
    id          SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES llm_providers(id) ON DELETE CASCADE,
    model_id    TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_llm_models_provider_model UNIQUE (provider_id, model_id)
);
CREATE INDEX IF NOT EXISTS ix_llm_models_provider ON llm_models(provider_id);
