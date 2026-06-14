from app.models.base import Base
import app.models  # noqa


def test_rbac_tables_and_user_columns():
    t = Base.metadata.tables
    assert {"roles", "permissions", "role_permissions"} <= set(t)
    rcols = t["roles"].columns.keys()
    assert {"id", "name", "description", "data_scope", "is_system"} <= set(rcols)
    ucols = t["users"].columns.keys()
    assert {"password_hash", "role_id", "is_active"} <= set(ucols)
    assert "role" not in ucols  # 旧字符串列已移除
