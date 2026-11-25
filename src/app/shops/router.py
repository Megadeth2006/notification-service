from fastapi import APIRouter, status

from app.db.session import SessionDependency
from app.shops import service
from app.shops.dependencies import CurrentShop
from app.shops.schemas import ShopBalanceTopUp, ShopCreate, ShopCreatedResponse, ShopMeResponse

router = APIRouter(prefix="/shops", tags=["shops"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_shop(
    payload: ShopCreate,
    session: SessionDependency,
) -> ShopCreatedResponse:
    return await service.create_shop(session, payload)


@router.get("/me")
async def get_my_shop(shop: CurrentShop) -> ShopMeResponse:
    return ShopMeResponse.model_validate(shop)


@router.post("/balance")
async def top_up_shop_balance(
    payload: ShopBalanceTopUp,
    session: SessionDependency,
    shop: CurrentShop,
) -> ShopMeResponse:
    return await service.top_up_balance(session, shop.id, payload)
