from django.urls import path

from apps.orders.guest_views import (
    GuestAddItemView,
    GuestModifyItemView,
    GuestOpenOrderView,
    GuestOrderDetailView,
    GuestRemoveItemView,
    GuestSubmitOrderView,
)
from apps.orders.views import (
    AckOrderView,
    AddItemView,
    CompView,
    DiscountView,
    FireView,
    KdsTicketsView,
    ModifyItemView,
    OpenOrderView,
    OrderDetailView,
    PriceOverrideView,
    ReadyItemView,
    ReadyOrderView,
    RemoveItemView,
    ServeOrderView,
    StartItemView,
    SubmitOrderView,
    VoidOrderView,
)

urlpatterns = [
    path("orders", OpenOrderView.as_view(), name="orders-open"),
    path("orders/<uuid:order_id>", OrderDetailView.as_view(), name="orders-detail"),
    path("orders/<uuid:order_id>/items", AddItemView.as_view(), name="orders-add-item"),
    path(
        "orders/<uuid:order_id>/items/<uuid:item_id>/remove",
        RemoveItemView.as_view(),
        name="orders-remove-item",
    ),
    path(
        "orders/<uuid:order_id>/items/<uuid:item_id>/modify",
        ModifyItemView.as_view(),
        name="orders-modify-item",
    ),
    path("orders/<uuid:order_id>/submit", SubmitOrderView.as_view(), name="orders-submit"),
    path("orders/<uuid:order_id>/ack", AckOrderView.as_view(), name="orders-ack"),
    path(
        "orders/<uuid:order_id>/items/<uuid:item_id>/start",
        StartItemView.as_view(),
        name="orders-start-item",
    ),
    path(
        "orders/<uuid:order_id>/items/<uuid:item_id>/ready",
        ReadyItemView.as_view(),
        name="orders-ready-item",
    ),
    path("orders/<uuid:order_id>/ready", ReadyOrderView.as_view(), name="orders-ready"),
    path("orders/<uuid:order_id>/serve", ServeOrderView.as_view(), name="orders-serve"),
    path("orders/<uuid:order_id>/void", VoidOrderView.as_view(), name="orders-void"),
    path("orders/<uuid:order_id>/discount", DiscountView.as_view(), name="orders-discount"),
    path("orders/<uuid:order_id>/comp", CompView.as_view(), name="orders-comp"),
    path(
        "orders/<uuid:order_id>/items/<uuid:item_id>/price-override",
        PriceOverrideView.as_view(),
        name="orders-price-override",
    ),
    path("orders/<uuid:order_id>/fire", FireView.as_view(), name="orders-fire"),
    path("kds/tickets", KdsTicketsView.as_view(), name="kds-tickets"),
    # Guest
    path("guest/orders", GuestOpenOrderView.as_view(), name="guest-orders-open"),
    path(
        "guest/orders/<uuid:order_id>", GuestOrderDetailView.as_view(), name="guest-orders-detail"
    ),
    path(
        "guest/orders/<uuid:order_id>/items",
        GuestAddItemView.as_view(),
        name="guest-orders-add-item",
    ),
    path(
        "guest/orders/<uuid:order_id>/items/<uuid:item_id>/remove",
        GuestRemoveItemView.as_view(),
        name="guest-orders-remove-item",
    ),
    path(
        "guest/orders/<uuid:order_id>/items/<uuid:item_id>/modify",
        GuestModifyItemView.as_view(),
        name="guest-orders-modify-item",
    ),
    path(
        "guest/orders/<uuid:order_id>/submit",
        GuestSubmitOrderView.as_view(),
        name="guest-orders-submit",
    ),
]
