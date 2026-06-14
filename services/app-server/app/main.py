from fastapi import FastAPI

app = FastAPI(title="ModelForge app-server")

@app.get("/health")
def health():
    return {"status": "ok"}

from app.api import datasets
app.include_router(datasets.router)

from app.api import training
app.include_router(training.router)

from app.api import models
app.include_router(models.router)

from app.api import eval as eval_api
app.include_router(eval_api.router)

from app.api import deployment
app.include_router(deployment.router)

from app.api import auth
app.include_router(auth.router)

from app.api import users
app.include_router(users.router)
