from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.training import Deployment, ModelVersion
from app.config import settings
from app.modelserver_client import load_on_server as notify_load, unload_on_server as notify_unload

def create(db: Session, body, created_by=None) -> Deployment:
    mv = db.get(ModelVersion, body.model_version_id)
    if not mv:
        raise ValueError("model_version not found")
    # one model version can be deployed only once — manage it via start/stop
    exists = db.execute(
        select(Deployment.id).where(Deployment.model_version_id == mv.id)).first()
    if exists:
        raise ValueError("该模型版本已有部署,请在列表中启动/停止,无需重复部署")
    dep = Deployment(model_version_id=mv.id, config=body.config,
                     endpoint=f"{settings.model_server_url}/predict",
                     created_by=created_by)
    db.add(dep); db.commit(); db.refresh(dep)
    try:
        notify_load(mv)
        dep.status = "running"
    except Exception as e:
        dep.status = "failed"; dep.error = str(e)
    db.commit(); db.refresh(dep)
    return dep

def start(db: Session, deployment_id: int) -> Deployment:
    dep = db.get(Deployment, deployment_id)
    if not dep:
        raise ValueError("deployment not found")
    mv = db.get(ModelVersion, dep.model_version_id)
    if not mv:
        raise ValueError("model_version not found")
    try:
        notify_load(mv)
        dep.status = "running"; dep.error = None
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
