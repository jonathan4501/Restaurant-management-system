from django.apps import AppConfig


class MenuConfig(AppConfig):
    name = "apps.menu"
    label = "menu"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import projector  # noqa: F401  (registers projection handlers)
