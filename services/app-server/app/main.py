from fastapi import FastAPI

app = FastAPI(title="ModelForge app-server")

@app.get("/health")
def health():
    return {"status": "ok"}

from app.api import datasets
app.include_router(datasets.router)
