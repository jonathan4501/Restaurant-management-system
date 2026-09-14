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
