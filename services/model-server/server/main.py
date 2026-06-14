from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from server.store import store

app = FastAPI(title="ModelForge model-server")


# ---- Unified response envelope: {code, data, message} ----
# code: 0 = success; otherwise the HTTP-like error code. data: payload (null on error).
def ok(data=None, message: str = "success"):
    return {"code": 0, "data": data, "message": message}


@app.exception_handler(HTTPException)
async def _http_exc_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content={"code": exc.status_code, "data": None, "message": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422,
                        content={"code": 422, "data": jsonable_encoder(exc.errors()),
                                 "message": "请求参数校验失败"})


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500,
                        content={"code": 500, "data": None, "message": str(exc)})


@app.get("/health")
def health():
    return ok({"status": "ok"})


class LoadReq(BaseModel):
    model_version_id: int
    mlflow_model_name: str
    mlflow_version: str
    task_type: str


@app.post("/load")
def load(req: LoadReq):
    store.load(req.model_version_id, req.mlflow_model_name, req.mlflow_version, req.task_type)
    return ok({"loaded": True, "model_version_id": req.model_version_id})


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
        return ok({"predictions": pred.predict([t.split() for t in req.texts])})
    if task_type == "classification":
        return ok({"predictions": pred.predict(req.texts)})
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
    return ok({"embeddings": pred.embed(req.texts)})


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
    return ok({"scores": pred.similarity(req.pairs)})


@app.get("/loaded")
def loaded():
    return ok({"model_version_ids": store.loaded_ids()})


@app.delete("/loaded/{model_version_id}")
def unload(model_version_id: int):
    if not store.unload(model_version_id):
        raise HTTPException(404, "not loaded")
    return ok({"unloaded": True})
