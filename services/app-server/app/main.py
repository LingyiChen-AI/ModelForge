from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager
from app.config import settings
from app.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.run_migrations_on_startup and engine.dialect.name == "postgresql":
        from app.migrate import run_migrations
        run_migrations(engine)
    yield


app = FastAPI(title="ModelForge app-server", lifespan=lifespan)

# CORS: frontend (Vite dev) is a different origin; it authenticates via the
# Authorization Bearer header (no cookies), so allow all origins without credentials.
_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

from app.api import roles
app.include_router(roles.router)
