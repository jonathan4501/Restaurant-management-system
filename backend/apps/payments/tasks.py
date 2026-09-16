"""
Owner alerts. A reopened bill is the classic way money leaves a restaurant unnoticed, so the owner
hears about it without having to look. WhatsApp and the daily summary are WS06; this is email.
"""

from __future__ import annotations

import logging
import uuid

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from apps.core.tenancy import restaurant_context

log = logging.getLogger(__name__)


@shared_task(name="payments.notify_owner_reopen")
def notify_owner_reopen(
    restaurant_id: str,
    session_id: str,
    table_number: str,
    actor_name: str,
    authoriser_name: str,
    note: str = "",
) -> None:
    subject = f"Bill reopened — table {table_number}"
    body = (
        f"{actor_name} reopened the bill on table {table_number}, "
        f"authorised by {authoriser_name}.\n\n"
        + (f"Reason given: {note}.\n\n" if note else "")
        + f"Session {session_id}. See the event log for what changed afterwards."
    )
    recipient = getattr(settings, "OWNER_ALERT_EMAIL", "") or ""
    with restaurant_context(uuid.UUID(restaurant_id)):
        if not recipient:
            log.warning("owner reopen alert (no OWNER_ALERT_EMAIL set): %s", body)
            return
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=True,
        )
