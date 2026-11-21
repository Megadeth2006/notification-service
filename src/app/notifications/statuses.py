from enum import StrEnum


class NotificationStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    SENDING = "sending"
    DELIVERED = "delivered"
    FAILED = "failed"
