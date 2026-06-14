def test_seed_idempotent(session_factory):
    from app.bootstrap import seed
    from app.models.rbac import Role, Permission
    from app.models.user import User
    from sqlalchemy import select, func
    S = session_factory
    db = S()
    seed(db); seed(db)  # 跑两次
    assert db.execute(select(func.count()).select_from(Permission)).scalar() == 12
    roles = {r.name: r for r in db.execute(select(Role)).scalars()}
    assert set(roles) == {"superadmin", "admin", "member", "viewer"}
    assert roles["superadmin"].is_system is True
    assert {p.code for p in roles["superadmin"].permissions} == {"*"}
    assert roles["member"].data_scope == "own"
    admins = db.execute(select(User).where(User.role_id == roles["superadmin"].id)).scalars().all()
    assert len(admins) == 1 and admins[0].is_active
