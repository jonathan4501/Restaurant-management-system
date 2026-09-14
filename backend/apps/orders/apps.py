from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = "apps.orders"
    label = "orders"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.core.projections import register_projection_model

        from . import projector  # noqa: F401
        from .models import Order, OrderItem

        register_projection_model(Order)
        register_projection_model(OrderItem)
