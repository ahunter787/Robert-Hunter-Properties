"""uv run python -m tools.design_prototype [serve|export]"""

import argparse
import os
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server


class ReviewServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    request_queue_size = 32


class QuietHandler(WSGIRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, format, *args):
        pass  # No names, snapshot data or request parameters in access logs.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["serve", "export"], nargs="?", default="serve")
    parser.add_argument("--port", type=int, default=8014)
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    os.environ["DJANGO_SETTINGS_MODULE"] = (
        "config.settings.development"
        if args.command == "export"
        else "tools.design_prototype.settings"
    )
    import django

    django.setup()
    if args.command == "export":
        from .export import export_snapshot

        print(export_snapshot())  # noqa: T201 - intentionally only the private file path
        return
    if args.port in {8000, 8080, 8090, 8025, 1025, 8443, 10025, 10465, 10587, 5432}:
        parser.error("That port belongs to RHP or its ecosystem.")
    if args.snapshot:
        from .data import load_snapshot

        load_snapshot(args.snapshot)
    from django.conf import settings
    from django.core.wsgi import get_wsgi_application

    settings.SESSION_COOKIE_NAME = f"rhp_design_review_{args.port}"
    settings.CSRF_COOKIE_NAME = f"rhp_design_csrf_{args.port}"

    with make_server(
        "127.0.0.1",
        args.port,
        get_wsgi_application(),
        server_class=ReviewServer,
        handler_class=QuietHandler,
    ) as server:
        print(  # noqa: T201 - loopback launch URL only
            f"RHP design review: http://127.0.0.1:{server.server_port}/ — Ctrl+C to stop",
            flush=True,
        )  # noqa: T201
        server.serve_forever()


if __name__ == "__main__":
    main()
