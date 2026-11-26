from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Channel


class NotificationTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: Annotated[int, Field(strict=True, ge=1, le=9223372036854775807)]
    channel: Channel
