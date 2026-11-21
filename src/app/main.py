from fastapi import FastAPI

app = FastAPI(title="notification-service")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
