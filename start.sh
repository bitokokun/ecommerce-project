#!/bin/sh
set -e
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] || [ -n "$DJANGO_SUPERUSER_EMAIL" ] || [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  if [ -z "$DJANGO_SUPERUSER_USERNAME" ] || [ -z "$DJANGO_SUPERUSER_EMAIL" ] || [ -z "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Set DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD together." >&2
    exit 1
  fi
  python manage.py shell -c 'import os; from django.contrib.auth import get_user_model; User=get_user_model(); username=os.environ["DJANGO_SUPERUSER_USERNAME"]; email=os.environ["DJANGO_SUPERUSER_EMAIL"]; password=os.environ["DJANGO_SUPERUSER_PASSWORD"]; User.objects.create_superuser(username=username, email=email, password=password) if not User.objects.filter(username=username).exists() else None'
fi

if [ "$SEED_DEMO" = "1" ]; then
  python manage.py seed_demo
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000
