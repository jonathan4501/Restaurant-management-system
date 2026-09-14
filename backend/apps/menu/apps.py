from django.apps import AppConfig


class MenuConfig(AppConfig):
    name = "apps.menu"
    label = "menu"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import projector as _projector  # noqa: F401
        from . import signals as _signals

        _signals.connect_signals()
