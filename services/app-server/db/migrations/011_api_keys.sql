-- Shared API keys (for badcase report + model-server inference auth). Plaintext key
-- is shown once at creation; only its sha256 hash is stored.
CREATE TABLE IF NOT EXISTS api_keys (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    key_prefix    TEXT NOT NULL,
    key_hash      TEXT NOT NULL UNIQUE,
    scopes        JSON NOT NULL DEFAULT '[]',
    created_by    INTEGER REFERENCES users(id),
    last_used_at  TIMESTAMP,
    revoked_at    TIMESTAMP,
    created_at    TIMESTAMP DEFAULT now(),
    updated_at    TIMESTAMP DEFAULT now()
);
