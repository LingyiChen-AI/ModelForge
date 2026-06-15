INSERT INTO permissions (code, description) VALUES
  ('prompt:read', '看 Prompt'),
  ('prompt:write', '管理 Prompt')
ON CONFLICT (code) DO NOTHING;

-- prompt:read -> admin, member, viewer
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member', 'viewer') AND p.code = 'prompt:read'
ON CONFLICT DO NOTHING;

-- prompt:write -> admin, member
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member') AND p.code = 'prompt:write'
ON CONFLICT DO NOTHING;
