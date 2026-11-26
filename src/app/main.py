from fastapi import FastAPI

from app.notifications.router import router as notifications_router

app = FastAPI(title="notification-service")
app.include_router(notifications_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
