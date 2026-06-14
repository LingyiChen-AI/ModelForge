INSERT INTO permissions (code, description) VALUES
  ('badcase:read', '看 Badcase / 上报规则'),
  ('badcase:annotate', '标注 Badcase')
ON CONFLICT (code) DO NOTHING;

-- badcase:read -> admin, member, viewer
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member', 'viewer') AND p.code = 'badcase:read'
ON CONFLICT DO NOTHING;

-- badcase:annotate -> admin, member
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member') AND p.code = 'badcase:annotate'
ON CONFLICT DO NOTHING;
