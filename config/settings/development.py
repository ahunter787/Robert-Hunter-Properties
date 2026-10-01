"""Development settings: local workstations, Docker Compose dev stack, tests."""

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "[::1]"],
)

# Debug tooling expects this for tracebacks rendered in the browser.
INTERNAL_IPS = ["127.0.0.1"]

# Surface every query while developing; production keeps the base defaults.
LOGGING["loggers"]["django.db.backends"] = {  # noqa: F405
    "handlers": ["console"],  # noqa: F405
    "level": "INFO",
    "propagate": False,
}
