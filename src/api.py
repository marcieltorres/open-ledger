from fastapi import FastAPI

from src.config.settings import settings
from src.routes.entities import router as entities_router

app = FastAPI(title=settings.get('app_name'), description=settings.get('app_description'))

app.include_router(entities_router)


@app.get("/health-check")
async def health_check():
    return {"message": "OK"}
