from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import IdempotencyKey


class Command(BaseCommand):
    help = "Delete idempotency keys older than the given number of hours"

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=48)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=options["hours"])
        deleted, _ = IdempotencyKey.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"Deleted {deleted} idempotency key(s).")
