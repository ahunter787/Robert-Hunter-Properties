"""ASGI entrypoint.

Not used by Phase 0 (gunicorn/WSGI is the canonical server), but present so an
async server or long-lived connection can be added without restructuring.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
