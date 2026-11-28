import secrets
from hashlib import sha256

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TransactionType
from app.db.models.shop import Shop
from app.db.models.transaction import Transaction
from app.shops.schemas import ShopBalanceTopUp, ShopCreate, ShopCreatedResponse, ShopMeResponse


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


async def top_up_balance(
    session: AsyncSession,
    shop_id: int,
    payload: ShopBalanceTopUp,
) -> ShopMeResponse:
    stmt = (
        update(Shop)
        .where(Shop.id == shop_id)
        .values(balance=Shop.balance + payload.amount)
        .returning(Shop)
        .execution_options(populate_existing=True)
    )
    updated_shop: Shop | None = await session.scalar(stmt)
    if updated_shop is None:
        raise ValueError(f"Shop {shop_id} not found")

    tx = Transaction(
        shop_id=shop_id,
        type=TransactionType.DEPOSIT,
        amount=payload.amount,
        balance_after=updated_shop.balance,
    )
    session.add(tx)
    await session.commit()
    return ShopMeResponse.model_validate(updated_shop)
