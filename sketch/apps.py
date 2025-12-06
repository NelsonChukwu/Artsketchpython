from django.apps import AppConfig


class SketchConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sketch'

    def ready(self):
        # Import signals to create profiles on user creation
        from . import signals  # noqa: F401
