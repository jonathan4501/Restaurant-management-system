from django.urls import path

from apps.menu.views import (
    EightySixView,
    GuestMenuView,
    MenuView,
    PriceChangeView,
    RestoreView,
)

urlpatterns = [
    path("menu", MenuView.as_view(), name="menu"),
    path("guest/menu", GuestMenuView.as_view(), name="guest-menu"),
    path("menu/items/<uuid:item_id>/86", EightySixView.as_view(), name="menu-item-86"),
    path("menu/items/<uuid:item_id>/restore", RestoreView.as_view(), name="menu-item-restore"),
    path("menu/items/<uuid:item_id>/price", PriceChangeView.as_view(), name="menu-item-price"),
]
