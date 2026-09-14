from django.apps import AppConfig


class PrintingConfig(AppConfig):
    """ESC/POS payload builders (WS12). No models."""

    name = "apps.printing"
    label = "printing"
