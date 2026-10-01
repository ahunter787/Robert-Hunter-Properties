"""Container healthcheck.

The container is healthy only when ``/healthz`` answers 200, which in turn
requires a working database connection. ``X-Forwarded-Proto`` is sent so the
probe still succeeds when production enables ``SECURE_SSL_REDIRECT`` (the
header mirrors what Caddy sends for real traffic).
"""

import os
import sys
import urllib.error
import urllib.request

PORT = os.environ.get("PORT", "8000")
URL = f"http://127.0.0.1:{PORT}/healthz"


def main() -> int:
    request = urllib.request.Request(URL, headers={"X-Forwarded-Proto": "https"})
    try:
        # noqa: S310 - the scheme is a hardcoded http:// URL for the local probe.
        with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310
            return 0 if response.status == 200 else 1
    except urllib.error.URLError, OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
