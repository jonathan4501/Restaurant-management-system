import pytest

from apps.accounts.models import Staff
from apps.core.tenancy import TenantContextMissing, restaurant_context


@pytest.mark.django_db
def test_queries_without_context_raise(db) -> None:
    with pytest.raises(TenantContextMissing):
        Staff.objects.count()


@pytest.mark.django_db
def test_context_scopes_reads_and_writes(restaurant, other_restaurant, pin_hash) -> None:
    Staff.objects.create(full_name="Ours", role="WAITER", pin_hash=pin_hash)
    with restaurant_context(other_restaurant.id):
        Staff.objects.create(full_name="Theirs", role="WAITER", pin_hash=pin_hash)
        assert list(Staff.objects.values_list("full_name", flat=True)) == ["Theirs"]
    assert list(Staff.objects.values_list("full_name", flat=True)) == ["Ours"]
    assert Staff.objects.unscoped().count() == 2


@pytest.mark.django_db
def test_cross_tenant_lookup_by_id_is_not_found(restaurant, other_restaurant, pin_hash) -> None:
    with restaurant_context(other_restaurant.id):
        theirs = Staff.objects.create(full_name="Theirs", role="WAITER", pin_hash=pin_hash)
    assert not Staff.objects.filter(id=theirs.id).exists()


@pytest.mark.django_db
def test_create_honours_an_explicit_restaurant(restaurant, other_restaurant):
    """Passing restaurant=... must win over the context; otherwise a row lands in the wrong tenant."""
    from apps.floor.models import Table

    explicit = Table.objects.create(
        restaurant=other_restaurant, number="99", qr_token=Table.new_qr_token()
    )
    assert explicit.restaurant_id == other_restaurant.id

    by_id = Table.objects.create(
        restaurant_id=other_restaurant.id, number="98", qr_token=Table.new_qr_token()
    )
    assert by_id.restaurant_id == other_restaurant.id

    # Nothing named: the context tenant, as before.
    implicit = Table.objects.create(number="97", qr_token=Table.new_qr_token())
    assert implicit.restaurant_id == restaurant.id
    assert list(Table.objects.values_list("number", flat=True)) == ["97"]
