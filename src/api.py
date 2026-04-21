from fastapi import FastAPI

from src.config.settings import settings
from src.routes.entities import router as entities_router
from src.routes.periods import router as periods_router
from src.routes.transactions import router as transactions_router

app = FastAPI(title=settings.get('app_name'), description=settings.get('app_description'))

app.include_router(entities_router)
app.include_router(periods_router)
app.include_router(transactions_router)


@app.get("/health-check")
async def health_check():
    return {"message": "OK"}
