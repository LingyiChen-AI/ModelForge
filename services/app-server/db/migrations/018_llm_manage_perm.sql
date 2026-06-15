INSERT INTO permissions (code, description) VALUES
  ('llm:manage', 'LLM 供应商配置')
ON CONFLICT (code) DO NOTHING;

-- llm:manage -> admin(superadmin 持有 '*' 通配,无需单授)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'admin' AND p.code = 'llm:manage'
ON CONFLICT DO NOTHING;
