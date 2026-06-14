-- New permission: manage models (promote lifecycle stage). Grant to admin & member.
INSERT INTO permissions (code, description)
VALUES ('model:write', '管理模型(提升阶段)')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member') AND p.code = 'model:write'
ON CONFLICT DO NOTHING;
