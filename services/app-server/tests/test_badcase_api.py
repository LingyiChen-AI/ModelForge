def test_badcase_model_roundtrip(session_factory):
    from app.models.badcase import Badcase
    db = session_factory()
    b = Badcase(model_version_id=1, task_type="classification",
                input={"text": "x"}, inference={"label": "A", "score": 0.9},
                category="A", source="svc", status="reported")
    db.add(b); db.commit(); db.refresh(b)
    assert b.id and b.status == "reported" and b.annotation is None
