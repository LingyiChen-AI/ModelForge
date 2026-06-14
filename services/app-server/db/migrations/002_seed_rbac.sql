-- 002 seed RBAC: permissions, system roles, role_permissions, initial superadmin (idempotent)

INSERT INTO permissions (code, description) VALUES
  ('dataset:read', '看数据集/版本'),
  ('dataset:write', '建数据集/传版本'),
  ('training:read', '看训练任务'),
  ('training:run', '发起训练'),
  ('model:read', '看模型版本'),
  ('eval:read', '看评估'),
  ('eval:run', '发起评估'),
  ('deploy:read', '看部署'),
  ('deploy:write', '部署/停止'),
  ('user:manage', '用户管理'),
  ('role:manage', '角色管理'),
  ('*', '通配')
ON CONFLICT (code) DO NOTHING;

INSERT INTO roles (name, description, data_scope, is_system) VALUES
  ('superadmin', '超级管理员', 'all', true),
  ('admin', '管理员', 'all', false),
  ('member', '成员', 'own', false),
  ('viewer', '只读', 'own', false)
ON CONFLICT (name) DO NOTHING;

-- superadmin: wildcard
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = '*'
WHERE r.name = 'superadmin'
ON CONFLICT DO NOTHING;

-- admin + member: business read+write (9 codes)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p
  ON p.code IN ('dataset:read','dataset:write','training:read','training:run',
                'model:read','eval:read','eval:run','deploy:read','deploy:write')
WHERE r.name IN ('admin', 'member')
ON CONFLICT DO NOTHING;

-- viewer: reads (5 codes)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p
  ON p.code IN ('dataset:read','training:read','model:read','eval:read','deploy:read')
WHERE r.name = 'viewer'
ON CONFLICT DO NOTHING;

-- initial superadmin (email admin@modelforge.local, password admin12345 — change after first login)
INSERT INTO users (name, email, password_hash, role_id, is_active)
SELECT 'admin', 'admin@modelforge.local', '$2b$12$tHOkWWRoGn4z6DXYONZlpuARL1R5y7nslCvPXyDO42opEs01vay2u', r.id, true
FROM roles r WHERE r.name = 'superadmin'
ON CONFLICT (email) DO NOTHING;
