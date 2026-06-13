from app.services.mlflow_sync import upsert_model_version_from_result

def test_upsert_creates_model_version(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.training import TrainingJob
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False)
    db = S()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="bert-base",
                      task_type="classification", hyperparams={}); db.add(job); db.commit()
    mv = upsert_model_version_from_result(db, job.id, {
        "run_id": "r1", "model_name": "ModelForge-j", "version": "1",
        "metrics": {"accuracy": 0.9}})
    assert mv.mlflow_version == "1"
    assert mv.train_metrics["accuracy"] == 0.9
    assert mv.task_type == "classification"
