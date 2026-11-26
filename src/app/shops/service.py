import secrets
from hashlib import sha256

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.shop import Shop
from app.shops.schemas import ShopCreate, ShopCreatedResponse


def generate_api_key() -> tuple[str, str]:
    raw_key = f"ntf_{secrets.token_urlsafe(32)}"
    key_hash = sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


async def create_shop(
    session: AsyncSession,
    payload: ShopCreate,
) -> ShopCreatedResponse:
    raw_key, key_hash = generate_api_key()
    shop = Shop(name=payload.name, api_key_hash=key_hash)
    session.add(shop)
    await session.commit()
    await session.refresh(shop)
    return ShopCreatedResponse(
        id=shop.id,
        name=shop.name,
        api_key=raw_key,
        is_active=shop.is_active,
        created_at=shop.created_at,
    )
