from fastapi import FastAPI

app = FastAPI(title="ModelForge app-server")

@app.get("/health")
def health():
    return {"status": "ok"}
