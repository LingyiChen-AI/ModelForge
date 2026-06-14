INSERT INTO permissions (code, description)
VALUES ('apikey:manage', 'API Key 管理')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'admin' AND p.code = 'apikey:manage'
ON CONFLICT DO NOTHING;
