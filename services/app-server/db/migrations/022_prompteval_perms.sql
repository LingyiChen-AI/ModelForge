INSERT INTO permissions (code, description) VALUES
  ('prompteval:read', '看 Prompt 评测'),
  ('prompteval:run', '发起 Prompt 评测')
ON CONFLICT (code) DO NOTHING;

-- prompteval:read -> admin, member, viewer
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member', 'viewer') AND p.code = 'prompteval:read'
ON CONFLICT DO NOTHING;

-- prompteval:run -> admin, member
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member') AND p.code = 'prompteval:run'
ON CONFLICT DO NOTHING;
