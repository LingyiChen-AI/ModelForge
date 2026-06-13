from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.training import Deployment
from app.schemas.deployment import DeploymentCreate, DeploymentOut
from app.services import deployment_service

router = APIRouter(prefix="/deployments", tags=["deployment"])

@router.post("", response_model=DeploymentOut, status_code=201)
def create(body: DeploymentCreate, db: Session = Depends(get_db)):
    try:
        return deployment_service.create(db, body)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[DeploymentOut])
def list_deployments(db: Session = Depends(get_db)):
    return db.execute(select(Deployment).order_by(Deployment.id.desc())).scalars().all()

@router.post("/{deployment_id}/stop", response_model=DeploymentOut)
def stop(deployment_id: int, db: Session = Depends(get_db)):
    try:
        return deployment_service.stop(db, deployment_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
