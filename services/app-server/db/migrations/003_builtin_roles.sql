-- 003 protect built-in roles from deletion (idempotent; also repairs existing rows)
ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_builtin boolean NOT NULL DEFAULT false;

-- mark the seeded default roles as built-in so they can't be deleted
UPDATE roles SET is_builtin = true WHERE name IN ('superadmin', 'admin', 'member', 'viewer');
