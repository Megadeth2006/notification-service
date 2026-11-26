from typing import Annotated

from fastapi import APIRouter, Header, Path, Response

from app.db.session import SessionDependency
from app.notifications import service
from app.notifications.schemas import NotificationCreate, NotificationResponse
from app.shops.dependencies import CurrentShop

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("", status_code=202, responses={200: {"model": NotificationResponse}})
async def create_notification(
    message: NotificationCreate,
    response: Response,
    session: SessionDependency,
    shop: CurrentShop,
    idempotency_key: Annotated[
        str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    ],
) -> NotificationResponse:
    notification, created = await service.create_notification(
        session,
        shop.id,
        message,
        idempotency_key,
    )
    if created:
        response.headers["Location"] = f"/notifications/{notification.id}"
    else:
        response.status_code = 200
    return notification


@router.get("/{notification_id}")
async def get_notification(
    notification_id: Annotated[int, Path(ge=1, le=9223372036854775807)],
    session: SessionDependency,
    shop: CurrentShop,
) -> NotificationResponse:
    return await service.get_notification(session, shop.id, notification_id)
