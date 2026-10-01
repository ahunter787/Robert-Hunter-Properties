#!/bin/sh
# RHP container entrypoint.
#
#   web     migrations + collectstatic + gunicorn   (production, image default)
#   dev     migrations + runserver                  (development stack)
#   manage  pass through to manage.py               (e.g. docker compose exec web ...)
#   shell   Django shell
#
# Anything else is executed verbatim, so `docker run rhp-web:local bash` works.
set -eu

case "${1:-web}" in
  web)
    shift
    echo "rhp: applying database migrations"
    python manage.py migrate --noinput
    echo "rhp: collecting static files"
    python manage.py collectstatic --noinput
    exec gunicorn config.wsgi:application \
      --bind "0.0.0.0:${PORT:-8000}" \
      --workers "${GUNICORN_WORKERS:-3}" \
      --timeout "${GUNICORN_TIMEOUT:-60}" \
      --access-logfile - \
      --error-logfile - \
      "$@"
    ;;
  dev)
    shift
    echo "rhp: applying database migrations"
    python manage.py migrate --noinput
    exec python manage.py runserver "0.0.0.0:${PORT:-8000}" "$@"
    ;;
  manage)
    shift
    exec python manage.py "$@"
    ;;
  shell)
    exec python manage.py shell
    ;;
  *)
    exec "$@"
    ;;
esac
