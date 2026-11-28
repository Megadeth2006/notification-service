from enum import StrEnum


class Channel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class AttemptResult(StrEnum):
    SUCCESS = "success"
    TEMPORARY_ERROR = "temporary_error"
    PERMANENT_ERROR = "permanent_error"


class TransactionType(StrEnum):
    DEPOSIT = "deposit"
    RESERVE = "reserve"
    CHARGE = "charge"
    REFUND = "refund"
