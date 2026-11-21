from hashlib import sha256
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy import select

from app.db.models.shop import Shop
from app.db.session import SessionDependency

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_shop(
    session: SessionDependency,
    api_key: Annotated[str | None, Depends(api_key_header)],
) -> Shop:
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    key_hash = sha256(api_key.encode()).hexdigest()
    shop = await session.scalar(
        select(Shop).where(Shop.api_key_hash == key_hash, Shop.is_active.is_(True))
    )
    if shop is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return shop


CurrentShop = Annotated[Shop, Depends(get_current_shop)]
