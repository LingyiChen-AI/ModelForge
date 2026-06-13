def test_metadata_has_users_table():
    from app.models.base import Base
    import app.models  # noqa: ensure models registered
    assert "users" in Base.metadata.tables
