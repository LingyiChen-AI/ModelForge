-- Store API key plaintext so it can be re-copied from the list (internal-tool convenience).
-- Pre-existing keys keep NULL plaintext (their secret was never stored).
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS plaintext VARCHAR;
