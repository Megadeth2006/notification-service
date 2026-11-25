from fastapi import APIRouter, status

from app.db.session import SessionDependency
from app.shops import service
from app.shops.schemas import ShopCreate, ShopCreatedResponse

router = APIRouter(prefix="/shops", tags=["shops"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_shop(
    payload: ShopCreate,
    session: SessionDependency,
) -> ShopCreatedResponse:
    return await service.create_shop(session, payload)
