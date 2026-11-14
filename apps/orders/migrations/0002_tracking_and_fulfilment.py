from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="order", name="cancelled_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="orderitem", name="fulfilment_status",
            field=models.CharField(
                choices=[("pending", "Not shipped yet"), ("shipped", "Shipped"), ("delivered", "Delivered")],
                default="pending", max_length=20,
            ),
        ),
        migrations.AddField(model_name="orderitem", name="carrier", field=models.CharField(blank=True, max_length=60)),
        migrations.AddField(model_name="orderitem", name="tracking_number", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="orderitem", name="shipped_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="orderitem", name="delivered_at", field=models.DateTimeField(blank=True, null=True)),
    ]
