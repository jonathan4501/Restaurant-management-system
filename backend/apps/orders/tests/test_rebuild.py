"""rebuild / verify work end-to-end with the one projector that exists at WS00 (menu 86)."""

import pytest

from apps.core.commands import CommandOutcome, EventDraft, run_command
from apps.core.roles import AggregateType
from apps.menu.models import MenuCategory, MenuItem
from apps.orders.events import EventType
from apps.orders.rebuild import rebuild, verify


@pytest.fixture
def tilapia(restaurant):
    cat = MenuCategory.objects.create(name="Grill")
    return MenuItem.objects.create(
        category=cat, name="Whole Grilled Tilapia", price_pesewas=13000, prep_station="GRILL"
    )


@pytest.mark.django_db
def test_86_event_projects_and_replays(restaurant, tilapia, make_ctx) -> None:
    def eighty_six(ctx):
        draft = EventDraft(
            AggregateType.MENU_ITEM,
            tilapia.id,
            EventType.ITEM_86ED,
            {"menu_item_id": str(tilapia.id), "name": tilapia.name},
        )
        return CommandOutcome(events=[draft], response={"is_available": False})

    run_command(make_ctx(), eighty_six)
    tilapia.refresh_from_db()
    assert tilapia.is_available is False

    # Someone flips it by hand; the stream still says 86'd, so a rebuild restores the truth.
    MenuItem.objects.filter(pk=tilapia.pk).update(is_available=True)
    assert rebuild(restaurant.id) == 1
    tilapia.refresh_from_db()
    assert tilapia.is_available is False


@pytest.mark.django_db
def test_verify_is_clean_with_no_drift(restaurant) -> None:
    assert verify(restaurant.id) == {}
