from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require, apply_scope
from app.models.user import User
from app.models.training import Deployment
from app.schemas.deployment import DeploymentCreate, DeploymentOut
from app.services import deployment_service
from app.services.delete_service import delete_deployment
from app.pagination import paginate

router = APIRouter(prefix="/deployments", tags=["deployment"])

@router.post("", response_model=DeploymentOut, status_code=201)
def create(body: DeploymentCreate, user: User = Depends(require("deploy:write")),
           db: Session = Depends(get_db)):
    try:
        return deployment_service.create(db, body, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[DeploymentOut])
def list_deployments(response: Response, page: int | None = Query(None, ge=1),
                     page_size: int = Query(20, ge=1, le=200),
                     user: User = Depends(require("deploy:read")), db: Session = Depends(get_db)):
    deployment_service.reconcile(db)  # flip stale 'running' (e.g. after model-server restart) to truthful status
    stmt = apply_scope(select(Deployment).order_by(Deployment.id.desc()), Deployment, user)
    return paginate(db, stmt, response, page, page_size)

@router.post("/{deployment_id}/start", response_model=DeploymentOut)
def start(deployment_id: int, user: User = Depends(require("deploy:write")),
          db: Session = Depends(get_db)):
    dep = db.execute(apply_scope(select(Deployment).where(Deployment.id == deployment_id),
                                 Deployment, user)).scalar_one_or_none()
    if not dep:
        raise HTTPException(404, "deployment not found")
    try:
        return deployment_service.start(db, deployment_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.post("/{deployment_id}/stop", response_model=DeploymentOut)
def stop(deployment_id: int, user: User = Depends(require("deploy:write")),
         db: Session = Depends(get_db)):
    dep = db.execute(apply_scope(select(Deployment).where(Deployment.id == deployment_id),
                                 Deployment, user)).scalar_one_or_none()
    if not dep:
        raise HTTPException(404, "deployment not found")
    try:
        return deployment_service.stop(db, deployment_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.delete("/{deployment_id}")
def delete(deployment_id: int, user: User = Depends(require("deploy:write")),
           db: Session = Depends(get_db)):
    dep = db.execute(apply_scope(select(Deployment).where(Deployment.id == deployment_id),
                                 Deployment, user)).scalar_one_or_none()
    if not dep:
        raise HTTPException(404, "deployment not found")
    delete_deployment(db, deployment_id)
    return {"deleted": True}
