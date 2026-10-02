"""Development settings: local workstations, Docker Compose dev stack, tests."""

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# Development answers on whatever address you reach it by: the point of the dev
# stack is that you can open it from a phone on the same network, and a LAN
# address is handed out by DHCP. Production is the opposite — it requires an
# explicit DJANGO_ALLOWED_HOSTS and refuses to boot without one (production.py).
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

# Debug tooling expects this for tracebacks rendered in the browser.
INTERNAL_IPS = ["127.0.0.1"]

# Surface every query while developing; production keeps the base defaults.
LOGGING["loggers"]["django.db.backends"] = {  # noqa: F405
    "handlers": ["console"],  # noqa: F405
    "level": "INFO",
    "propagate": False,
}
