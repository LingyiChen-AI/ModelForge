from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from server.store import store

app = FastAPI(title="ModelForge model-server")


@app.get("/health")
def health():
    return {"status": "ok"}


class LoadReq(BaseModel):
    model_version_id: int
    mlflow_model_name: str
    mlflow_version: str
    task_type: str


@app.post("/load")
def load(req: LoadReq):
    store.load(req.model_version_id, req.mlflow_model_name, req.mlflow_version, req.task_type)
    return {"loaded": True, "model_version_id": req.model_version_id}


class PredictReq(BaseModel):
    model_version_id: int
    texts: list[str]


@app.post("/predict")
def predict(req: PredictReq):
    entry = store.get(req.model_version_id)
    if not entry:
        raise HTTPException(404, "model not loaded")
    task_type, pred = entry
    if task_type == "ner":
        return {"predictions": pred.predict([t.split() for t in req.texts])}
    if task_type == "classification":
        return {"predictions": pred.predict(req.texts)}
    raise HTTPException(400, f"/predict not supported for task_type={task_type}")


class EmbedReq(BaseModel):
    model_version_id: int
    texts: list[str]


@app.post("/embed")
def embed(req: EmbedReq):
    entry = store.get(req.model_version_id)
    if not entry:
        raise HTTPException(404, "model not loaded")
    task_type, pred = entry
    if task_type != "embedding":
        raise HTTPException(400, "/embed requires an embedding model")
    return {"embeddings": pred.embed(req.texts)}


class SimReq(BaseModel):
    model_version_id: int
    pairs: list[tuple[str, str]]


@app.post("/similarity")
def similarity(req: SimReq):
    entry = store.get(req.model_version_id)
    if not entry:
        raise HTTPException(404, "model not loaded")
    task_type, pred = entry
    if task_type != "pair":
        raise HTTPException(400, "/similarity requires a pair model")
    return {"scores": pred.similarity(req.pairs)}


@app.get("/loaded")
def loaded():
    return {"model_version_ids": store.loaded_ids()}


@app.delete("/loaded/{model_version_id}")
def unload(model_version_id: int):
    if not store.unload(model_version_id):
        raise HTTPException(404, "not loaded")
    return {"unloaded": True}
