"""
The daily summary the owner is sent after cutover.

Short on purpose: it is read on a phone, once, standing up. Money taken, covers, what was given away,
what the drawer was out by, the three things that sold best. If a figure needs explaining it belongs on
the owner screen, not here.

The channel sits behind `SummarySender` because the owner has not confirmed one yet. Email works today.
WhatsApp is a stub: it records what it would have sent and returns False, so the caller can fall back to
email. Twilio is not a dependency of this project and must not become one until the owner asks for it
(`docs/tasks/WS06-reporting.md` §6).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from django.conf import settings
from django.core.mail import send_mail

from apps.accounts.models import Restaurant, Staff
from apps.core.money import format_pesewas
from apps.reporting.models import DailySales
from apps.reporting.queries import patterns

log = logging.getLogger(__name__)

TOP_ITEMS = 3


@dataclass(frozen=True)
class Summary:
    subject: str
    body: str


def owner_recipients(restaurant: Restaurant) -> list[str]:
    """
    Who hears about the service. `OWNER_ALERT_EMAIL` is in `infra/.env.example` but nothing reads it
    into settings yet, so the environment is checked directly as a fallback — see "Requests to other
    workstreams" in the WS06 pull request. Managers and owners with an address on file get it too.
    """
    configured = getattr(settings, "OWNER_ALERT_EMAIL", "") or os.environ.get(
        "OWNER_ALERT_EMAIL", ""
    )
    staff = Staff.objects.filter(
        role__in=["OWNER", "MANAGER"], is_active=True, email__isnull=False
    ).exclude(email="")
    recipients = [configured] if configured else []
    recipients += [s.email for s in staff if s.email]
    return sorted({r for r in recipients if r})


def render_summary(restaurant: Restaurant, row: DailySales) -> Summary:
    """
    Plain text, one figure per line.

    "Money taken" is gross cash through the till. It is not revenue and it is not the owner's income,
    and this email is the one place a tired reader is most likely to forget that — so it says so.
    """
    day: date = row.business_date
    best = patterns(restaurant, day, day)["best_sellers_by_value"][:TOP_ITEMS]
    lines = [
        f"{restaurant.name} — service of {day}",
        "",
        f"Money taken (gross cash through the till, not revenue): {format_pesewas(int(row.money_taken_pesewas))}",
        f"Covers: {row.covers}",
        f"Bills closed: {row.orders_closed} orders",
        f"Voided after the kitchen started: {row.orders_voided} orders, "
        f"{format_pesewas(int(row.void_value_pesewas))}",
        f"Discounts and comps: {format_pesewas(int(row.discount_pesewas))}",
        f"Cash drawer variance: {format_pesewas(row.cash_variance_pesewas)}",
    ]
    if best:
        lines += ["", f"Best sellers by value (top {len(best)}):"]
        lines += [
            f"  {item['quantity']} x {item['name']} — {format_pesewas(item['value_pesewas'])}"
            for item in best
        ]
    lines += ["", "Every action behind these figures is in the event log."]
    return Summary(subject=f"{restaurant.name} — {day} — money taken", body="\n".join(lines))


class SummarySender(Protocol):
    """A channel the summary can go out on. Returns True when it actually sent something."""

    name: str

    def send(self, restaurant: Restaurant, summary: Summary, recipients: list[str]) -> bool: ...


class EmailSummarySender:
    name = "email"

    def send(self, restaurant: Restaurant, summary: Summary, recipients: list[str]) -> bool:
        if not recipients:
            log.warning(
                "daily summary has nowhere to go: set OWNER_ALERT_EMAIL or give the owner an email address"
            )
            return False
        send_mail(
            summary.subject,
            summary.body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "renzy@localhost"),
            recipients,
            fail_silently=False,
        )
        return True


class WhatsAppSummarySender:
    """
    Stub. The owner may well prefer WhatsApp to email, and this is where that goes — behind the same
    interface, so choosing it later is a settings change and not a rewrite. It deliberately does not
    send: adding the Twilio dependency needs the owner to confirm the channel first.
    """

    name = "whatsapp"

    def send(self, restaurant: Restaurant, summary: Summary, recipients: list[str]) -> bool:
        log.info(
            "daily summary would go to WhatsApp once the owner confirms the channel: %s",
            summary.subject,
        )
        return False


SENDERS: dict[str, type[EmailSummarySender] | type[WhatsAppSummarySender]] = {
    EmailSummarySender.name: EmailSummarySender,
    WhatsAppSummarySender.name: WhatsAppSummarySender,
}


def get_sender() -> SummarySender:
    choice = str(getattr(settings, "SUMMARY_CHANNEL", "") or "email").lower()
    return SENDERS.get(choice, EmailSummarySender)()


def send_summary(restaurant: Restaurant, row: DailySales) -> bool:
    summary = render_summary(restaurant, row)
    sender = get_sender()
    sent = sender.send(restaurant, summary, owner_recipients(restaurant))
    if not sent and sender.name != EmailSummarySender.name:
        sent = EmailSummarySender().send(restaurant, summary, owner_recipients(restaurant))
    return sent
