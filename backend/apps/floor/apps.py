from django.apps import AppConfig


class FloorConfig(AppConfig):
    name = "apps.floor"
    label = "floor"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.core.projections import register_projection_model

        from . import projector  # noqa: F401
        from .models import TableSession

        register_projection_model(TableSession)
