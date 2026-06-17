from fastapi import FastAPI

from app.config import settings
from app.routers import comment_claims

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.include_router(comment_claims.router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok"}
