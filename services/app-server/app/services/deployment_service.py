from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.training import Deployment, ModelVersion
from app.config import settings
from app.modelserver_client import (load_on_server as notify_load,
                                     unload_on_server as notify_unload, list_loaded)


def reconcile(db: Session) -> None:
    """Make deployment statuses truthful against what's actually loaded on model-server.
    A 'running' deployment whose model isn't loaded (e.g. model-server was restarted and
    lost its in-memory models) is flipped to 'stopped' with a hint; the user can click
    启动 to reload it. No-op when model-server is unreachable (avoids false flips)."""
    loaded = list_loaded()
    if loaded is None:
        return
    running = db.execute(select(Deployment).where(Deployment.status == "running")).scalars().all()
    changed = False
    for dep in running:
        if dep.model_version_id not in loaded:
            dep.status = "stopped"
            dep.error = "实例未加载(model-server 可能已重启),点击「启动」可恢复"
            changed = True
    if changed:
        db.commit()

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
