from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "apps.payments"
    label = "payments"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.core.projections import register_projection_model

        from .models import DrawerMovement, Payment, Shift

        register_projection_model(Shift)
        register_projection_model(Payment)
        register_projection_model(DrawerMovement)
