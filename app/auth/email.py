"""Account email: the verification and password-reset messages (ADR-061).

Two backends, picked by ``EMAIL_BACKEND`` (:attr:`app.config.Settings.effective_email_backend`):

- ``console`` logs the message, link included, instead of sending it. The default in
  development and test, where the link is opened straight from the backend log.
- ``smtp`` sends it with the standard library's :mod:`smtplib`, upgrading the connection with
  STARTTLS before logging in.

A send never fails the request that caused it. Forgot-password must answer the same 202 whether
or not the email has an account, and a register whose account already exists must not turn
into a 500 because a mail server was down; the user can ask for another link.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings, get_settings
from app.errors import ConfigurationError

logger = logging.getLogger(__name__)

#: How long one SMTP conversation may take before it is given up.
SMTP_TIMEOUT_SECONDS = 30


class EmailSender(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    """Writes each message to the log. Never use where the log is readable by others."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info("Email to %s (EMAIL_BACKEND=console, not sent): %s\n%s", to, subject, body)


class SmtpEmailSender:
    """Sends over SMTP with STARTTLS, off the request thread.

    Off the request thread so a slow mail server neither holds the request open nor lets the
    response time of forgot-password reveal whether an address has an account.
    """

    def __init__(self, settings: Settings) -> None:
        if settings.smtp_host is None or settings.smtp_from is None:
            raise ConfigurationError(
                "EMAIL_BACKEND=smtp needs SMTP_HOST and SMTP_FROM.",
                detail="Set them, or use EMAIL_BACKEND=console to log each email instead.",
            )
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._from = settings.smtp_from

    def send(self, *, to: str, subject: str, body: str) -> None:
        threading.Thread(
            target=self.send_now, kwargs={"to": to, "subject": subject, "body": body}, daemon=True
        ).start()

    def send_now(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if self._user is not None and self._password is not None:
                    smtp.login(self._user, self._password.get_secret_value())
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            logger.exception("Could not send %r to %s via %s", subject, to, self._host)
            return
        logger.info("Sent %r to %s", subject, to)


def get_email_sender(settings: Settings | None = None) -> EmailSender:
    settings = settings or get_settings()
    if settings.effective_email_backend == "smtp":
        return SmtpEmailSender(settings)
    return ConsoleEmailSender()


def deliver(to: str, subject: str, body: str) -> None:
    """Send one message, logging rather than raising any failure (see the module docstring)."""
    try:
        get_email_sender().send(to=to, subject=subject, body=body)
    except Exception:
        logger.exception("Could not send %r to %s", subject, to)


def send_verification_email(to: str, token: str) -> None:
    link = f"{get_settings().app_url}/verify?token={token}"
    deliver(
        to,
        "Verify your Adaptive Trainer email address",
        "Confirm this address to finish setting up your Adaptive Trainer account:\n\n"
        f"{link}\n\n"
        "The link works for one hour. If you did not create an account, ignore this email.\n",
    )


def send_password_reset_email(to: str, token: str) -> None:
    link = f"{get_settings().app_url}/reset-password?token={token}"
    deliver(
        to,
        "Reset your Adaptive Trainer password",
        "Someone asked to reset the password of your Adaptive Trainer account. "
        "Choose a new one here:\n\n"
        f"{link}\n\n"
        "The link works for one hour. If it was not you, ignore this email; "
        "your password stays as it is.\n",
    )
