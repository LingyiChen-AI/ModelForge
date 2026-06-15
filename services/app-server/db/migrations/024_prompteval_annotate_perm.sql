INSERT INTO permissions (code, description) VALUES
  ('prompteval:annotate', '标注 Prompt 评估')
ON CONFLICT (code) DO NOTHING;

-- prompteval:annotate -> admin, member
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member') AND p.code = 'prompteval:annotate'
ON CONFLICT DO NOTHING;
