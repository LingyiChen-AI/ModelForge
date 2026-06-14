from fastapi.testclient import TestClient
from tests.conftest import make_user


def test_internal_callback_requires_token(session_factory):
    S = session_factory
    db = S()
    from app.models.training import TrainingJob
    owner = make_user(db, codes=("*",), email="o@x.com")
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b",
                      task_type="classification", hyperparams={}, created_by=owner.id)
    db.add(job)
    db.commit()
    jid = job.id
    db.close()
    from app.main import app
    c = TestClient(app)
    payload = {"run_id": "r", "model_name": "m", "version": "1", "metrics": {}}
    assert c.post(f"/training-jobs/internal/{jid}/result", json=payload).status_code == 401
    ok = c.post(f"/training-jobs/internal/{jid}/result", json=payload,
                headers={"X-Internal-Token": "modelforge-internal"})
    assert ok.status_code == 201
