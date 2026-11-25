from fastapi import FastAPI

from app.notifications.router import router as notifications_router
from app.shops.router import router as shops_router

app = FastAPI(title="notification-service")
app.include_router(shops_router)
app.include_router(notifications_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
