from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    name = "apps.communications"

    def ready(self):
        from . import signals  # noqa: F401
