#!/bin/sh
set -e
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser --noinput || true
# Optional: set SEED_DEMO=1 on Render to fill the shop with demo products
if [ -n "$SEED_DEMO" ]; then
  python manage.py seed_demo || true
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000
