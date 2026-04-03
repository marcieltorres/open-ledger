from fastapi import FastAPI

from src.config.settings import settings

app = FastAPI(title=settings.get('app_name'), description=settings.get('app_description'))


@app.get("/health-check")
async def health_check():
    return {"message": "OK"}
