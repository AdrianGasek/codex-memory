from fastapi import FastAPI

from app.routes.memory import router as memory_router

app = FastAPI(title="Codex-Mem API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(memory_router)
