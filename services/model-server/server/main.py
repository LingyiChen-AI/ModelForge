from fastapi import FastAPI

app = FastAPI(title="ModelForge model-server")


@app.get("/health")
def health():
    return {"status": "ok"}
