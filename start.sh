#!/bin/sh
set -e
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser --noinput || true
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000
