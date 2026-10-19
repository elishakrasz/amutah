"""Applicant notifications. Messages carry only the case number and a link:
never amounts or category."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from app.settings import NotifierBackend, Settings

log = logging.getLogger("amutah.notify")


class NotificationEvent(StrEnum):
    APPLICATION_RECEIVED = "application_received"
    DOCUMENTS_REQUESTED = "documents_requested"
    DECISION_MADE = "decision_made"
    PAYMENT_EXECUTED = "payment_executed"
    APPEAL_RECEIVED = "appeal_received"
    OTP_CODE = "otp_code"


@dataclass(frozen=True)
class Notification:
    event: NotificationEvent
    to_phone: str | None
    to_email: str | None
    case_number: str | None
    link: str | None
    otp_code: str | None = None


class Notifier(ABC):
    @abstractmethod
    def send(self, n: Notification) -> None: ...


class ConsoleNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, n: Notification) -> None:
        self.sent.append(n)
        # Demo only: the OTP is printed so the demo can be driven without SMS.
        log.warning("NOTIFY %s case=%s link=%s otp=%s", n.event, n.case_number, n.link, n.otp_code)


def make_notifier(settings: Settings) -> Notifier:
    if settings.notifier_backend is NotifierBackend.CONSOLE:
        return ConsoleNotifier()
    raise NotImplementedError("AcsNotifier arrives in build phase 8")
