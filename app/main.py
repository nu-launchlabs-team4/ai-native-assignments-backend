import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text

app = FastAPI(title="AI-Native Assignments API")
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "db": "unreachable"})
    return {"status": "ok", "db": "connected"}
