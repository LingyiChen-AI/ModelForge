from sqlalchemy.orm import Session
from app.models.training import Deployment, ModelVersion
from app.config import settings
from app.modelserver_client import load_on_server as notify_load, unload_on_server as notify_unload

def create(db: Session, body) -> Deployment:
    mv = db.get(ModelVersion, body.model_version_id)
    if not mv:
        raise ValueError("model_version not found")
    dep = Deployment(model_version_id=mv.id, config=body.config,
                     endpoint=f"{settings.model_server_url}/predict")
    db.add(dep); db.commit(); db.refresh(dep)
    try:
        notify_load(mv)
        dep.status = "running"
    except Exception as e:
        dep.status = "failed"; dep.error = str(e)
    db.commit(); db.refresh(dep)
    return dep

def stop(db: Session, deployment_id: int) -> Deployment:
    dep = db.get(Deployment, deployment_id)
    if not dep:
        raise ValueError("deployment not found")
    try:
        notify_unload(dep.model_version_id)
    except Exception:
        pass
    dep.status = "stopped"
    db.commit(); db.refresh(dep)
    return dep
