import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_one_default_address_per_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.ImageField(blank=True, upload_to="avatars/"),
        ),
        migrations.AddField(
            model_name="user",
            name="marketing_emails",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="order_update_emails",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="SellerProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("store_name", models.CharField(max_length=80)),
                ("description", models.TextField(blank=True, max_length=1000)),
                ("logo", models.ImageField(blank=True, upload_to="stores/")),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("shipping_note", models.CharField(blank=True, max_length=255)),
                ("return_policy", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="store",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
